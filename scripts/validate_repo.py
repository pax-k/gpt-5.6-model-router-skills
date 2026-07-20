#!/usr/bin/env python3
"""Validate repository-owned marketplace, plugin, skill, and schema-2 agent contracts."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "gpt-5-6-model-router"
SKILLS = ("setup-gpt56-model-router", "route-gpt56-task")
AGENT_DIR = PLUGIN / "skills" / "setup-gpt56-model-router" / "assets" / "agents"
ROUTE_REFS = PLUGIN / "skills" / "route-gpt56-task" / "references"
EXPECTED_AGENT_COUNT = 10
MANAGED_MARKER = re.compile(
    r"^# Managed by gpt-5-6-model-router; agent=([a-z0-9_]+); schema=2$"
)
VERSION = re.compile(r"^0\.2\.2\+codex\.20260720\d{6}$")
VALID_MODELS = {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"}
VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate() -> list[str]:
    errors: list[str] = []
    marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())

    require(marketplace.get("name") == "gpt-5-6-model-router-skills", "wrong marketplace name", errors)
    entries = marketplace.get("plugins", [])
    require(len(entries) == 1, "marketplace must contain exactly one plugin", errors)
    if entries:
        require(entries[0].get("name") == manifest.get("name"), "marketplace and manifest names differ", errors)
        require(entries[0].get("source", {}).get("path") == "./plugins/gpt-5-6-model-router", "wrong plugin source path", errors)

    require(manifest.get("name") == PLUGIN.name, "manifest name must match plugin directory", errors)
    require(bool(VERSION.fullmatch(manifest.get("version", ""))), "manifest must use a fresh v0.2.2 codex cachebuster", errors)
    require(manifest.get("skills") == "./skills/", "manifest must expose skills", errors)
    require("hooks" not in manifest and "apps" not in manifest and "mcpServers" not in manifest, "plugin must not declare hooks, apps, or MCP servers", errors)
    author = manifest.get("author", {})
    require(author.get("name") == "Pax Dynamics", "manifest publisher name is missing", errors)
    require(author.get("email") == "hello@paxdynamics.com", "manifest support email is missing", errors)
    require(manifest.get("repository") == "https://github.com/pax-k/gpt-5.6-model-router-skills", "manifest repository URL is wrong", errors)
    interface = manifest.get("interface", {})
    for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        require(str(interface.get(field, "")).startswith("https://paxdynamics.com/"), f"manifest publication URL is missing: {field}", errors)
    logo = PLUGIN / str(interface.get("logo", "")).removeprefix("./")
    require(logo.is_file(), "manifest logo is missing", errors)
    composer_icon = PLUGIN / str(interface.get("composerIcon", "")).removeprefix("./")
    require(composer_icon.is_file(), "manifest composer icon is missing", errors)
    require("brandColor" not in interface, "live portal rejects interface.brandColor", errors)

    for skill_name in SKILLS:
        skill_root = PLUGIN / "skills" / skill_name
        skill_text = (skill_root / "SKILL.md").read_text()
        metadata = (skill_root / "agents" / "openai.yaml").read_text()
        require(skill_text.startswith(f"---\nname: {skill_name}\n"), f"invalid skill frontmatter: {skill_name}", errors)
        require("allow_implicit_invocation: false" in metadata, f"implicit invocation must be disabled: {skill_name}", errors)
        require(f"${skill_name}" in metadata, f"default prompt must name skill: {skill_name}", errors)

    router_skill = (PLUGIN / "skills" / "route-gpt56-task" / "SKILL.md").read_text()
    for expected in ("autonomous execution within the requested scope", "re-enter", "route_task.py\" decide", "orchestrate.py", "build_spawn_prompt.py", "inspect_spawn.py", "fork_turns: \"none\"", "runtime evidence"):
        require(expected in router_skill, f"router skill missing v0.2 contract text: {expected}", errors)

    reference_statuses = {
        "model-effort-research.md": "Status: Implemented",
        "routing-policy.md": "Status: Implemented",
        "protocol-schemas.md": "Status: Implemented",
        "orchestration-workflows.md": "Status: Implemented",
        "open-design-decisions.md": "Status: Resolved and implemented",
        "migration-v0.2.md": "Status: Implemented",
        "runtime-evidence.md": "Status: Implemented",
    }
    for filename, status in reference_statuses.items():
        path = ROUTE_REFS / filename
        require(path.is_file(), f"missing v0.2 reference: {filename}", errors)
        if path.is_file():
            require(status in path.read_text(), f"reference not marked implemented: {filename}", errors)

    paths = sorted(AGENT_DIR.glob("gpt56-router-*.toml"))
    require(len(paths) == EXPECTED_AGENT_COUNT, "agent inventory must contain exactly ten schema-2 templates", errors)
    found_agents: set[str] = set()
    for path in paths:
        raw = path.read_bytes()
        try:
            parsed = tomllib.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            errors.append(f"invalid TOML template {path.name}: {error}")
            continue
        first_line = raw.decode("utf-8", errors="replace").splitlines()[0] if raw else ""
        marker = MANAGED_MARKER.fullmatch(first_line)
        name = parsed.get("name")
        require(marker is not None, f"missing schema-2 managed marker: {path.name}", errors)
        require(isinstance(name, str) and name.startswith("gpt56_router_"), f"invalid agent name: {path.name}", errors)
        if marker and isinstance(name, str):
            require(marker.group(1) == name, f"managed marker and TOML name differ: {path.name}", errors)
        if isinstance(name, str):
            require(name not in found_agents, f"duplicate agent name: {name}", errors)
            found_agents.add(name)
        require(parsed.get("model") in VALID_MODELS, f"invalid model for {path.name}", errors)
        require(parsed.get("model_reasoning_effort") in VALID_EFFORTS, f"invalid effort for {path.name}", errors)
        require(bool(parsed.get("description")), f"missing description for {path.name}", errors)
        require(bool(parsed.get("developer_instructions")), f"missing instructions for {path.name}", errors)
        instructions = str(parsed.get("developer_instructions", ""))
        require("autonom" in instructions.lower(), f"missing autonomous execution instruction in {path.name}", errors)
        require("router-specific approval" in instructions, f"missing no-approval instruction in {path.name}", errors)
        require('"event":"child_complete"' not in instructions, f"obsolete child event contract in {path.name}", errors)
        for field in ("event_type", "task_id", "node_id", "agent_path", "discovered_work", "write_scopes", "review"):
            require(field in instructions, f"missing canonical child event field {field} in {path.name}", errors)

    require(len(found_agents) == EXPECTED_AGENT_COUNT, "schema-2 agent names must be unique", errors)
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
