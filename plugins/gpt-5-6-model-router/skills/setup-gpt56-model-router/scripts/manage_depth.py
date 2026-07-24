#!/usr/bin/env python3
"""Pure-ish ownership-aware management for the router's agents.max_depth entry."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10
    plugin_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(plugin_root / "vendor"))
    import tomli as tomllib  # type: ignore[no-redef]


MARKER = "# Managed by gpt-5-6-model-router; depth; schema=3"
LEGACY_MARKER = "# Managed by gpt-5-6-model-router; recursion; schema=2"
STATE_NAME = ".gpt56-router-depth-state.json"
LEGACY_STATE_NAME = ".gpt56-router-recursion-state.json"


@dataclass
class Result:
    ok: bool
    command: str
    config_path: str
    state_path: str
    effective_depth: int | None = None
    managed: bool = False
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    backed_up: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary, 0o600); os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _result(command: str, config: Path, state: Path, **values: object) -> Result:
    return Result(command=command, config_path=str(config), state_path=str(state), **values)


def _parse(content: bytes) -> tuple[dict, str | None]:
    try:
        return tomllib.loads(content.decode("utf-8")) if content else {}, None
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return {}, f"config.toml is invalid: {error}"


def _depth(parsed: dict) -> int | None:
    value = parsed.get("agents", {}).get("max_depth")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _load_json(path: Path) -> tuple[dict | None, str | None]:
    if not path.exists(): return None, None
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: return None, f"router depth state is unreadable: {error}"
    return (value, None) if isinstance(value, dict) else (None, "router depth state is not an object")


def _replace_depth(content: bytes, value: int, marker: str = MARKER) -> bytes:
    text = content.decode("utf-8") if content else ""
    lines = text.splitlines()
    agents = next((i for i, line in enumerate(lines) if re.fullmatch(r"\s*\[agents\]\s*", line)), None)
    if agents is None:
        if lines and lines[-1].strip(): lines.append("")
        lines.extend(("[agents]", marker, f"max_depth = {value}"))
    else:
        end = next((i for i in range(agents + 1, len(lines)) if re.fullmatch(r"\s*\[.*\]\s*", lines[i])), len(lines))
        depth_lines = [i for i in range(agents + 1, end) if re.fullmatch(r"\s*max_depth\s*=.*", lines[i])]
        if len(depth_lines) > 1: raise ValueError("agents.max_depth is declared more than once")
        if depth_lines:
            index = depth_lines[0]
            if index > agents + 1 and lines[index - 1] in (MARKER, LEGACY_MARKER): lines[index - 1] = marker
            else: lines.insert(index, marker); index += 1
            lines[index] = f"max_depth = {value}"
        else:
            lines[agents + 1:agents + 1] = [marker, f"max_depth = {value}"]
    return ("\n".join(lines).rstrip() + "\n").encode()


def _restore_depth(content: bytes, prior_depth: int | None, managed_value: int) -> bytes:
    lines = content.decode("utf-8").splitlines()
    marker_indices = [i for i, line in enumerate(lines) if line == MARKER]
    if len(marker_indices) != 1: raise ValueError("managed depth marker is missing or duplicated")
    marker = marker_indices[0]
    if marker + 1 >= len(lines) or not re.fullmatch(
        rf"\s*max_depth\s*=\s*{managed_value}\s*", lines[marker + 1]
    ):
        raise ValueError("managed depth entry was edited")
    if prior_depth is None:
        del lines[marker:marker + 2]
        agents = next((i for i, line in enumerate(lines) if re.fullmatch(r"\s*\[agents\]\s*", line)), None)
        if agents is not None:
            end = next((i for i in range(agents + 1, len(lines)) if re.fullmatch(r"\s*\[.*\]\s*", lines[i])), len(lines))
            if not any(line.strip() and not line.lstrip().startswith("#") for line in lines[agents + 1:end]):
                del lines[agents:end]
                while agents > 0 and agents <= len(lines) and not lines[agents - 1].strip():
                    del lines[agents - 1]; agents -= 1
    else: lines[marker:marker + 2] = [f"max_depth = {prior_depth}"]
    return ("\n".join(lines).rstrip() + "\n").encode() if lines else b""


def _legacy_original_depth(codex: Path, legacy: dict) -> tuple[int | None, str | None]:
    required = {"schema", "backup_path", "original_exists", "original_sha256", "managed_sha256"}
    if legacy.get("schema") != 2 or not required.issubset(legacy): return None, "legacy recursion state is incomplete"
    backup = Path(str(legacy["backup_path"]))
    if not backup.is_file(): return None, "legacy recursion backup is missing"
    original = backup.read_bytes()
    if _digest(original) != legacy["original_sha256"]: return None, "legacy recursion backup checksum differs"
    parsed, error = _parse(original)
    return (_depth(parsed), error)


def preflight(command: str, codex: Path) -> Result:
    config, state_path = codex / "config.toml", codex / STATE_NAME
    content = config.read_bytes() if config.exists() else b""
    parsed, error = _parse(content)
    if error: return _result(command, config, state_path, ok=False, errors=[error])
    depth = _depth(parsed)
    state, state_error = _load_json(state_path)
    legacy, legacy_error = _load_json(codex / LEGACY_STATE_NAME)
    if state_error or legacy_error: return _result(command, config, state_path, ok=False, effective_depth=depth, errors=[state_error or legacy_error])
    marker = MARKER.encode() in content
    legacy_marker = LEGACY_MARKER.encode() in content
    if state:
        managed_value = state.get("managed_value")
        if state.get("schema") != 3 or managed_value not in (1, 2): return _result(command, config, state_path, ok=False, effective_depth=depth, errors=["router depth state is unrecognized"])
        if not marker or depth != managed_value: return _result(command, config, state_path, ok=False, effective_depth=depth, errors=["managed depth entry was edited; refusing to overwrite it"])
        if managed_value == 2 and command == "check":
            return _result(command, config, state_path, ok=False, effective_depth=depth, managed=True, errors=["managed depth is two; run install to contract it to one"])
        status = "managed depth entry is intact" if managed_value == 1 else "managed depth-two entry can be contracted"
        return _result(command, config, state_path, ok=True, effective_depth=depth, managed=True, unchanged=[status])
    if marker: return _result(command, config, state_path, ok=False, effective_depth=depth, errors=["managed depth marker exists without trusted state"])
    if legacy or legacy_marker:
        if not (legacy and legacy_marker and depth == 2):
            return _result(command, config, state_path, ok=False, effective_depth=depth, errors=["legacy router-owned depth entry is not intact"])
        _, legacy_error = _legacy_original_depth(codex, legacy)
        if legacy_error: return _result(command, config, state_path, ok=False, effective_depth=depth, errors=[legacy_error])
        if command == "check":
            return _result(command, config, state_path, ok=False, effective_depth=2, managed=True, errors=["legacy depth is two; run install to contract it to one"])
        return _result(command, config, state_path, ok=True, effective_depth=2, managed=True, unchanged=["legacy router-owned depth can be adopted"])
    if command == "uninstall": return _result(command, config, state_path, ok=True, effective_depth=depth, unchanged=["no router-owned depth entry"])
    if depth == 1: return _result(command, config, state_path, ok=True, effective_depth=depth, unchanged=["existing depth already satisfies the router"])
    if command == "check": return _result(command, config, state_path, ok=False, effective_depth=depth, errors=["agents.max_depth must equal 1; run install"])
    return _result(command, config, state_path, ok=True, effective_depth=depth, unchanged=["depth entry can be installed"])


def install(codex: Path) -> Result:
    ready = preflight("install", codex)
    if not ready.ok: return ready
    config, state_path = codex / "config.toml", codex / STATE_NAME
    content = config.read_bytes() if config.exists() else b""
    legacy_path = codex / LEGACY_STATE_NAME
    legacy, _ = _load_json(legacy_path)
    state, _ = _load_json(state_path)
    if ready.managed and state_path.exists() and state and state.get("managed_value") == 1: return ready
    if ready.managed and state_path.exists() and state and state.get("managed_value") == 2:
        managed = _replace_depth(content, 1)
        state["managed_value"] = 1
        try:
            atomic_write(config, managed)
            atomic_write(state_path, (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
        except OSError as error:
            return _result("install", config, state_path, ok=False, effective_depth=ready.effective_depth, errors=[f"depth contraction failed: {error}"])
        checked = preflight("check", codex)
        checked.command = "install"
        checked.changed = ["agents.max_depth=1", "depth ownership state"]
        return checked
    if legacy:
        prior_depth, error = _legacy_original_depth(codex, legacy)
        if error: return _result("install", config, state_path, ok=False, effective_depth=2, errors=[error])
        managed = _replace_depth(content, 1)
        backup_path = str(legacy["backup_path"])
    elif ready.effective_depth == 1:
        return ready
    else:
        prior_depth = ready.effective_depth
        backup_dir = codex / ".gpt56-router-depth-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ%f")
        backup_dir.mkdir(parents=True, exist_ok=False)
        backup = backup_dir / "config.toml"
        backup.write_bytes(content)
        backup_path = str(backup)
        managed = _replace_depth(content, 1)
    state = {"schema": 3, "managed_value": 1, "prior_depth": prior_depth, "backup_path": backup_path}
    try:
        atomic_write(config, managed)
        atomic_write(state_path, (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
        legacy_path.unlink(missing_ok=True)
    except OSError as error:
        return _result("install", config, state_path, ok=False, effective_depth=ready.effective_depth, errors=[f"depth install failed: {error}"])
    checked = preflight("check", codex)
    checked.command = "install"; checked.changed = ["agents.max_depth=1", "depth ownership state"]
    checked.backed_up = [backup_path]
    return checked


def uninstall(codex: Path) -> Result:
    ready = preflight("uninstall", codex)
    if not ready.ok or not ready.managed: return ready
    config, state_path = codex / "config.toml", codex / STATE_NAME
    state, _ = _load_json(state_path)
    if state is None: return _result("uninstall", config, state_path, ok=False, errors=["legacy depth must be adopted with install before uninstall"])
    current = config.read_bytes()
    try: restored = _restore_depth(current, state.get("prior_depth"), int(state.get("managed_value")))
    except ValueError as error: return _result("uninstall", config, state_path, ok=False, effective_depth=ready.effective_depth, errors=[str(error)])
    try:
        if restored: atomic_write(config, restored)
        else: config.unlink(missing_ok=True)
        state_path.unlink()
    except OSError as error:
        return _result("uninstall", config, state_path, ok=False, effective_depth=ready.effective_depth, errors=[f"depth uninstall failed: {error}"])
    parsed, _ = _parse(restored)
    return _result("uninstall", config, state_path, ok=True, effective_depth=_depth(parsed), changed=["restored prior agents.max_depth"], unchanged=["unrelated config preserved"])


def to_dict(value: Result) -> dict:
    return asdict(value)
