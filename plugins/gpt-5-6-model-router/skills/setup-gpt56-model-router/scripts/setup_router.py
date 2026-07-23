#!/usr/bin/env python3
"""Install, check, or uninstall the complete GPT-5.6 router contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import manage_agents
import manage_depth


@dataclass
class SetupResult:
    ok: bool
    command: str
    agents: dict
    depth: dict
    changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    runtime: dict = field(default_factory=dict)
    rolled_back: bool = False


def inspect_runtime(executable: str | None = None) -> dict:
    command = executable or shutil.which("codex")
    if not command:
        return {
            "ok": False,
            "errors": ["Codex CLI is unavailable; cannot verify stable hooks and multi-agent support"],
            "warnings": [],
            "features": {},
        }
    completed = subprocess.run(
        [command, "features", "list"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "errors": ["could not inspect Codex feature state"],
            "warnings": [completed.stderr.strip()] if completed.stderr.strip() else [],
            "features": {},
        }
    features: dict[str, dict[str, object]] = {}
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] in ("hooks", "multi_agent"):
            features[fields[0]] = {
                "maturity": fields[1],
                "enabled": fields[2].lower() == "true",
            }
    errors = []
    for name in ("hooks", "multi_agent"):
        feature = features.get(name)
        if not feature:
            errors.append(f"Codex does not report the required {name} feature")
        elif feature["maturity"] != "stable" or not feature["enabled"]:
            errors.append(f"Codex {name} must be stable and enabled")
    return {"ok": not errors, "errors": errors, "warnings": [], "features": features}


def _agent_preflight(command: str, templates: dict[str, bytes], destination: Path, force: bool) -> manage_agents.Result:
    if command == "check": return manage_agents.check_agents(templates, destination)
    missing, unchanged, divergent = manage_agents.inspect(templates, destination)
    if command == "install":
        legacy = []
        for filename in divergent:
            path = destination / filename
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() in {
                manage_agents.LEGACY_SCHEMA2_SHA256[filename],
                manage_agents.LEGACY_SCHEMA3_SHA256[filename],
                manage_agents.LEGACY_SCHEMA4_SHA256[filename],
            }: legacy.append(filename)
        refused = [name for name in divergent if name not in legacy]
        errors = [] if force or not refused else ["refusing modified templates without --force"]
        return manage_agents.Result(ok=not errors, command=command, target_dir=str(destination), missing=missing, unchanged=unchanged, divergent=refused, errors=errors)
    removable, refused = [], []
    for filename, expected in templates.items():
        path = destination / filename
        if not path.exists(): continue
        if path.is_file() and path.read_bytes() == expected: removable.append(filename)
        else: refused.append(filename)
    errors = [] if force or not refused else ["refusing divergent templates without --force"]
    return manage_agents.Result(ok=not errors, command=command, target_dir=str(destination), unchanged=removable, divergent=refused, errors=errors)


def _snapshot(paths: list[Path]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.is_file() else None for path in paths}


def _restore(snapshot: dict[Path, bytes | None]) -> list[str]:
    errors: list[str] = []
    for path, content in snapshot.items():
        try:
            if content is None: path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                manage_agents.atomic_write(path, content)
        except OSError as error: errors.append(f"rollback failed for {path}: {error}")
    return errors


def run(command: str, force: bool = False, *, codex: Path | None = None) -> SetupResult:
    codex = codex or Path.home() / ".codex"
    destination = codex / "agents"
    templates, template_errors = manage_agents.load_templates()
    if template_errors:
        empty = manage_agents.Result(ok=False, command=command, target_dir=str(destination), errors=template_errors)
        depth = manage_depth.preflight(command, codex)
        return SetupResult(False, command, asdict(empty), manage_depth.to_dict(depth), errors=template_errors)
    agent_ready = _agent_preflight(command, templates, destination, force)
    depth_ready = manage_depth.preflight(command, codex)
    if not agent_ready.ok or not depth_ready.ok:
        errors = [*agent_ready.errors, *depth_ready.errors]
        return SetupResult(False, command, asdict(agent_ready), manage_depth.to_dict(depth_ready), errors=errors)
    if command == "check":
        return SetupResult(True, command, asdict(agent_ready), manage_depth.to_dict(depth_ready))

    paths = [destination / name for name in templates]
    paths += [codex / "config.toml", codex / manage_depth.STATE_NAME, codex / manage_depth.LEGACY_STATE_NAME]
    snapshot = _snapshot(paths)
    if command == "install":
        depth_result = manage_depth.install(codex)
        agent_result = manage_agents.install_agents(templates, destination, force) if depth_result.ok else agent_ready
        post_agents = manage_agents.check_agents(templates, destination) if agent_result.ok else agent_result
        post_depth = manage_depth.preflight("check", codex) if agent_result.ok else depth_result
        ok = agent_result.ok and depth_result.ok and post_agents.ok and post_depth.ok and (post_depth.effective_depth or 0) >= 2
    else:
        agent_result = manage_agents.uninstall_agents(templates, destination, force)
        depth_result = manage_depth.uninstall(codex) if agent_result.ok else depth_ready
        ok = agent_result.ok and depth_result.ok
    if not ok:
        rollback_errors = _restore(snapshot)
        errors = [*agent_result.errors, *depth_result.errors, *rollback_errors]
        return SetupResult(False, command, asdict(agent_result), manage_depth.to_dict(depth_result), errors=errors or ["post-operation verification failed"], rolled_back=True)
    return SetupResult(True, command, asdict(agent_result), manage_depth.to_dict(depth_result), changed=[*agent_result.changed, *depth_result.changed])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "check", "uninstall"))
    parser.add_argument("--force", action="store_true", help="Back up and replace divergent templates; never overrides depth ownership checks.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv or sys.argv[1:])
    if args.force and args.command == "check": parser.error("--force is valid only with install or uninstall")
    if sys.version_info < (3, 9):
        parser.error("Python 3.9 or newer is required")
    runtime = inspect_runtime() if args.command in ("install", "check") else {
        "ok": True,
        "errors": [],
        "warnings": [],
        "features": {},
    }
    if not runtime["ok"]:
        payload = {
            "ok": False,
            "command": args.command,
            "runtime": runtime,
            "errors": runtime["errors"],
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"{args.command}: failed")
            print("errors: " + ", ".join(runtime["errors"]))
        return 1
    result = run(args.command, args.force)
    result.runtime = runtime
    payload = asdict(result)
    if args.json: print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{args.command}: {'ok' if result.ok else 'failed'}")
        if result.changed: print("changed: " + ", ".join(result.changed))
        if result.errors: print("errors: " + ", ".join(result.errors))
    return 0 if result.ok else 1


if __name__ == "__main__": raise SystemExit(main())
