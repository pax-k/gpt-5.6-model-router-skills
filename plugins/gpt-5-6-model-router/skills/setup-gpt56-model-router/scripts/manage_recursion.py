#!/usr/bin/env python3
"""Safely manage the router-owned agents.max_depth recursion setting."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


PLUGIN_ID = "gpt-5-6-model-router"
SCHEMA = 2
MARKER = f"# Managed by {PLUGIN_ID}; recursion; schema={SCHEMA}"
SECTION_PATTERN = re.compile(r"^\s*\[agents\]\s*(?:#.*)?$")
SUBSECTION_PATTERN = re.compile(r"^\s*\[agents\.[^\]]+\]\s*(?:#.*)?$")
INLINE_OR_DOTTED_PATTERN = re.compile(r"^\s*agents(?:\s*=|\.[A-Za-z0-9_-]+\s*=)")
TABLE_PATTERN = re.compile(r"^\s*\[[^\[][^\]]*\]\s*(?:#.*)?$")
MAX_DEPTH_PATTERN = re.compile(r"^(\s*max_depth\s*=\s*)\S+(\s*#.*)?(?:\r?\n)?$")


@dataclass
class Result:
    ok: bool
    command: str
    config_path: str
    state_path: str
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    backed_up: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def codex_dir() -> Path:
    return Path.home() / ".codex"


def config_path() -> Path:
    return codex_dir() / "config.toml"


def state_path() -> Path:
    return codex_dir() / ".gpt56-router-recursion-state.json"


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_config(content: bytes) -> tuple[dict[str, object] | None, str | None]:
    try:
        value = tomllib.loads(content.decode("utf-8")) if content else {}
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return None, f"config.toml is not valid UTF-8 TOML: {error}"
    if not isinstance(value, dict):
        return None, "config.toml root is not a TOML table"
    return value, None


def load_state(path: Path) -> tuple[dict[str, object] | None, str | None]:
    if not path.exists():
        return None, None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, f"recursion state is unreadable: {error}"
    required = {"schema", "backup_path", "original_exists", "original_sha256", "managed_sha256"}
    if not isinstance(value, dict) or not required.issubset(value):
        return None, "recursion state is incomplete or unrecognized"
    if value["schema"] != SCHEMA or not isinstance(value["backup_path"], str):
        return None, "recursion state has an unsupported schema"
    return value, None


def agents_section(lines: list[str]) -> tuple[int, int] | None:
    starts = [index for index, line in enumerate(lines) if SECTION_PATTERN.match(line)]
    if len(starts) != 1:
        return None
    start = starts[0]
    end = next(
        (index for index in range(start + 1, len(lines)) if TABLE_PATTERN.match(lines[index])),
        len(lines),
    )
    return start, end


def managed_config(original: bytes) -> tuple[bytes | None, str | None]:
    parsed, error = parse_config(original)
    if error:
        return None, error
    assert parsed is not None
    agents = parsed.get("agents")
    if agents is not None and not isinstance(agents, dict):
        return None, "agents is not a TOML table"
    if isinstance(agents, dict) and "max_depth" in agents and not isinstance(agents["max_depth"], int):
        return None, "agents.max_depth must be an integer"

    text = original.decode("utf-8")
    if MARKER in text:
        return None, "found a recursion ownership marker without a trusted matching state"
    lines = text.splitlines(keepends=True)
    section = agents_section(lines)
    if section is None:
        if isinstance(agents, dict):
            if any(INLINE_OR_DOTTED_PATTERN.match(line) for line in lines):
                return None, "agents uses an unsupported inline or dotted-key form; refusing to rewrite it"
            subsections = [index for index, line in enumerate(lines) if SUBSECTION_PATTERN.match(line)]
            if not subsections:
                return None, "agents table shape is unsupported; refusing to rewrite it"
            index = subsections[0]
            prefix = "" if index == 0 or lines[index - 1].endswith(("\n", "\r")) else "\n"
            lines.insert(index, prefix + "[agents]\n" + MARKER + "\nmax_depth = 2\n\n")
            return "".join(lines).encode(), None
        suffix = "" if not text or text.endswith(("\n", "\r")) else "\n"
        return (text + suffix + "\n[agents]\n" + MARKER + "\nmax_depth = 2\n").encode(), None

    start, end = section
    matches = [index for index in range(start + 1, end) if MAX_DEPTH_PATTERN.match(lines[index])]
    if len(matches) > 1:
        return None, "agents contains multiple max_depth assignments; refusing ambiguous edit"
    if not matches:
        lines.insert(end, MARKER + "\nmax_depth = 2\n")
        return "".join(lines).encode(), None

    index = matches[0]
    match = MAX_DEPTH_PATTERN.match(lines[index])
    assert match is not None
    newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index] = f"{match.group(1)}2{match.group(2) or ''}{newline}"
    lines.insert(index, MARKER + newline)
    return "".join(lines).encode(), None


def verify_enabled(content: bytes) -> tuple[bool, str | None]:
    if MARKER not in content.decode("utf-8", errors="replace"):
        return False, "recursion ownership marker is missing"
    parsed, error = parse_config(content)
    if error:
        return False, error
    assert parsed is not None
    agents = parsed.get("agents")
    if not isinstance(agents, dict) or agents.get("max_depth") != 2:
        return False, "agents.max_depth is not 2"
    return True, None


def backup_original(config: Path, original: bytes) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ%f")
    backup = codex_dir() / ".gpt56-router-recursion-backups" / timestamp / "config.toml"
    atomic_write(backup, original)
    return backup


def result(command: str, **kwargs: object) -> Result:
    return Result(command=command, config_path=str(config_path()), state_path=str(state_path()), **kwargs)


def check() -> Result:
    config = config_path()
    state, state_error = load_state(state_path())
    if state_error:
        return result("check", ok=False, errors=[state_error])
    content = config.read_bytes() if config.exists() else b""
    enabled, enabled_error = verify_enabled(content)
    if state is not None and enabled:
        unchanged = ["agents.max_depth=2"]
        if digest(content) != state["managed_sha256"]:
            unchanged.append("router marker/value intact; rollback remains guarded after later config edits")
        return result("check", ok=True, unchanged=unchanged)
    errors = ["router recursion is not safely managed"]
    if state is not None and digest(content) != state["managed_sha256"]:
        errors.append("config.toml changed after enable; refusing to infer ownership")
    elif enabled_error:
        errors.append(enabled_error)
    return result("check", ok=False, errors=errors)


def enable() -> Result:
    config = config_path()
    state, state_error = load_state(state_path())
    if state_error:
        return result("enable", ok=False, errors=[state_error])
    original_exists = config.exists()
    original = config.read_bytes() if original_exists else b""
    if state is not None:
        enabled, enabled_error = verify_enabled(original)
        if enabled:
            unchanged = ["agents.max_depth=2"]
            if digest(original) != state["managed_sha256"]:
                unchanged.append("router marker/value intact; rollback remains guarded after later config edits")
            return result("enable", ok=True, unchanged=unchanged)
        if digest(original) == state["managed_sha256"]:
            return result("enable", ok=False, errors=[enabled_error or "managed config is invalid"])
        return result("enable", ok=False, errors=["config.toml changed after enable; refusing ambiguous ownership"])

    managed, error = managed_config(original)
    if error:
        return result("enable", ok=False, errors=[error])
    assert managed is not None
    enabled, enabled_error = verify_enabled(managed)
    if not enabled:
        return result("enable", ok=False, errors=[enabled_error or "post-edit validation failed"])
    backup = backup_original(config, original)
    state_payload = {
        "schema": SCHEMA,
        "backup_path": str(backup),
        "original_exists": original_exists,
        "original_sha256": digest(original),
        "managed_sha256": digest(managed),
    }
    try:
        atomic_write(config, managed)
        atomic_write(state_path(), (json.dumps(state_payload, indent=2, sort_keys=True) + "\n").encode())
    except OSError as error:
        try:
            if original_exists:
                atomic_write(config, original)
            else:
                config.unlink(missing_ok=True)
            state_path().unlink(missing_ok=True)
        except OSError as rollback_error:
            return result(
                "enable",
                ok=False,
                backed_up=[str(backup)],
                errors=[f"recursion enable failed: {error}", f"automatic rollback also failed: {rollback_error}"],
            )
        return result(
            "enable",
            ok=False,
            backed_up=[str(backup)],
            errors=[f"recursion enable failed and was rolled back: {error}"],
        )
    return result("enable", ok=True, changed=["agents.max_depth=2"], backed_up=[str(backup)])


def disable() -> Result:
    config = config_path()
    state, state_error = load_state(state_path())
    if state_error:
        return result("disable", ok=False, errors=[state_error])
    if state is None:
        return result("disable", ok=False, errors=["no trusted recursion state exists; refusing rollback"])
    current = config.read_bytes() if config.exists() else b""
    if digest(current) != state["managed_sha256"]:
        return result("disable", ok=False, errors=["config.toml changed after enable; refusing ambiguous rollback"])
    enabled, enabled_error = verify_enabled(current)
    if not enabled:
        return result("disable", ok=False, errors=[enabled_error or "managed config is invalid"])
    backup = Path(state["backup_path"])
    if not backup.is_file():
        return result("disable", ok=False, errors=["saved full config backup is missing; refusing rollback"])
    original = backup.read_bytes()
    if digest(original) != state["original_sha256"]:
        return result("disable", ok=False, errors=["saved full config backup does not match trusted state"])
    try:
        if state["original_exists"]:
            atomic_write(config, original)
        else:
            config.unlink()
    except OSError as error:
        return result(
            "disable",
            ok=False,
            errors=[f"recursion disable failed before state removal; trusted state was retained: {error}"],
        )
    try:
        state_path().unlink()
    except OSError as error:
        try:
            atomic_write(config, current)
        except OSError as rollback_error:
            return result(
                "disable",
                ok=False,
                errors=[
                    f"recursion disable failed while removing state: {error}",
                    f"automatic rollback to the managed config also failed: {rollback_error}",
                ],
            )
        return result(
            "disable",
            ok=False,
            errors=[f"recursion disable failed and was rolled back: {error}"],
        )
    return result("disable", ok=True, changed=["agents.max_depth=2"], unchanged=["full backup retained"])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "enable", "disable"))
    parser.add_argument("--json", action="store_true", help="Emit a JSON result.")
    return parser.parse_args(argv)


def render(value: Result, as_json: bool) -> None:
    payload = asdict(value)
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"{value.command}: {'ok' if value.ok else 'failed'}")
    print(f"config: {value.config_path}")
    for key in ("changed", "unchanged", "backed_up", "errors"):
        if values := getattr(value, key):
            print(f"{key}: {', '.join(values)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    action = {"check": check, "enable": enable, "disable": disable}[args.command]
    try:
        outcome = action()
    except OSError as error:
        outcome = result(
            args.command,
            ok=False,
            errors=[f"recursion {args.command} failed: {error}"],
        )
    render(outcome, args.json)
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
