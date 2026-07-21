#!/usr/bin/env python3
"""Optionally build a compact spawn request for any selected bundled route."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Mapping

from router_contract import ContractError, load_json_input, load_role_inventory


CUSTOM_AGENT_LIMIT = 6000
MODEL_OVERRIDE_LIMIT = 8000
FORBIDDEN_LABELS = ("source_files", "diff", "logs", "parent_conversation", "agents_md", "repository_documentation")
DELEGATION_GRANTS = ("none", "one-level")


class UnsupportedSpawnContract(ValueError):
    """The requested route cannot be represented by the supplied spawn fields."""


def _strings(value: Any, field: str, *, required: bool = False) -> list[str]:
    if value is None and not required: return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    return value


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug: raise ValueError("task_name must contain an ASCII letter or number")
    return slug[:64]


def _fork_turns(value: Any) -> str:
    if value is None: return "none"
    if value in ("none", "all"): return value
    if isinstance(value, int) and not isinstance(value, bool) and value > 0: return str(value)
    if isinstance(value, str) and value.isdigit() and int(value) > 0: return value
    raise ValueError('fork_turns must be "none", "all", or a positive turn count')


def _selected_route(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping): raise ValueError("selected_route must be an object")
    required = {"agent", "model", "reasoning_effort", "read_only"}
    if set(value) != required: raise ValueError("selected_route must contain exactly agent, model, reasoning_effort, and read_only")
    role = load_role_inventory().get(value["agent"])
    if role is None: raise ValueError("selected_route.agent is not a bundled role")
    expected = (role.model, role.reasoning_effort, role.read_only)
    actual = (value["model"], value["reasoning_effort"], value["read_only"])
    if actual != expected: raise ValueError("selected_route does not match the bundled role")
    return dict(value)


def _validate_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"selected_route", "task_name", "objective", "references", "owned_paths", "constraints", "verification", "supported_spawn_fields", "fork_turns", "delegation_grant"}
    extra = sorted(set(payload) - allowed)
    if extra:
        if set(extra) & set(FORBIDDEN_LABELS):
            raise ValueError("pasted source, diffs, logs, parent context, AGENTS.md, and repository documentation are forbidden")
        raise ValueError(f"unsupported handoff fields: {', '.join(extra)}")
    for field in ("task_name", "objective"):
        if not isinstance(payload.get(field), str) or not payload[field].strip(): raise ValueError(f"{field} must be a non-empty string")
    result = dict(payload)
    for field in ("references", "owned_paths", "constraints", "verification"):
        result[field] = _strings(payload.get(field), field, required=field == "verification")
    result["supported_spawn_fields"] = set(_strings(payload.get("supported_spawn_fields"), "supported_spawn_fields", required=True))
    result["selected_route"] = _selected_route(payload.get("selected_route"))
    result["fork_turns"] = _fork_turns(payload.get("fork_turns"))
    result["delegation_grant"] = payload.get("delegation_grant", "none")
    if result["delegation_grant"] not in DELEGATION_GRANTS:
        raise ValueError("delegation_grant must be none or one-level")
    return result


def _message(data: Mapping[str, Any], include_role: bool) -> str:
    route = data["selected_route"]
    roles = load_role_inventory()
    lines: list[str] = []
    if include_role: lines.extend(("Role:", roles[route["agent"]].instructions, ""))
    lines.extend((
        f"Objective: {data['objective'].strip()}", "", "Canonical references:",
        *([f"- {item}" for item in data["references"]] or ["- None supplied; inspect only the owned paths."]),
        "", "Owned paths:", *([f"- {item}" for item in data["owned_paths"]] or ["- Read-only; do not edit files."]),
        "", "Essential constraints:", *[f"- {item}" for item in data["constraints"]],
        f"Delegation grant: {data['delegation_grant']}",
    ))
    if data["delegation_grant"] == "one-level":
        lines.append("- You may create useful bounded descendants; every descendant must receive Delegation grant: none and cannot delegate further.")
    else:
        lines.append("- Remain a leaf and do not delegate or spawn subagents.")
    lines.extend((
        "- Keep long command output out of the conversation; report a failing command and only its relevant tail.",
        "", "Required verification:", *[f"- {item}" for item in data["verification"]], "",
        "Return a concise normal result: outcome, changed files, validation, and blockers.",
    ))
    return "\n".join(lines).strip() + "\n"


def build_spawn_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = _validate_input(payload)
    if data["fork_turns"] == "all":
        raise UnsupportedSpawnContract(
            'routed spawns cannot use fork_turns "all"; use "none" or a positive turn count, '
            "or create an inherited full-history spawn without routing fields"
        )
    route, fields = data["selected_route"], data["supported_spawn_fields"]
    request: dict[str, Any] = {"task_name": _slug(data["task_name"]), "fork_turns": data["fork_turns"]}
    if "agent_type" in fields:
        request["agent_type"] = route["agent"]
        request["message"] = _message(data, include_role=False)
        limit = CUSTOM_AGENT_LIMIT
    elif {"model", "reasoning_effort"}.issubset(fields):
        request["model"], request["reasoning_effort"] = route["model"], route["reasoning_effort"]
        request["message"] = _message(data, include_role=True)
        limit = MODEL_OVERRIDE_LIMIT
    else:
        raise UnsupportedSpawnContract("selected route requires agent_type or both model and reasoning_effort")
    if len(request["message"]) > limit: raise ValueError(f"spawn message exceeds {limit} characters")
    return request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, metavar="PATH|-")
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
        request = build_spawn_request(load_json_input(args.input))
    except (ContractError, UnsupportedSpawnContract, ValueError) as error:
        print(f"build_spawn_prompt.py: error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(request, indent=2, sort_keys=True) if args.json else request["message"], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
