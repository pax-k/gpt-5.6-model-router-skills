#!/usr/bin/env python3
"""Make a validated, structured GPT-5.6 route decision."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import PurePosixPath
from typing import Any, Mapping

try:
    from router_contract import (
        ContractError,
        Role,
        load_json_input,
        load_role_inventory,
        validate_route_decision,
        validate_task_profile,
    )
except ModuleNotFoundError:  # Loaded by path in repository tests.
    import importlib.util
    from pathlib import Path

    _contract_path = Path(__file__).with_name("router_contract.py")
    _spec = importlib.util.spec_from_file_location("router_contract", _contract_path)
    assert _spec and _spec.loader
    _contract = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _contract
    _spec.loader.exec_module(_contract)
    ContractError = _contract.ContractError
    Role = _contract.Role
    load_json_input = _contract.load_json_input
    load_role_inventory = _contract.load_role_inventory
    validate_route_decision = _contract.validate_route_decision
    validate_task_profile = _contract.validate_task_profile


BASE_ROUTES = {
    "mechanical": "gpt56_router_luna_worker",
    "exploration": "gpt56_router_terra_explorer",
    "implementation": "gpt56_router_terra_worker",
    "ambiguous": "gpt56_router_sol_engineer",
    "debugging": "gpt56_router_sol_debugger",
    "review": "gpt56_router_sol_reviewer",
}
REVIEW_AGENT = "gpt56_router_sol_reviewer"
ADVISOR_AGENT = "gpt56_router_sol_advisor"
CONSEQUENTIAL_DOMAINS = frozenset({
    "authentication", "authorization", "secrets", "credentials", "payments",
    "financial_state", "personal_data", "regulated_data", "destructive_migration",
    "lossy_migration", "concurrency", "distributed_state", "public_api", "schema",
    "compatibility", "safety", "critical_business_logic",
})
SOL_HIGH_DOMAINS = frozenset({"security", "concurrency", "distributed_state"})


def _rating(profile: Mapping[str, Any], name: str) -> int:
    value = profile["dimensions"][name]
    return value["rating"] if isinstance(value, Mapping) else int(value)


def _domains(profile: Mapping[str, Any]) -> set[str]:
    return {str(value).strip().lower().replace("-", "_").replace(" ", "_") for value in profile.get("risk_domains", [])}


def _failed_attempt(profile: Mapping[str, Any], model_fragment: str, effort: str) -> bool:
    for attempt in profile.get("prior_attempts", []):
        outcome = str(attempt.get("outcome", "")).lower()
        if model_fragment in str(attempt.get("model", "")).lower() and attempt.get("effort") == effort and any(word in outcome for word in ("fail", "incorrect", "incomplete", "rejected")) and str(attempt.get("evidence", "")).strip():
            return True
    return False


def _route(role: Role, effort: str | None = None) -> dict[str, Any]:
    return {
        "agent": role.name,
        "model": role.model,
        "reasoning_effort": effort or role.reasoning_effort,
        "read_only": role.read_only,
    }


def _runtime_mode(profile: Mapping[str, Any], role: Role) -> str:
    runtime = profile.get("runtime_capabilities")
    if not isinstance(runtime, Mapping):
        return "unsupported"
    available_agents = runtime.get("available_agents")
    available_models = runtime.get("available_models")
    agent_available = not isinstance(available_agents, list) or role.name in available_agents
    model_available = not isinstance(available_models, list) or role.model in available_models
    if runtime.get("agent_type") and agent_available:
        return "custom_agent"
    if runtime.get("model_override") and model_available:
        return "model_override"
    return "unsupported"


def _delegation_capability(profile: Mapping[str, Any], role: Role | None) -> dict[str, Any]:
    request = profile["delegation_request"]
    allowed_roles = list(request.get("allowed_roles", []))
    authorize = bool(request.get("authorize_descendants", False))
    remaining_depth = max(0, 2 - int(profile["depth"]) - 1)
    roles = load_role_inventory()
    may_spawn_writers = bool(request.get("may_spawn_writers", False))
    contains_writer = any(name in roles and not roles[name].read_only for name in allowed_roles)
    allowed = bool(
        role and role.may_delegate and authorize and remaining_depth and allowed_roles
        and not (contains_writer and not may_spawn_writers)
    )
    max_children = min(3, int(request.get("max_children", 3))) if allowed else 0
    max_parallel = min(2, max_children, int(request.get("max_parallel_children", 2))) if allowed else 0
    allowed_models = list(dict.fromkeys(roles[name].model for name in allowed_roles if name in roles)) if allowed else []
    return {
        "schema_version": 1,
        "allowed": allowed,
        "remaining_depth": remaining_depth if allowed else 0,
        "max_children": max_children,
        "max_parallel_children": max_parallel,
        "allowed_roles": allowed_roles if allowed else [],
        "allowed_models": allowed_models,
        "allowed_write_scopes": list(request.get("allowed_write_scopes", [])) if allowed else [],
        "may_spawn_writers": may_spawn_writers if allowed else False,
        # The explicit router invocation is autonomous within the authority
        # recorded by the root task profile. Do not invent a second, hidden
        # deny-list here: callers can still attenuate a descendant explicitly.
        "forbidden_actions": list(request.get("forbidden_actions", [])),
        "required_return": list(request.get("required_return", ["child-runtime-evidence", "child-results", "undispatched-work"])),
    }


def _select_primary(profile: Mapping[str, Any], roles: Mapping[str, Role]) -> tuple[dict[str, Any], list[str]]:
    kind = profile["kind"]
    ambiguity = _rating(profile, "ambiguity")
    consequence = _rating(profile, "consequence")
    breadth = _rating(profile, "context_breadth")
    irreversibility = _rating(profile, "irreversibility")
    verification = _rating(profile, "verification_strength")
    domains = _domains(profile)
    reasons = [f"KIND_{kind.upper()}"]

    severe = (
        consequence == 3
        or irreversibility == 3
        or (verification <= 1 and consequence >= 2)
        or bool(domains & SOL_HIGH_DOMAINS)
    )
    sol_gate = (
        severe
        or ambiguity == 3
        or (breadth >= 2 and bool(domains & {"migration", "compatibility", "security", "concurrency", "distributed_state", "architecture"}))
    )
    # Review authority is read-only: risk raises the reviewer to Sol/high, but
    # must never turn the review into a writable implementation/debug route.
    if kind == "review":
        agent, effort = REVIEW_AGENT, "high"
        if severe:
            reasons.append("SOL_HIGH_RISK_GATE")
    elif severe:
        reasons.append("SOL_HIGH_RISK_GATE")
        agent, effort = "gpt56_router_sol_debugger", "high"
    elif sol_gate:
        reasons.append("SOL_CAPABILITY_GATE")
        agent, effort = "gpt56_router_sol_debugger" if kind == "debugging" else "gpt56_router_sol_engineer", "medium"
    else:
        agent, effort = BASE_ROUTES[kind], roles[BASE_ROUTES[kind]].reasoning_effort

    luna_ineligible = (
        agent == "gpt56_router_luna_worker"
        and (ambiguity >= 2 or consequence >= 2 or breadth >= 2 or irreversibility >= 2 or verification <= 1 or bool(domains))
    )
    if luna_ineligible:
        agent, effort = "gpt56_router_terra_worker", "medium"
        reasons.append("LUNA_LOW_ELIGIBILITY_EXCEEDED")

    if agent == "gpt56_router_luna_worker" and _failed_attempt(profile, "luna", "low"):
        agent, effort = "gpt56_router_terra_worker", "medium"
        reasons.append("ESCALATE_LUNA_LOW_TO_TERRA_MEDIUM")
    elif agent == "gpt56_router_terra_worker" and _failed_attempt(profile, "terra", "medium"):
        agent, effort = "gpt56_router_sol_engineer", "medium"
        reasons.append("ESCALATE_TERRA_MEDIUM_TO_SOL_MEDIUM")
    elif agent == "gpt56_router_sol_engineer" and _failed_attempt(profile, "sol", "medium"):
        agent, effort = "gpt56_router_sol_debugger", "high"
        reasons.append("ESCALATE_SOL_MEDIUM_TO_SOL_HIGH")

    # Advanced routes are deliberately gated by recorded evidence or authority.
    quality_first = bool(profile["human_authority"].get("quality_first"))
    sol_xhigh_failed = _failed_attempt(profile, "sol", "xhigh")
    sol_high_failed = _failed_attempt(profile, "sol", "high")
    improved_verifier = verification >= 2
    bounded = breadth <= 2
    terra_medium_failed = _failed_attempt(profile, "terra", "medium")
    broad_investigation = kind == "exploration" and breadth >= 2

    if kind != "review" and agent.startswith("gpt56_router_sol") and (quality_first or sol_xhigh_failed):
        agent, effort = "gpt56_router_sol_specialist_max", "max"
        reasons.append("SOL_MAX_QUALITY_FIRST_AUTHORITY" if quality_first else "SOL_MAX_AFTER_XHIGH_FAILURE")
    elif kind != "review" and agent.startswith("gpt56_router_sol") and sol_high_failed and bounded and improved_verifier:
        agent, effort = "gpt56_router_sol_specialist_xhigh", "xhigh"
        reasons.append("SOL_XHIGH_AFTER_HIGH_FAILURE")
    elif agent.startswith("gpt56_router_terra") and (broad_investigation or terra_medium_failed):
        agent, effort = "gpt56_router_terra_investigator", "high"
        reasons.append("TERRA_HIGH_BROAD_INVESTIGATION" if broad_investigation else "TERRA_HIGH_AFTER_MEDIUM_FAILURE")

    return _route(roles[agent], effort), reasons


def decide(profile_payload: Any) -> dict[str, Any]:
    """Validate a task profile and return a validated route decision."""
    profile = validate_task_profile(profile_payload)
    roles = load_role_inventory()
    primary, reasons = _select_primary(profile, roles)
    domains = _domains(profile)
    writes = bool(profile["write_scopes"]) and not profile.get("read_only", False)
    consequential = bool(domains & CONSEQUENTIAL_DOMAINS)
    review_required = consequential and primary["agent"] != REVIEW_AGENT
    if consequential:
        reasons.append("CONSEQUENTIAL_RISK_DOMAIN")
    if review_required:
        reasons.append("INDEPENDENT_REVIEW_REQUIRED")

    orchestrator_model = str(profile["orchestrator"]["model"]).lower()
    below_sol = "sol" not in orchestrator_model
    ambiguous_write = writes and (profile["kind"] == "ambiguous" or _rating(profile, "ambiguity") >= 2)
    advisory_required = below_sol and writes and (ambiguous_write or consequential)
    if advisory_required:
        reasons.append("SOL_ADVISORY_BEFORE_IMPLEMENTATION")

    requested = profile["delegation_request"]["requested"]
    selected_role = roles[primary["agent"]]
    routing_mode = _runtime_mode(profile, selected_role)
    if not requested:
        decision = "direct_execution"
        routing_mode = "direct"
        primary_output = None
        reasons.append("DELEGATION_NOT_REQUESTED")
    elif routing_mode == "unsupported":
        decision = "unsupported"
        primary_output = None
        runtime = profile.get("runtime_capabilities", {})
        if isinstance(runtime, Mapping) and isinstance(runtime.get("available_models"), list) and selected_role.model not in runtime["available_models"]:
            reasons.append("MODEL_UNAVAILABLE")
        if isinstance(runtime, Mapping) and isinstance(runtime.get("available_agents"), list) and selected_role.name not in runtime["available_agents"]:
            reasons.append("AGENT_UNAVAILABLE")
        reasons.append("NO_ENFORCEABLE_ROUTE")
    else:
        decision = "delegate"
        primary_output = primary

    advisor = roles.get(ADVISOR_AGENT)
    if advisory_required and advisor is None:
        # Fail closed until the setup inventory carries the canonical advisor.
        decision = "unsupported"
        routing_mode = "unsupported"
        primary_output = None
        reasons.append("ADVISOR_ROLE_UNAVAILABLE")
    elif advisory_required and advisor is not None and _runtime_mode(profile, advisor) == "unsupported":
        decision = "unsupported"
        routing_mode = "unsupported"
        primary_output = None
        reasons.append("ADVISOR_ROUTE_UNAVAILABLE")

    result = {
        "schema_version": 1,
        **(
            {"task_id": profile["task_id"], "node_id": profile.get("node_id", profile["task_id"])}
            if "task_id" in profile
            else {}
        ),
        "decision": decision,
        "routing_mode": routing_mode,
        "primary": primary_output,
        "review": {"required": review_required, "route": _route(roles[REVIEW_AGENT]) if review_required else None},
        "advisory": {"required": advisory_required, "route": _route(advisor) if advisory_required and advisor else None},
        "delegation_capability": _delegation_capability(profile, selected_role if decision == "delegate" else None),
        "parallel_eligibility": {
            "eligible": bool(profile.get("read_only", False) or profile["write_scopes"]),
            "requires_disjoint_peers": not bool(profile.get("read_only", False)),
            "reason_code": "READ_ONLY_PARALLEL_SAFE" if profile.get("read_only", False) else ("KNOWN_WRITE_SCOPE_REQUIRES_DISJOINT_PEERS" if profile["write_scopes"] else "UNKNOWN_WRITE_SCOPE_SERIALIZE"),
        },
        "reason_codes": list(dict.fromkeys(reasons)),
    }
    return validate_route_decision(result)


def normalize_scope(scope: str) -> PurePosixPath:
    return PurePosixPath(scope.replace("\\", "/").rstrip("/") or "/")


def scopes_overlap(left: str, right: str) -> bool:
    left_path, right_path = normalize_scope(left), normalize_scope(right)
    return left_path == right_path or left_path in right_path.parents or right_path in left_path.parents


def may_parallelize(write_scope_groups: list[list[str]], read_only: list[bool] | None = None) -> bool:
    """Unknown/empty writer scopes are unsafe; explicitly read-only work is safe."""
    flags = read_only or [False] * len(write_scope_groups)
    if len(flags) != len(write_scope_groups):
        raise ValueError("read_only must have one entry per scope group")
    for index, group in enumerate(write_scope_groups):
        if not group and not flags[index]:
            return False
    writers = [(index, group) for index, group in enumerate(write_scope_groups) if not flags[index]]
    for position, (_, left_group) in enumerate(writers):
        for _, right_group in writers[position + 1:]:
            if any(scopes_overlap(left, right) for left in left_group for right in right_group):
                return False
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    legacy = [flag for flag in ("--kind", "--consequential", "--prior-validation-failure") if flag in argv]
    if legacy:
        raise ContractError(f"legacy flag(s) no longer supported: {', '.join(legacy)}; pass a task profile with --input path|- instead")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    decide_command = commands.add_parser("decide", help="validate a task profile and emit a route decision")
    decide_command.add_argument("--input", required=True, metavar="PATH|-", help="task-profile JSON file, or - for stdin")
    decide_command.add_argument("--json", action="store_true", help="emit the complete route-decision JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        decision = decide(load_json_input(args.input))
    except ContractError as error:
        print(f"route_task.py: error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(decision, indent=2, sort_keys=True))
    else:
        if decision["primary"]:
            primary = decision["primary"]
            print(f"{decision['decision']}: {primary['agent']} ({primary['model']}/{primary['reasoning_effort']})")
        else:
            print(decision["decision"])
        print(", ".join(decision["reason_codes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
