#!/usr/bin/env python3
"""Recommend one governed GPT-5.6 route using pure schema-v4 policy."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Mapping

if sys.version_info < (3, 9):
    print("GPT-5.6 Model Router requires Python 3.9 or newer", file=sys.stderr)
    raise SystemExit(2)

from router_contract import (
    ContractError,
    Role,
    canonical_sha256,
    load_json_input,
    load_role_inventory,
    validate_route_recommendation,
    validate_task_profile,
)


ROLES = {
    "luna": "gpt56_router_luna_worker",
    "terra_explorer": "gpt56_router_terra_explorer",
    "terra_worker": "gpt56_router_terra_worker",
    "terra_high": "gpt56_router_terra_investigator",
    "sol_engineer": "gpt56_router_sol_engineer",
    "sol_debugger": "gpt56_router_sol_debugger",
    "sol_reviewer": "gpt56_router_sol_reviewer",
    "sol_advisor": "gpt56_router_sol_advisor",
    "sol_xhigh": "gpt56_router_sol_specialist_xhigh",
    "sol_max": "gpt56_router_sol_specialist_max",
}
CRITICAL_DOMAINS = frozenset(
    {
        "security",
        "authentication",
        "authorization",
        "secrets",
        "credentials",
        "payments",
        "financial_mutations",
        "financial_state",
        "destructive_migrations",
        "destructive_migration",
        "concurrency",
        "distributed_state",
        "safety",
    }
)


def _domains(profile: Mapping[str, Any]) -> set[str]:
    return {str(value).strip().lower().replace("-", "_").replace(" ", "_") for value in profile["risk_domains"]}


def _route(role: Role) -> dict[str, Any]:
    return {
        "agent": role.name,
        "model": role.model,
        "reasoning_effort": role.reasoning_effort,
        "read_only": role.read_only,
    }


def _failed(profile: Mapping[str, Any], model: str, effort: str) -> bool:
    failure = profile.get("prior_route_failure")
    return bool(
        isinstance(failure, Mapping)
        and model in str(failure.get("model", "")).lower()
        and failure.get("effort") == effort
    )


def _select(profile: Mapping[str, Any]) -> tuple[str, list[str], bool]:
    kind = profile["kind"]
    ambiguity = profile["ambiguity"]
    breadth = profile["context_breadth"]
    verification = profile["verification_strength"]
    critical = bool(_domains(profile) & CRITICAL_DOMAINS)
    reasons = [f"KIND_{kind.upper()}"]
    if kind == "mechanical":
        key = "luna" if ambiguity <= 1 and breadth <= 1 and verification >= 2 and not critical else "terra_worker"
        if key != "luna":
            reasons.append("LUNA_ELIGIBILITY_EXCEEDED")
    elif kind == "exploration":
        key = "terra_high" if breadth >= 2 and ambiguity >= 2 else "terra_explorer"
        if key == "terra_high":
            reasons.append("BROAD_COMPETING_HYPOTHESES")
        elif breadth >= 2:
            reasons.append("BROAD_CONTEXT_TERRA")
    elif kind == "implementation":
        key = "sol_engineer" if critical or ambiguity >= 2 else "terra_worker"
        if breadth >= 3 and key == "terra_worker":
            reasons.append("BROAD_CONTEXT_TERRA")
        if ambiguity >= 2:
            reasons.append("AMBIGUITY_REQUIRES_SOL")
    elif kind == "ambiguous":
        key = "sol_engineer"
    elif kind == "debugging":
        key = "sol_debugger"
    elif kind == "review":
        key = "sol_reviewer"
    else:
        key = "sol_advisor"

    if critical and kind not in ("review", "advisory"):
        reasons.append("CRITICAL_RISK_FLOOR")
        key = "sol_debugger" if verification <= 1 or kind == "debugging" else "sol_engineer"
        if verification <= 1:
            reasons.append("WEAK_CRITICAL_VERIFICATION")
    if _failed(profile, "luna", "low"):
        key, reasons = "terra_worker", reasons + ["ESCALATE_LUNA_LOW"]
    elif _failed(profile, "terra", "medium"):
        key, reasons = "sol_engineer", reasons + ["ESCALATE_TERRA_MEDIUM"]
    elif _failed(profile, "sol", "medium"):
        key, reasons = "sol_debugger", reasons + ["ESCALATE_SOL_MEDIUM"]
    elif _failed(profile, "sol", "high"):
        key, reasons = "sol_xhigh", reasons + ["ESCALATE_SOL_HIGH"]
    elif _failed(profile, "sol", "xhigh"):
        key, reasons = "sol_max", reasons + ["ESCALATE_SOL_XHIGH"]
    if profile["quality_mode"]["level"] == "quality_first" and kind not in ("review", "advisory"):
        key, reasons = "sol_max", reasons + ["QUALITY_FIRST"]
    return key, reasons, critical


def _availability(profile: Mapping[str, Any], role: Role) -> str:
    runtime = profile.get("runtime_capabilities")
    if runtime is None:
        return "unknown"
    if runtime["custom_agent"] and role.name in runtime["available_agents"]:
        return "custom_agent"
    if runtime["model_override"] and role.model in runtime["available_models"]:
        return "model_override"
    return "unavailable"


def recommend(payload: Any) -> dict[str, Any]:
    profile = validate_task_profile(payload)
    roles = load_role_inventory()
    key, reasons, critical = _select(profile)
    role = roles[ROLES[key]]
    availability = _availability(profile, role)
    if availability == "unavailable":
        reasons.append("PREFERRED_ROUTE_UNAVAILABLE")
    elif availability == "unknown":
        reasons.append("RUNTIME_AVAILABILITY_UNKNOWN")
    review_required = critical and profile["kind"] not in ("review", "advisory")
    reviewer = roles[ROLES["sol_reviewer"]]
    if review_required:
        reasons.append("CRITICAL_REVIEW_REQUIRED")
    result = {
        "schema_version": 4,
        "profile_sha256": canonical_sha256(profile),
        "preferred_route": _route(role),
        "availability": availability,
        "constraints": {
            "critical": critical,
            "minimum_model": "gpt-5.6-sol" if critical else None,
            "minimum_effort": "medium" if critical else None,
        },
        "review": {
            "required": review_required,
            "preferred_reviewer": _route(reviewer) if review_required else None,
        },
        "reason_codes": list(dict.fromkeys(reasons)),
    }
    return validate_route_recommendation(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("recommend")
    command.add_argument("--input", required=True, metavar="PATH|-")
    command.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
        recommendation = recommend(load_json_input(args.input))
    except ContractError as error:
        print(f"route_task.py: error: {error}", file=sys.stderr)
        return 2
    route = recommendation["preferred_route"]
    print(
        json.dumps(recommendation, indent=2, sort_keys=True)
        if args.json
        else f"prefer {route['agent']} ({route['model']}/{route['reasoning_effort']}), "
        f"availability={recommendation['availability']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
