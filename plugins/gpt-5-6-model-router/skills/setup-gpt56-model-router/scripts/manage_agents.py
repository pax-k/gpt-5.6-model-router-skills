#!/usr/bin/env python3
"""Safely manage the custom agents owned by gpt-5-6-model-router."""

from __future__ import annotations

import argparse
import hashlib
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
    r"^# Managed by gpt-5-6-model-router; agent=([a-z0-9_]+); schema=4$"
)
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
LEGACY_SCHEMA2_SHA256 = {
    "gpt56-router-luna-worker.toml": "7aa785ef640d85f1bc36aa28c561daeba05834e6f4d7eaf057b86c6f876355f9",
    "gpt56-router-sol-advisor.toml": "ee1132e57aa9f9a161248105a6637f855cba9dd6e482e79e4a8bc0965c30ce27",
    "gpt56-router-sol-debugger.toml": "0f6d302a56e5e76a9cd8f79ab504e01303dd62e6a539f06a5a50f12af0516be4",
    "gpt56-router-sol-engineer.toml": "15fba2a305c0fa0a05eff138d3ee4ad196472340e518a5e9b2787d7d6a3bcbbd",
    "gpt56-router-sol-reviewer.toml": "8a3380a7f689e4b4e39a4208dbb9583f625283bd8e9ba1d4d95f588c205d809a",
    "gpt56-router-sol-specialist-max.toml": "72665a4846ac502cf69d389c1be553dd148848fdfa1a9e3bf2ffbf8b714b1bcb",
    "gpt56-router-sol-specialist-xhigh.toml": "a919ab1826853213723286942de50aa5893f3220041c986b89a7b64f902ef0c0",
    "gpt56-router-terra-explorer.toml": "39b02a9a3884b2f63dfd1de545da8acb98b7072b933cf5f03c8e994685ddf4b0",
    "gpt56-router-terra-investigator.toml": "4eafd5d895b275fbe90062ec6550523f10d69af42e3984a61eb95dd30f44279f",
    "gpt56-router-terra-worker.toml": "959660d50170f429903dde653c1e52b9a4fd4318b3fac32208d87950dfd9b83a",
}
LEGACY_SCHEMA3_SHA256 = {
    "gpt56-router-luna-worker.toml": "e5fee6650fccaf09e5dcb27103e466514fe8f0ee4fb447eb1b2d5f04a0a83b5f",
    "gpt56-router-sol-advisor.toml": "a279198611a9b1a8da4ef4fc950eab970ce38b0f7e2b0849f43ddbaadb0133c3",
    "gpt56-router-sol-debugger.toml": "416611a0db562afd9105bacfb10923292642cf2bdea5c58fdeb70759706e246c",
    "gpt56-router-sol-engineer.toml": "5aef9afbbf590d2d532829a3ce83a0dda73caa31385d092d1a22d09398196c33",
    "gpt56-router-sol-reviewer.toml": "842ba0e8dd15ec35ecbad3d50a911698da1e3886e5d7a1286bba0d82a7ddc07c",
    "gpt56-router-sol-specialist-max.toml": "dbe70515bc500ef2b477297b66f04d32587ccc0e69afcdb417e67361c9600c03",
    "gpt56-router-sol-specialist-xhigh.toml": "5a5d9a1968f9fdc5e2a24ea728972449c744f6051f9bedc85996ba793a8ae0c3",
    "gpt56-router-terra-explorer.toml": "709c8b9d12b4f78d4c9876fd4ef21c7db974bd28f4c2cc7bf58ea11cb6a98afb",
    "gpt56-router-terra-investigator.toml": "ccad9947c85a586c1b23eff803e829b1d1944858082deca572c3389abd6763a4",
    "gpt56-router-terra-worker.toml": "d16bc4d811850c3afb08343814b0eaa563da62145319ccda7723ac2d53b1dd51",
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
    return f"# Managed by {PLUGIN_ID}; agent={agent_name}; schema=4"


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
    legacy = [
        filename for filename in divergent
        if (destination / filename).is_file()
        and hashlib.sha256((destination / filename).read_bytes()).hexdigest()
        in {LEGACY_SCHEMA2_SHA256[filename], LEGACY_SCHEMA3_SHA256[filename]}
    ]
    refused = [filename for filename in divergent if filename not in legacy]
    if refused and not force:
        return Result(
            ok=False,
            command="install",
            target_dir=str(destination),
            unchanged=unchanged,
            missing=missing,
            divergent=refused,
            errors=[
                "refusing to overwrite unknown or user-modified files; inspect them and explicitly rerun with --force"
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
