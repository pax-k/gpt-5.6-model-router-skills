#!/usr/bin/env python3
"""Validate the governed v0.4 repository contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "gpt-5-6-model-router"
ROUTE = PLUGIN / "skills" / "route-gpt56-task"
SETUP = PLUGIN / "skills" / "setup-gpt56-model-router"
VERSION = re.compile(r"^0\.4\.1\+codex\.[A-Za-z0-9.-]+$")
MARKER = re.compile(r"^# Managed by gpt-5-6-model-router; agent=([a-z0-9_]+); schema=5$")

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10
    sys.path.insert(0, str(PLUGIN / "vendor"))
    import tomli as tomllib  # type: ignore[no-redef]


EXPECTED_ROUTES = {
    ("gpt-5.6-luna", "high"),
    ("gpt-5.6-terra", "medium"),
    ("gpt-5.6-terra", "high"),
    ("gpt-5.6-sol", "medium"),
    ("gpt-5.6-sol", "high"),
}
HOOK_EVENTS = {
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "SubagentStart",
    "SubagentStop",
    "Stop",
}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate() -> list[str]:
    errors: list[str] = []
    manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    require(bool(VERSION.fullmatch(str(manifest.get("version", "")))), "manifest must use v0.4.1 with one cachebuster", errors)
    require(marketplace["plugins"][0]["name"] == manifest["name"], "marketplace and manifest names differ", errors)
    require(manifest.get("skills") == "./skills/", "manifest must expose skills", errors)
    require(manifest.get("hooks") == "./hooks/hooks.json", "manifest must expose bundled hooks", errors)
    require(not any(key in manifest for key in ("apps", "mcpServers")), "plugin must not invent app or MCP components", errors)

    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())
    require(set(hooks.get("hooks", {})) == HOOK_EVENTS, "hook event inventory differs from v0.4 contract", errors)
    for event, groups in hooks.get("hooks", {}).items():
        for group in groups:
            for handler in group.get("hooks", []):
                require(handler.get("type") == "command", f"{event} must use a command hook", errors)
                require("$PLUGIN_ROOT" in handler.get("command", ""), f"{event} POSIX command must use PLUGIN_ROOT", errors)
                require("py -3" in handler.get("commandWindows", ""), f"{event} Windows command must use py -3", errors)
                require("route_guard.py" in handler.get("command", ""), f"{event} must execute route_guard.py", errors)

    for skill_name in ("route-gpt56-task", "setup-gpt56-model-router"):
        root = PLUGIN / "skills" / skill_name
        skill = (root / "SKILL.md").read_text()
        metadata = (root / "agents/openai.yaml").read_text()
        require(skill.startswith(f"---\nname: {skill_name}\n"), f"invalid frontmatter: {skill_name}", errors)
        require(
            f"${skill_name}" in metadata and "allow_implicit_invocation: false" in metadata,
            f"invalid explicit-only metadata: {skill_name}",
            errors,
        )

    scripts = ROUTE / "scripts"
    require((scripts / "route_guard.py").is_file(), "route_guard.py is missing", errors)
    require(not (scripts / "build_spawn_prompt.py").exists(), "legacy spawn helper must be removed", errors)
    require(not (scripts / "orchestrate.py").exists(), "legacy orchestration helper must be removed", errors)
    schemas = sorted((ROUTE / "schemas").glob("*.schema.json"))
    require(
        {path.name for path in schemas}
        == {
            "task-profile.schema.json",
            "route-recommendation.schema.json",
            "route-intent.schema.json",
        },
        "exactly the three schema-v4 contracts are required",
        errors,
    )
    for path in schemas:
        value = json.loads(path.read_text())
        require("v4" in value.get("$id", ""), f"schema ID is not v4: {path.name}", errors)
        require(value.get("properties", {}).get("schema_version", {}).get("const") == 4, f"schema version is not 4: {path.name}", errors)
        require("ultra" not in path.read_text(), f"Ultra is out of scope: {path.name}", errors)

    route_skill = (ROUTE / "SKILL.md").read_text()
    for text in (
        "every root `Agent` spawn on every turn",
        "Root rationale alone cannot change",
        "spawn_request",
        "critical execution uses at least Sol/medium",
        "manifest SHA-256",
        "trusted hooks are enforceable guardrails",
    ):
        require(text.lower() in route_skill.lower(), f"route skill missing governed contract: {text}", errors)
    guard = (scripts / "route_guard.py").read_text()
    for text in (
        "MISSING_ROUTE_INTENT",
        "ROUTER_STATE_UNAVAILABLE",
        "CUSTOM_FULL_HISTORY",
        "UNAUTHORIZED_DESCENDANT",
        "CHILD_COMMIT_DENIED",
        "SENSITIVE_HANDOFF",
        "RUNTIME_MODEL_MISMATCH",
        "RUNTIME_DEPTH_MISMATCH",
        "session_sha256",
        "git_status",
        "STATE_RETENTION_DAYS = 30",
        "STATE_MAX_COMPLETED = 1000",
    ):
        require(text in guard, f"route guard missing enforcement: {text}", errors)

    setup_text = (SETUP / "scripts/setup_router.py").read_text()
    for text in ("inspect_runtime", '"hooks"', '"multi_agent"', "rolled_back"):
        require(text in setup_text, f"setup missing runtime or rollback contract: {text}", errors)
    require((PLUGIN / "vendor/tomli/LICENSE").is_file(), "vendored TOML license is missing", errors)

    templates = sorted((SETUP / "assets/agents").glob("*.toml"))
    require(len(templates) == 8, "exactly eight schema-v5 templates are required", errors)
    names: set[str] = set()
    routes: set[tuple[str, str]] = set()
    for path in templates:
        text = path.read_text()
        raw = tomllib.loads(text)
        marker = MARKER.fullmatch(text.splitlines()[0])
        require(marker is not None and marker.group(1) == raw.get("name"), f"invalid schema-v5 marker: {path.name}", errors)
        require(raw.get("name") not in names, f"duplicate role: {raw.get('name')}", errors)
        names.add(raw.get("name"))
        routes.add((raw.get("model"), raw.get("model_reasoning_effort")))
        instructions = str(raw.get("developer_instructions", ""))
        for expected in ("remain a leaf", "Do not delegate or spawn subagents"):
            require(expected in instructions, f"role delegation contract missing {expected}: {path.name}", errors)
        require(
            "Router-Result" in instructions or "Router-Review" in instructions,
            f"role result footer contract missing: {path.name}",
            errors,
        )
    require(routes == EXPECTED_ROUTES, "role catalog contains an unapproved model/effort combination", errors)
    require(
        not any("specialist-xhigh" in path.name or "specialist-max" in path.name for path in templates),
        "retired Sol/xhigh or Sol/max templates remain bundled",
        errors,
    )

    for name in (
        "routing-policy.md",
        "model-effort-research.md",
        "runtime-evidence.md",
        "migration-v0.4.md",
    ):
        require((ROUTE / "references" / name).is_file(), f"missing v0.4 reference: {name}", errors)
    require((ROOT / "docs/release-v0.4.0-plan.md").is_file(), "release plan is missing", errors)
    require((ROOT / "docs/catalog-v0.4.1.md").is_file(), "v0.4.1 catalog decision is missing", errors)
    return errors


def main() -> int:
    if sys.version_info < (3, 9):
        print("ERROR: Python 3.9 or newer is required", file=sys.stderr)
        return 1
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("repository contracts: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
