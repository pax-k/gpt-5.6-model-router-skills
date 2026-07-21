#!/usr/bin/env python3
"""Validate the routing-only v0.3 repository contract."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "gpt-5-6-model-router"
ROUTE = PLUGIN / "skills" / "route-gpt56-task"
SETUP = PLUGIN / "skills" / "setup-gpt56-model-router"
VERSION = re.compile(r"^0\.3\.0\+codex\.20260721\d{6}$")
MARKER = re.compile(r"^# Managed by gpt-5-6-model-router; agent=([a-z0-9_]+); schema=4$")


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate() -> list[str]:
    errors: list[str] = []
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    require(bool(VERSION.fullmatch(manifest.get("version", ""))), "manifest must use a fresh v0.3.0 cachebuster", errors)
    require(marketplace["plugins"][0]["name"] == manifest["name"], "marketplace and manifest names differ", errors)
    require(manifest.get("skills") == "./skills/", "manifest must expose skills", errors)
    require(not any(key in manifest for key in ("hooks", "apps", "mcpServers")), "plugin must remain skills-only", errors)

    for skill_name in ("route-gpt56-task", "setup-gpt56-model-router"):
        root = PLUGIN / "skills" / skill_name
        skill = (root / "SKILL.md").read_text()
        metadata = (root / "agents/openai.yaml").read_text()
        require(skill.startswith(f"---\nname: {skill_name}\n"), f"invalid frontmatter: {skill_name}", errors)
        require(f"${skill_name}" in metadata and "allow_implicit_invocation: false" in metadata, f"invalid metadata: {skill_name}", errors)

    scripts = ROUTE / "scripts"
    schemas = ROUTE / "schemas"
    require(not (scripts / "orchestrate.py").exists(), "orchestrate.py is forbidden in v0.3", errors)
    require({path.name for path in schemas.glob("*.json")} == {"task-profile.schema.json", "route-recommendation.schema.json"}, "only the two schema-v3 advisory schemas may remain", errors)
    route_skill = (ROUTE / "SKILL.md").read_text()
    for text in ('fork_turns: "none"', "best expected value", "may override every", "one-level", "never blocks", "no fixed count", "optional helpers"):
        require(text.lower() in route_skill.lower(), f"route skill missing autonomy contract: {text}", errors)
    runtime_evidence = (ROUTE / "references/runtime-evidence.md").read_text()
    for text in (
        "inspect_plugin_discovery.py", "plugin/read", "allow_implicit_invocation: false",
        "absence from the ambient model skill catalog is therefore expected",
        "--task-name", "--parent-thread-id", "--expected-fork-turns none", "matching parent",
    ):
        require(text in runtime_evidence, f"runtime evidence missing persisted fork proof: {text}", errors)
    discovery_inspector = SETUP / "scripts/inspect_plugin_discovery.py"
    require(discovery_inspector.is_file(), "plugin discovery inspector is missing", errors)
    if discovery_inspector.is_file():
        discovery_text = discovery_inspector.read_text()
        for text in ("plugin/read", "route-gpt56-task", "setup-gpt56-model-router"):
            require(text in discovery_text, f"plugin discovery inspector missing contract: {text}", errors)
    for forbidden in ("delegation capability", "task graph", "task ledger", "terminal JSON"):
        require(forbidden not in route_skill, f"route skill contains stale orchestration contract: {forbidden}", errors)

    setup = (SETUP / "scripts/setup_router.py").read_text()
    require('choices=("install", "check", "uninstall")' in setup, "unified setup CLI is missing", errors)
    require("manage_depth" in setup and "rolled_back" in setup, "setup must coordinate depth with rollback", errors)

    templates = sorted((SETUP / "assets/agents").glob("*.toml"))
    require(len(templates) == 10, "exactly ten schema-4 templates are required", errors)
    names: set[str] = set()
    for path in templates:
        text = path.read_text()
        raw = tomllib.loads(text)
        marker = MARKER.fullmatch(text.splitlines()[0])
        require(marker is not None and marker.group(1) == raw.get("name"), f"invalid schema-4 marker: {path.name}", errors)
        require(raw.get("name") not in names, f"duplicate role: {raw.get('name')}", errors)
        names.add(raw.get("name"))
        instructions = str(raw.get("developer_instructions", ""))
        for grant in ("Delegation grant: one-level", "Delegation grant: none", "cannot delegate further"):
            require(grant in instructions, f"role delegation contract missing {grant}: {path.name}", errors)
        for forbidden in ("terminal", "event_type", "delegation capability", "task_id", "agent_path"):
            require(forbidden not in instructions, f"stale role instruction {forbidden}: {path.name}", errors)

    for removed in ("protocol-schemas.md", "orchestration-workflows.md", "open-design-decisions.md", "migration-v0.2.md"):
        require(not (ROUTE / "references" / removed).exists(), f"removed v0.2 reference remains: {removed}", errors)
    require((ROUTE / "references/migration-v0.3.md").is_file(), "migration-v0.3.md is missing", errors)
    for path in schemas.glob("*.json"):
        require("ultra" not in path.read_text(), f"Ultra is out of scope but appears in {path.name}", errors)
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("repository contracts: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
