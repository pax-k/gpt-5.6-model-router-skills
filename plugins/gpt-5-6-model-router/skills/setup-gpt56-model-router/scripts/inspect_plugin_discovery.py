#!/usr/bin/env python3
"""Verify explicit router-skill discovery through Codex's plugin API."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


SCRIPT = Path(__file__).resolve()
PLUGIN = SCRIPT.parents[3]
DEFAULT_PLUGIN_NAME = "gpt-5-6-model-router"
DEFAULT_SKILLS = ("route-gpt56-task", "setup-gpt56-model-router")


def object_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def evaluate_plugin(
    plugin: Mapping[str, Any],
    *,
    expected_plugin_id: str,
    expected_version: str,
    expected_skills: Sequence[str],
) -> dict[str, Any]:
    summary = object_value(plugin.get("summary"))
    visible_skills: list[str] = []
    enabled_skills: set[str] = set()
    for raw_skill in plugin.get("skills", []):
        skill = object_value(raw_skill)
        raw_name = skill.get("name")
        if not isinstance(raw_name, str):
            continue
        name = raw_name.split(":", 1)[-1]
        visible_skills.append(name)
        if skill.get("enabled") is True:
            enabled_skills.add(name)

    failure_reasons: list[str] = []
    if summary.get("id") != expected_plugin_id:
        failure_reasons.append("plugin ID did not match expected marketplace identity")
    if summary.get("installed") is not True:
        failure_reasons.append("plugin is not installed")
    if summary.get("enabled") is not True:
        failure_reasons.append("plugin is not enabled")
    if summary.get("localVersion") != expected_version:
        failure_reasons.append("installed plugin version did not match expected version")
    for name in expected_skills:
        if name not in enabled_skills:
            failure_reasons.append(f"expected explicit skill is unavailable: {name}")

    return {
        "ok": not failure_reasons,
        "plugin_id": summary.get("id"),
        "installed": summary.get("installed"),
        "enabled": summary.get("enabled"),
        "version": summary.get("localVersion"),
        "expected_version": expected_version,
        "marketplace": plugin.get("marketplaceName"),
        "skills": sorted(visible_skills),
        "expected_skills": sorted(expected_skills),
        "failure_reasons": failure_reasons,
    }


class AppServerClient:
    def __init__(self, codex_bin: str) -> None:
        self.process = subprocess.Popen(
            [codex_bin, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.next_id = 1

    def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Codex app-server pipes are unavailable")
        request_id = self.next_id
        self.next_id += 1
        self.process.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        while True:
            line = self.process.stdout.readline()
            if not line:
                detail = ""
                if self.process.stderr is not None:
                    detail = self.process.stderr.read().strip()
                raise RuntimeError(detail or "Codex app-server exited before responding")
            message = json.loads(line)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(json.dumps(message["error"], sort_keys=True))
            return object_value(message.get("result"))

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def inspect(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    marketplace_path = args.marketplace_path.resolve()
    marketplace = json.loads(marketplace_path.read_text())
    marketplace_name = marketplace.get("name")
    if not isinstance(marketplace_name, str) or not marketplace_name:
        raise ValueError("marketplace name is missing")
    expected_version = args.expected_version
    if expected_version is None:
        expected_version = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())["version"]
    expected_skills = tuple(args.expected_skill or DEFAULT_SKILLS)
    expected_plugin_id = f"{args.plugin_name}@{marketplace_name}"

    client = AppServerClient(args.codex_bin)
    try:
        client.request(
            "initialize",
            {
                "clientInfo": {"name": "gpt56-plugin-discovery-inspector", "version": "1.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        response = client.request(
            "plugin/read",
            {"pluginName": args.plugin_name, "marketplacePath": str(marketplace_path)},
        )
    finally:
        client.close()

    result = evaluate_plugin(
        object_value(response.get("plugin")),
        expected_plugin_id=expected_plugin_id,
        expected_version=str(expected_version),
        expected_skills=expected_skills,
    )
    result["marketplace_path"] = str(marketplace_path)
    return result, 0 if result["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marketplace-path", required=True, type=Path)
    parser.add_argument("--plugin-name", default=DEFAULT_PLUGIN_NAME)
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-skill", action="append")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result, exit_code = inspect(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        result = {"ok": False, "failure_reasons": [str(error)]}
        exit_code = 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print(f"plugin discovery: ok ({result['plugin_id']} {result['version']})")
    else:
        for reason in result["failure_reasons"]:
            print(f"ERROR: {reason}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
