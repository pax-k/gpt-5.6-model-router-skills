#!/usr/bin/env python3
"""Safely manage the custom agents owned by gpt-5-6-model-router."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


PLUGIN_ID = "gpt-5-6-model-router"
MARKER_PATTERN = re.compile(
    r"^# Managed by gpt-5-6-model-router; agent=([a-z0-9_]+); schema=2$"
)
CAPABILITY_MARKER_PATTERN = re.compile(r"^# Router capability: may_delegate=(true|false)$")
NAME_PATTERN = re.compile(r'^name\s*=\s*"([a-z0-9_]+)"\s*$', re.MULTILINE)
EXPECTED_AGENTS = {
    "gpt56-router-luna-worker.toml": "gpt56_router_luna_worker",
    "gpt56-router-terra-explorer.toml": "gpt56_router_terra_explorer",
    "gpt56-router-terra-worker.toml": "gpt56_router_terra_worker",
    "gpt56-router-sol-engineer.toml": "gpt56_router_sol_engineer",
    "gpt56-router-sol-debugger.toml": "gpt56_router_sol_debugger",
    "gpt56-router-sol-reviewer.toml": "gpt56_router_sol_reviewer",
    "gpt56-router-terra-investigator.toml": "gpt56_router_terra_investigator",
    "gpt56-router-sol-specialist-xhigh.toml": "gpt56_router_sol_specialist_xhigh",
    "gpt56-router-sol-specialist-max.toml": "gpt56_router_sol_specialist_max",
    "gpt56-router-sol-advisor.toml": "gpt56_router_sol_advisor",
}
DELEGATING_AGENTS = {
    "gpt56_router_terra_explorer",
    "gpt56_router_sol_engineer",
}


@dataclass
class Result:
    ok: bool
    command: str
    target_dir: str
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    backed_up: list[str] = field(default_factory=list)
    migrated_backups: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    divergent: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def template_dir() -> Path:
    return skill_dir() / "assets" / "agents"


def target_dir() -> Path:
    return Path.home() / ".codex" / "agents"


def backup_root(destination: Path) -> Path:
    """Keep backups outside the recursively discovered custom-agent tree."""
    return destination.parent / ".gpt56-router-agent-backups"


def migrate_legacy_backups(destination: Path) -> list[str]:
    """Move router-owned legacy backups out of ~/.codex/agents safely."""
    legacy = destination / ".gpt56-router-backups"
    if not legacy.exists():
        return []
    if not legacy.is_dir():
        raise OSError(f"legacy router backup path is not a directory: {legacy}")
    root = backup_root(destination)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ%f")
    target = root / f"legacy-{timestamp}"
    shutil.move(str(legacy), target)
    return [str(target)]


def marker_for(agent_name: str) -> str:
    return f"# Managed by {PLUGIN_ID}; agent={agent_name}; schema=2"


def capability_marker_for(agent_name: str) -> str:
    may_delegate = "true" if agent_name in DELEGATING_AGENTS else "false"
    return f"# Router capability: may_delegate={may_delegate}"


def validate_owned_content(content: bytes, filename: str) -> tuple[bool, str]:
    expected_name = EXPECTED_AGENTS[filename]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return False, "content is not UTF-8"

    lines = text.splitlines()
    first_line = lines[0] if lines else ""
    marker = MARKER_PATTERN.fullmatch(first_line)
    if marker is None or marker.group(1) != expected_name:
        return False, "managed marker does not match expected agent identity"
    second_line = lines[1] if len(lines) > 1 else ""
    capability_marker = CAPABILITY_MARKER_PATTERN.fullmatch(second_line)
    if capability_marker is None or second_line != capability_marker_for(expected_name):
        return False, "router capability marker does not match expected delegation policy"

    name = NAME_PATTERN.search(text)
    if name is None or name.group(1) != expected_name:
        return False, "TOML name does not match expected agent identity"
    return True, ""


def load_templates() -> tuple[dict[str, bytes], list[str]]:
    templates: dict[str, bytes] = {}
    errors: list[str] = []
    root = template_dir()
    for filename in EXPECTED_AGENTS:
        path = root / filename
        if not path.is_file():
            errors.append(f"missing bundled template: {path}")
            continue
        content = path.read_bytes()
        valid, reason = validate_owned_content(content, filename)
        if not valid:
            errors.append(f"invalid bundled template {filename}: {reason}")
            continue
        templates[filename] = content
    return templates, errors


def atomic_write(path: Path, content: bytes) -> None:
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


def inspect(templates: dict[str, bytes], destination: Path) -> tuple[list[str], list[str], list[str]]:
    missing: list[str] = []
    unchanged: list[str] = []
    divergent: list[str] = []
    for filename, expected in templates.items():
        path = destination / filename
        if not path.exists():
            missing.append(filename)
        elif not path.is_file() or path.read_bytes() != expected:
            divergent.append(filename)
        else:
            unchanged.append(filename)
    return missing, unchanged, divergent


def check_agents(templates: dict[str, bytes], destination: Path) -> Result:
    missing, unchanged, divergent = inspect(templates, destination)
    errors: list[str] = []
    if missing:
        errors.append("router setup is missing managed agent files")
    if divergent:
        errors.append("router setup contains divergent managed destinations")
    legacy = destination / ".gpt56-router-backups"
    if legacy.exists():
        errors.append("legacy router backups are inside the custom-agent discovery tree; run install to migrate them")
    return Result(
        ok=not errors,
        command="check",
        target_dir=str(destination),
        unchanged=unchanged,
        missing=missing,
        divergent=divergent,
        errors=errors,
    )


def install_agents(templates: dict[str, bytes], destination: Path, force: bool) -> Result:
    missing, unchanged, divergent = inspect(templates, destination)
    if divergent and not force:
        return Result(
            ok=False,
            command="install",
            target_dir=str(destination),
            unchanged=unchanged,
            missing=missing,
            divergent=divergent,
            errors=[
                "refusing to overwrite divergent files; inspect them and explicitly rerun with --force"
            ],
        )

    destination.mkdir(parents=True, exist_ok=True)
    try:
        migrated_backups = migrate_legacy_backups(destination)
    except OSError as error:
        return Result(
            ok=False,
            command="install",
            target_dir=str(destination),
            unchanged=unchanged,
            missing=missing,
            divergent=divergent,
            errors=[f"failed to migrate legacy router backups: {error}"],
        )
    backed_up: list[str] = []
    if divergent:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = backup_root(destination) / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        for filename in divergent:
            source = destination / filename
            backup = backup_dir / filename
            shutil.copy2(source, backup)
            backed_up.append(str(backup))

    changed: list[str] = []
    for filename in [*missing, *divergent]:
        atomic_write(destination / filename, templates[filename])
        changed.append(filename)

    final_missing, _, final_divergent = inspect(templates, destination)
    errors: list[str] = []
    if final_missing or final_divergent:
        errors.append("post-install verification failed")
    return Result(
        ok=not errors,
        command="install",
        target_dir=str(destination),
        changed=changed,
        unchanged=unchanged,
        backed_up=backed_up,
        migrated_backups=migrated_backups,
        missing=final_missing,
        divergent=final_divergent,
        errors=errors,
    )


def uninstall_agents(
    templates: dict[str, bytes], destination: Path, force: bool = False
) -> Result:
    removable: list[str] = []
    divergent: list[str] = []
    errors: list[str] = []

    for filename, expected in templates.items():
        path = destination / filename
        if not path.exists():
            continue
        if not path.is_file():
            errors.append(f"refusing to remove non-file destination: {filename}")
            continue
        content = path.read_bytes()
        if content != expected:
            divergent.append(filename)
            valid, reason = validate_owned_content(content, filename)
            if not valid and not force:
                errors.append(f"refusing to remove unmanaged destination {filename}: {reason}")
            continue
        removable.append(filename)

    if divergent and not force and not errors:
        errors.append(
            "refusing to remove divergent files without backup; "
            "inspect them and explicitly rerun with --force: " + ", ".join(divergent)
        )

    if errors or (divergent and not force):
        return Result(
            ok=False,
            command="uninstall",
            target_dir=str(destination),
            unchanged=removable,
            divergent=divergent,
            errors=errors,
        )

    try:
        migrated_backups = migrate_legacy_backups(destination)
    except OSError as error:
        return Result(
            ok=False,
            command="uninstall",
            target_dir=str(destination),
            unchanged=removable,
            divergent=divergent,
            errors=[f"failed to migrate legacy router backups; nothing was removed: {error}"],
        )

    backed_up: list[str] = []
    if divergent:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ%f")
        backup_dir = backup_root(destination) / timestamp
        try:
            backup_dir.mkdir(parents=True, exist_ok=False)
            for filename in divergent:
                backup = backup_dir / filename
                shutil.copy2(destination / filename, backup)
                backed_up.append(str(backup))
        except OSError as error:
            return Result(
                ok=False,
                command="uninstall",
                target_dir=str(destination),
                unchanged=removable,
                backed_up=backed_up,
                divergent=divergent,
                errors=[f"failed to back up divergent files; nothing was removed: {error}"],
            )

    changed: list[str] = []
    try:
        for filename in [*removable, *divergent]:
            (destination / filename).unlink()
            changed.append(filename)
    except OSError as error:
        return Result(
            ok=False,
            command="uninstall",
            target_dir=str(destination),
            changed=changed,
            backed_up=backed_up,
            divergent=divergent,
            errors=[f"uninstall failed after removing {len(changed)} file(s): {error}"],
        )

    missing = [filename for filename in templates if not (destination / filename).exists()]
    return Result(
        ok=True,
        command="uninstall",
        target_dir=str(destination),
        changed=changed,
        backed_up=backed_up,
        migrated_backups=migrated_backups,
        missing=missing,
    )


def render(result: Result, as_json: bool) -> None:
    payload = asdict(result)
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print(f"{result.command}: {'ok' if result.ok else 'failed'}")
    print(f"target: {result.target_dir}")
    for key in ("changed", "unchanged", "backed_up", "migrated_backups", "missing", "divergent", "errors"):
        values = getattr(result, key)
        if values:
            print(f"{key}: {', '.join(values)}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "check", "uninstall"))
    parser.add_argument(
        "--force",
        action="store_true",
        help="Back up divergent files before replacing them on install or removing them on uninstall.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON result.")
    args = parser.parse_args(argv)
    if args.force and args.command == "check":
        parser.error("--force is valid only with install or uninstall")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    destination = target_dir()
    templates, errors = load_templates()
    if errors:
        result = Result(
            ok=False,
            command=args.command,
            target_dir=str(destination),
            errors=errors,
        )
    elif args.command == "check":
        result = check_agents(templates, destination)
    elif args.command == "install":
        result = install_agents(templates, destination, args.force)
    else:
        result = uninstall_agents(templates, destination, args.force)
    render(result, args.json)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
