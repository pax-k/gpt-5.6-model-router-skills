#!/usr/bin/env python3
"""Validate hook-bearing listing, reviewer tests, policy, and package hygiene."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins/gpt-5-6-model-router"
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
    manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
    listing = json.loads((SUBMISSION / "portal-fields.json").read_text())
    reviewer = json.loads((SUBMISSION / "reviewer-tests.json").read_text())

    for name in (
        "README.md",
        "portal-fields.json",
        "reviewer-tests.json",
        "release-notes.md",
        "policy-attestations.md",
        "availability.md",
        "clean-room-checklist.md",
    ):
        require((SUBMISSION / name).is_file(), f"missing submission document: {name}", errors)

    require(listing.get("plugin_type") == "skills_only", "listing must identify the portal skills package type", errors)
    disclosure = listing.get("bundled_hooks")
    require(isinstance(disclosure, dict) and disclosure.get("included") is True, "listing must disclose bundled hooks", errors)
    require(disclosure.get("trust_required") is True, "listing must disclose hook trust", errors)
    require(listing.get("name") == manifest.get("interface", {}).get("displayName"), "listing and manifest names differ", errors)
    require(listing.get("release_version") == "0.4.1", "listing release version must be 0.4.1", errors)
    starter = listing.get("starter_prompts", [])
    require(1 <= len(starter) <= 3, "listing must contain one to three starter prompts", errors)
    require(starter == manifest.get("interface", {}).get("defaultPrompt"), "listing and manifest starter prompts differ", errors)
    for prompt in starter:
        require(isinstance(prompt, str) and prompt.startswith("$"), "starter prompts must explicitly invoke a skill", errors)
        require(len(prompt) <= 128, "starter prompt exceeds portal limit", errors)

    interface = manifest.get("interface", {})
    for listing_key, manifest_value in {
        "website_url": interface.get("websiteURL"),
        "privacy_policy_url": interface.get("privacyPolicyURL"),
        "terms_of_service_url": interface.get("termsOfServiceURL"),
        "repository_url": manifest.get("repository"),
    }.items():
        listing_value = listing.get(listing_key)
        require(is_https_url(listing_value), f"invalid HTTPS listing URL: {listing_key}", errors)
        require(listing_value == manifest_value, f"listing and manifest URL differ: {listing_key}", errors)
    require(is_https_url(listing.get("support_url")), "invalid HTTPS support URL", errors)

    logo = PLUGIN / str(interface.get("logo", "")).removeprefix("./")
    require(logo.is_file(), "manifest logo is missing", errors)
    require(listing.get("logo_path") == str(logo.relative_to(ROOT)), "listing logo path differs", errors)
    require("brandColor" not in interface, "portal rejects interface.brandColor", errors)
    require(len(str(interface.get("shortDescription", ""))) <= 30, "manifest short description exceeds portal limit", errors)

    positive = reviewer.get("positive", [])
    negative = reviewer.get("negative", [])
    require(len(positive) == 5, "reviewer suite must contain exactly five positive cases", errors)
    require(len(negative) == 3, "reviewer suite must contain exactly three negative cases", errors)
    identifiers: set[str] = set()
    for case in [*positive, *negative]:
        require(
            set(case) == {"id", "prompt", "setup", "expected_behavior", "expected_result"},
            f"invalid reviewer case fields: {case.get('id')}",
            errors,
        )
        identifier = case.get("id")
        require(isinstance(identifier, str) and identifier not in identifiers, f"duplicate reviewer case: {identifier}", errors)
        if isinstance(identifier, str):
            identifiers.add(identifier)
        prompt = str(case.get("prompt", ""))
        if identifier == "negative-1-missing-intent":
            require(
                not prompt.startswith("$route-gpt56-task"),
                "global-enforcement negative case must omit explicit router invocation",
                errors,
            )
        else:
            require(prompt.startswith("$route-gpt56-task"), f"reviewer prompt must invoke router: {identifier}", errors)

    require(manifest.get("hooks") == "./hooks/hooks.json", "published manifest must retain bundled hooks", errors)
    require((PLUGIN / "hooks/hooks.json").is_file(), "published hook config is missing", errors)
    require(str(manifest.get("version", "")).startswith("0.4.1+codex."), "manifest is not a v0.4.1 candidate", errors)
    require((PLUGIN / "LICENSE").is_file(), "plugin package license is missing", errors)
    require((PLUGIN / "vendor/tomli/LICENSE").is_file(), "vendored dependency license is missing", errors)

    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".py", ".toml", ".yaml", ".yml", ".txt"}:
            continue
        text = path.read_text()
        for label, pattern in PRIVATE_PATTERNS.items():
            require(not pattern.search(text), f"{label} found in public plugin file: {path.relative_to(ROOT)}", errors)

    route = PLUGIN / "skills/route-gpt56-task"
    require(
        {path.name for path in (route / "schemas").glob("*.json")}
        == {
            "task-profile.schema.json",
            "route-recommendation.schema.json",
            "route-intent.schema.json",
        },
        "publication must contain the three v4 contracts",
        errors,
    )
    for path in (PLUGIN / "skills/setup-gpt56-model-router/assets/agents").glob("*.toml"):
        text = path.read_text()
        require("schema=5" in text.splitlines()[0], f"stale agent schema: {path.name}", errors)
        require('model_reasoning_effort = "ultra"' not in text, f"Ultra role is out of scope: {path.name}", errors)
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("publication contracts: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
