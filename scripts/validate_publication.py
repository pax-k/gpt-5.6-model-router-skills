#!/usr/bin/env python3
"""Validate public listing, reviewer tests, policies, assets, and plugin hygiene."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "gpt-5-6-model-router"
SUBMISSION = ROOT / "submission"
PRIVATE_PATTERNS = {
    "absolute macOS user path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "persisted rollout identifier": re.compile(
        r"\b019[0-9a-f]{5}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
    "GitHub token": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
    "OpenAI secret key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def validate() -> list[str]:
    errors: list[str] = []
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    listing = json.loads((SUBMISSION / "portal-fields.json").read_text())
    reviewer = json.loads((SUBMISSION / "reviewer-tests.json").read_text())

    required_docs = (
        "README.md",
        "portal-fields.json",
        "reviewer-tests.json",
        "release-notes.md",
        "policy-attestations.md",
        "availability.md",
        "clean-room-checklist.md",
    )
    for name in required_docs:
        require((SUBMISSION / name).is_file(), f"missing submission document: {name}", errors)

    require(listing.get("plugin_type") == "skills_only", "listing must identify a skills-only plugin", errors)
    require(listing.get("name") == manifest.get("interface", {}).get("displayName"), "listing and manifest display names differ", errors)
    require(listing.get("release_version") == str(manifest.get("version", "")).split("+", 1)[0], "listing release version differs from manifest base version", errors)
    require(len(listing.get("starter_prompts", [])) >= 3, "listing needs at least three starter prompts", errors)
    for prompt in listing.get("starter_prompts", []):
        require(isinstance(prompt, str) and prompt.startswith("$"), "every starter prompt must explicitly invoke a skill", errors)

    interface = manifest.get("interface", {})
    url_pairs = {
        "website_url": interface.get("websiteURL"),
        "privacy_policy_url": interface.get("privacyPolicyURL"),
        "terms_of_service_url": interface.get("termsOfServiceURL"),
        "repository_url": manifest.get("repository"),
    }
    for listing_key, manifest_value in url_pairs.items():
        listing_value = listing.get(listing_key)
        require(is_https_url(listing_value), f"invalid HTTPS listing URL: {listing_key}", errors)
        require(listing_value == manifest_value, f"listing and manifest URL differ: {listing_key}", errors)
    require(is_https_url(listing.get("support_url")), "invalid HTTPS support URL", errors)

    logo = PLUGIN / str(interface.get("logo", "")).removeprefix("./")
    require(logo.is_file(), "manifest logo is missing", errors)
    require(listing.get("logo_path") == str(logo.relative_to(ROOT)), "listing logo path differs from manifest logo", errors)
    composer_icon = PLUGIN / str(interface.get("composerIcon", "")).removeprefix("./")
    require(composer_icon.is_file(), "manifest composer icon is missing", errors)
    require("brandColor" not in interface, "live portal rejects interface.brandColor", errors)
    require(len(str(interface.get("shortDescription", ""))) <= 30, "manifest short description exceeds portal limit", errors)
    require(listing.get("short_description") == interface.get("shortDescription"), "listing and manifest short descriptions differ", errors)

    positive = reviewer.get("positive", [])
    negative = reviewer.get("negative", [])
    require(len(positive) == 7, "reviewer suite must contain exactly seven positive cases", errors)
    require(len(negative) == 1, "reviewer suite must contain exactly one negative case", errors)
    identifiers: set[str] = set()
    for case in [*positive, *negative]:
        require(set(case) == {"id", "prompt", "setup", "expected_behavior", "expected_result"}, f"invalid reviewer case fields: {case.get('id')}", errors)
        identifier = case.get("id")
        require(isinstance(identifier, str) and identifier not in identifiers, f"duplicate or invalid reviewer case id: {identifier}", errors)
        if isinstance(identifier, str):
            identifiers.add(identifier)
        require(str(case.get("prompt", "")).startswith("$route-gpt56-task"), f"reviewer prompt must explicitly invoke router: {identifier}", errors)

    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".py", ".toml", ".yaml", ".yml", ".txt"}:
            continue
        text = path.read_text()
        for label, pattern in PRIVATE_PATTERNS.items():
            require(not pattern.search(text), f"{label} found in public plugin file: {path.relative_to(ROOT)}", errors)

    require((ROOT / "LICENSE").is_file(), "MIT license file is missing", errors)
    require(manifest.get("license") == "MIT", "manifest license must be MIT", errors)
    require(str(manifest.get("version", "")).startswith("0.3.0+codex."), "manifest contains stale pre-v0.3 metadata", errors)

    route = PLUGIN / "skills" / "route-gpt56-task"
    require(not (route / "scripts" / "orchestrate.py").exists(), "publication contains forbidden orchestration CLI", errors)
    require(
        {path.name for path in (route / "schemas").glob("*.json")}
        == {"task-profile.schema.json", "route-recommendation.schema.json"},
        "publication contains removed orchestration schemas",
        errors,
    )
    setup = (PLUGIN / "skills/setup-gpt56-model-router/scripts/setup_router.py").read_text()
    require('choices=("install", "check", "uninstall")' in setup, "publication lacks unified setup", errors)
    for path in (PLUGIN / "skills/setup-gpt56-model-router/assets/agents").glob("*.toml"):
        text = path.read_text()
        require("schema=4" in text.splitlines()[0], f"stale agent schema: {path.name}", errors)
        require("Delegation grant: one-level" in text and "Delegation grant: none" in text, f"bounded delegation contract missing: {path.name}", errors)
        require("event_type" not in text and "terminal event" not in text.lower(), f"terminal-event language in role: {path.name}", errors)
        require('model_reasoning_effort = "ultra"' not in text, f"Ultra role is out of scope: {path.name}", errors)
    route_skill = (route / "SKILL.md").read_text()
    for expected in ("best expected value", "never blocks", "one-level", "no fixed count"):
        require(expected in route_skill, f"autonomy contract missing from publication: {expected}", errors)
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("publication contracts: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
