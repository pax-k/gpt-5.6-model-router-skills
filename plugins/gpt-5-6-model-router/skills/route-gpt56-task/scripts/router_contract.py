#!/usr/bin/env python3
"""Canonical protocol contract for the GPT-5.6 model router.

The module deliberately uses only the Python standard library.  The JSON
schemas are distribution artifacts; these validators provide the same useful
boundary when jsonschema is not installed.
"""

from __future__ import annotations

import json
import re
import tomllib
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


SCHEMA_VERSION = 1
KINDS = ("mechanical", "exploration", "implementation", "ambiguous", "debugging", "review")
PHASES = ("intake", "exploration", "implementation", "validation", "repair", "review")
EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")
DECISIONS = ("direct_execution", "delegate", "ask_human", "wait", "unsupported")
ROUTING_MODES = ("custom_agent", "model_override", "unsupported", "direct")
EVENTS = (
    "progress", "complete", "partial", "new_work", "needs_decision",
    "approval_required", "risk_discovered", "validation_failed", "blocked",
    "conflict", "budget_exhausted", "cancelled", "failed",
)
TERMINAL_EVENTS = frozenset(EVENTS) - {"progress"}
NODE_STATUSES = (
    "queued", "ready", "running", "waiting", "blocked", "review", "repair",
    "complete", "partial", "failed", "cancelled",
)


class ContractError(ValueError):
    """A payload does not satisfy a router protocol contract."""


@dataclass(frozen=True)
class Role:
    name: str
    description: str
    model: str
    reasoning_effort: str
    instructions: str
    read_only: bool
    may_delegate: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _agent_asset_dir() -> Path:
    skills_dir = Path(__file__).resolve().parents[2]
    return skills_dir / "setup-gpt56-model-router" / "assets" / "agents"


def load_role_inventory(asset_dir: str | Path | None = None) -> dict[str, Role]:
    """Load the shipped role contract from setup assets, never a duplicate table."""
    directory = Path(asset_dir) if asset_dir is not None else _agent_asset_dir()
    if not directory.is_dir():
        raise ContractError(f"role asset directory not found: {directory}")
    roles: dict[str, Role] = {}
    for path in sorted(directory.glob("*.toml")):
        source_text = path.read_text(encoding="utf-8")
        capability_markers = re.findall(
            r"^# Router capability: may_delegate=(true|false)$",
            source_text,
            flags=re.MULTILINE,
        )
        if len(capability_markers) != 1:
            raise ContractError(
                f"{path.name}: schema-2 role must contain exactly one "
                "'# Router capability: may_delegate=true|false' marker"
            )
        raw = tomllib.loads(source_text)
        required = ("name", "description", "model", "model_reasoning_effort", "developer_instructions")
        missing = [key for key in required if not isinstance(raw.get(key), str) or not raw[key].strip()]
        if missing:
            raise ContractError(f"{path.name}: missing role fields: {', '.join(missing)}")
        name = raw["name"]
        if name in roles:
            raise ContractError(f"duplicate role name: {name}")
        effort = raw["model_reasoning_effort"]
        if effort not in EFFORTS:
            raise ContractError(f"{path.name}: unsupported effort: {effort}")
        roles[name] = Role(
            name=name,
            description=raw["description"],
            model=raw["model"],
            reasoning_effort=effort,
            instructions=raw["developer_instructions"].strip(),
            read_only=raw.get("sandbox_mode") == "read-only",
            may_delegate=capability_markers[0] == "true",
            source=str(path),
        )
    if not roles:
        raise ContractError(f"no role TOMLs found in {directory}")
    return roles


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be an array")
    return value


def _required(data: Mapping[str, Any], names: tuple[str, ...], path: str = "$" ) -> None:
    missing = [name for name in names if name not in data]
    if missing:
        raise ContractError(f"{path} missing required fields: {', '.join(missing)}")


def _allowed(data: Mapping[str, Any], names: tuple[str, ...], path: str = "$") -> None:
    unexpected = sorted(set(data) - set(names))
    if unexpected:
        raise ContractError(f"{path} contains unsupported fields: {', '.join(unexpected)}")


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ContractError(f"{path} must be a non-empty string")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{path} must be a boolean")
    return value


def _integer(value: Any, path: str, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or (maximum is not None and value > maximum):
        suffix = f" between {minimum} and {maximum}" if maximum is not None else f" >= {minimum}"
        raise ContractError(f"{path} must be an integer{suffix}")
    return value


def _strings(value: Any, path: str) -> list[str]:
    values = _list(value, path)
    for index, item in enumerate(values):
        _string(item, f"{path}[{index}]")
    return values


def _unique_strings(value: Any, path: str) -> list[str]:
    values = _strings(value, path)
    if len(values) != len(set(values)):
        raise ContractError(f"{path} must contain unique items")
    return values


def _enum(value: Any, allowed: tuple[str, ...], path: str) -> str:
    if value not in allowed:
        raise ContractError(f"{path} must be one of: {', '.join(allowed)}")
    return value


def _schema_version(data: Mapping[str, Any]) -> None:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"$.schema_version must equal {SCHEMA_VERSION}")


DIMENSIONS = (
    "ambiguity", "consequence", "context_breadth", "irreversibility",
    "verification_strength", "latency_sensitivity",
)


def validate_task_profile(payload: Any) -> dict[str, Any]:
    data = dict(_object(payload, "$"))
    fields = ("schema_version", "task_id", "node_id", "objective", "kind", "phase", "dimensions", "risk_domains", "prior_attempts", "read_scopes", "write_scopes", "dependencies", "read_only", "human_authority", "orchestrator", "depth", "delegation_request", "runtime_capabilities")
    _required(data, ("schema_version", "objective", "kind", "phase", "dimensions", "risk_domains", "prior_attempts", "read_scopes", "write_scopes", "human_authority", "orchestrator", "depth", "delegation_request"))
    _allowed(data, fields)
    _schema_version(data)
    if "task_id" in data:
        _string(data["task_id"], "$.task_id")
        try:
            uuid.UUID(data["task_id"])
        except ValueError as error:
            raise ContractError("$.task_id must be a UUID") from error
    if "node_id" in data:
        _string(data["node_id"], "$.node_id")
        try:
            uuid.UUID(data["node_id"])
        except ValueError as error:
            raise ContractError("$.node_id must be a UUID") from error
    _string(data["objective"], "$.objective")
    _enum(data["kind"], KINDS, "$.kind")
    _enum(data["phase"], PHASES, "$.phase")
    dimensions = _object(data["dimensions"], "$.dimensions")
    _required(dimensions, DIMENSIONS, "$.dimensions")
    _allowed(dimensions, DIMENSIONS, "$.dimensions")
    for name in DIMENSIONS:
        dimension = _object(dimensions[name], f"$.dimensions.{name}")
        _required(dimension, ("rating", "evidence"), f"$.dimensions.{name}")
        _allowed(dimension, ("rating", "evidence"), f"$.dimensions.{name}")
        _integer(dimension["rating"], f"$.dimensions.{name}.rating", 0, 3)
        _string(dimension["evidence"], f"$.dimensions.{name}.evidence")
    _unique_strings(data["risk_domains"], "$.risk_domains")
    attempts = _list(data["prior_attempts"], "$.prior_attempts")
    for index, attempt_value in enumerate(attempts):
        attempt = _object(attempt_value, f"$.prior_attempts[{index}]")
        _required(attempt, ("model", "effort", "outcome", "evidence"), f"$.prior_attempts[{index}]")
        _allowed(attempt, ("model", "effort", "outcome", "evidence"), f"$.prior_attempts[{index}]")
        _string(attempt["model"], f"$.prior_attempts[{index}].model")
        _enum(attempt["effort"], EFFORTS, f"$.prior_attempts[{index}].effort")
        _string(attempt["outcome"], f"$.prior_attempts[{index}].outcome")
        _string(attempt["evidence"], f"$.prior_attempts[{index}].evidence")
    _unique_strings(data["read_scopes"], "$.read_scopes")
    _unique_strings(data["write_scopes"], "$.write_scopes")
    if "dependencies" in data:
        _unique_strings(data["dependencies"], "$.dependencies")
    authority = _object(data["human_authority"], "$.human_authority")
    _required(authority, ("local_writes", "external_writes", "destructive_actions", "quality_first"), "$.human_authority")
    _allowed(authority, ("local_writes", "external_writes", "destructive_actions", "quality_first"), "$.human_authority")
    for name in ("local_writes", "external_writes", "destructive_actions", "quality_first"):
        _bool(authority[name], f"$.human_authority.{name}")
    orchestrator = _object(data["orchestrator"], "$.orchestrator")
    _required(orchestrator, ("model", "effort"), "$.orchestrator")
    _allowed(orchestrator, ("model", "effort"), "$.orchestrator")
    _string(orchestrator["model"], "$.orchestrator.model")
    _enum(orchestrator["effort"], EFFORTS, "$.orchestrator.effort")
    _integer(data["depth"], "$.depth")
    delegation = _object(data["delegation_request"], "$.delegation_request")
    _required(delegation, ("requested",), "$.delegation_request")
    delegation_fields = ("requested", "authorize_descendants", "max_children", "max_parallel_children", "allowed_roles", "allowed_write_scopes", "may_spawn_writers", "forbidden_actions", "required_return")
    _allowed(delegation, delegation_fields, "$.delegation_request")
    _bool(delegation["requested"], "$.delegation_request.requested")
    if "authorize_descendants" in delegation:
        _bool(delegation["authorize_descendants"], "$.delegation_request.authorize_descendants")
    for name in ("max_children", "max_parallel_children"):
        if name in delegation:
            _integer(
                delegation[name],
                f"$.delegation_request.{name}",
                maximum=3 if name == "max_children" else 2,
            )
    for name in ("allowed_roles", "allowed_write_scopes", "forbidden_actions", "required_return"):
        if name in delegation:
            _unique_strings(delegation[name], f"$.delegation_request.{name}")
    if "may_spawn_writers" in delegation:
        _bool(delegation["may_spawn_writers"], "$.delegation_request.may_spawn_writers")
    if "read_only" in data:
        _bool(data["read_only"], "$.read_only")
    if "runtime_capabilities" in data:
        runtime = _object(data["runtime_capabilities"], "$.runtime_capabilities")
        runtime_fields = ("agent_type", "model_override", "current_sandbox", "read_only_agent_sandbox_enforced", "available_agents", "available_models")
        _allowed(runtime, runtime_fields, "$.runtime_capabilities")
        for name in ("agent_type", "model_override", "read_only_agent_sandbox_enforced"):
            if name in runtime:
                _bool(runtime[name], f"$.runtime_capabilities.{name}")
        if "current_sandbox" in runtime:
            _enum(runtime["current_sandbox"], ("read-only", "workspace-write", "danger-full-access"), "$.runtime_capabilities.current_sandbox")
        for name in ("available_agents", "available_models"):
            if name in runtime:
                _unique_strings(runtime[name], f"$.runtime_capabilities.{name}")
    return data


def _validate_route(value: Any, path: str, roles: Mapping[str, Role], *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    route = _object(value, path)
    fields = ("agent", "model", "reasoning_effort", "read_only")
    _required(route, fields, path)
    _allowed(route, fields, path)
    agent = _string(route["agent"], f"{path}.agent")
    if agent not in roles:
        raise ContractError(f"{path}.agent is not a bundled role: {agent}")
    role = roles[agent]
    if route["model"] != role.model:
        raise ContractError(f"{path} does not match bundled role model")
    _enum(route["reasoning_effort"], EFFORTS, f"{path}.reasoning_effort")
    if route["reasoning_effort"] != role.reasoning_effort:
        raise ContractError(f"{path} does not match bundled role reasoning effort")
    _bool(route["read_only"], f"{path}.read_only")
    if route["read_only"] != role.read_only:
        raise ContractError(f"{path} does not match bundled role read-only policy")


def validate_route_decision(payload: Any) -> dict[str, Any]:
    data = dict(_object(payload, "$"))
    fields = ("schema_version", "task_id", "node_id", "decision", "routing_mode", "primary", "review", "advisory", "delegation_capability", "parallel_eligibility", "reason_codes")
    _required(data, ("schema_version", "decision", "routing_mode", "primary", "review", "advisory", "delegation_capability", "parallel_eligibility", "reason_codes"))
    _allowed(data, fields)
    _schema_version(data)
    if "task_id" in data:
        _string(data["task_id"], "$.task_id")
    if "node_id" in data:
        _string(data["node_id"], "$.node_id")
    _enum(data["decision"], DECISIONS, "$.decision")
    _enum(data["routing_mode"], ROUTING_MODES, "$.routing_mode")
    roles = load_role_inventory()
    _validate_route(data["primary"], "$.primary", roles, nullable=True)
    review = _object(data["review"], "$.review")
    _required(review, ("required", "route"), "$.review")
    _allowed(review, ("required", "route"), "$.review")
    required = _bool(review["required"], "$.review.required")
    _validate_route(review["route"], "$.review.route", roles, nullable=True)
    if required != (review["route"] is not None):
        raise ContractError("$.review.route must be present exactly when review.required is true")
    advisory = _object(data["advisory"], "$.advisory")
    _required(advisory, ("required", "route"), "$.advisory")
    _allowed(advisory, ("required", "route"), "$.advisory")
    advisory_required = _bool(advisory["required"], "$.advisory.required")
    _validate_route(advisory["route"], "$.advisory.route", roles, nullable=True)
    if advisory_required != (advisory["route"] is not None):
        raise ContractError("$.advisory.route must be present exactly when advisory.required is true")
    validate_delegation_capability(data["delegation_capability"])
    parallel = _object(data["parallel_eligibility"], "$.parallel_eligibility")
    _required(parallel, ("eligible", "requires_disjoint_peers", "reason_code"), "$.parallel_eligibility")
    _allowed(parallel, ("eligible", "requires_disjoint_peers", "reason_code"), "$.parallel_eligibility")
    _bool(parallel["eligible"], "$.parallel_eligibility.eligible")
    _bool(parallel["requires_disjoint_peers"], "$.parallel_eligibility.requires_disjoint_peers")
    parallel_reason = _string(parallel["reason_code"], "$.parallel_eligibility.reason_code")
    if re.fullmatch(r"[A-Z][A-Z0-9_]*", parallel_reason) is None:
        raise ContractError("$.parallel_eligibility.reason_code must use UPPER_SNAKE_CASE")
    codes = _strings(data["reason_codes"], "$.reason_codes")
    if not codes:
        raise ContractError("$.reason_codes must contain at least one item")
    if len(codes) != len(set(codes)):
        raise ContractError("$.reason_codes must contain unique items")
    for index, code in enumerate(codes):
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", code) is None:
            raise ContractError(f"$.reason_codes[{index}] must use UPPER_SNAKE_CASE")
    return data


def validate_delegation_capability(payload: Any) -> dict[str, Any]:
    data = dict(_object(payload, "$"))
    fields = ("schema_version", "allowed", "remaining_depth", "max_children", "max_parallel_children", "allowed_roles", "allowed_models", "allowed_write_scopes", "may_spawn_writers", "forbidden_actions", "required_return")
    _required(data, fields)
    _allowed(data, fields)
    _schema_version(data)
    allowed = _bool(data["allowed"], "$.allowed")
    remaining = _integer(data["remaining_depth"], "$.remaining_depth", maximum=2)
    children = _integer(data["max_children"], "$.max_children", maximum=3)
    parallel = _integer(data["max_parallel_children"], "$.max_parallel_children", maximum=2)
    if parallel > children:
        raise ContractError("$.max_parallel_children cannot exceed $.max_children")
    roles = load_role_inventory()
    allowed_roles = _unique_strings(data["allowed_roles"], "$.allowed_roles")
    for role in allowed_roles:
        if role not in roles:
            raise ContractError(f"$.allowed_roles contains unknown bundled role: {role}")
    allowed_models = _unique_strings(data["allowed_models"], "$.allowed_models")
    expected_models = list(dict.fromkeys(roles[role].model for role in allowed_roles))
    if set(allowed_models) != set(expected_models):
        raise ContractError("$.allowed_models must exactly match the models of $.allowed_roles")
    _unique_strings(data["allowed_write_scopes"], "$.allowed_write_scopes")
    may_spawn_writers = _bool(data["may_spawn_writers"], "$.may_spawn_writers")
    if not may_spawn_writers and any(not roles[role].read_only for role in allowed_roles):
        raise ContractError("$.may_spawn_writers=false cannot allow writer roles")
    _unique_strings(data["forbidden_actions"], "$.forbidden_actions")
    _unique_strings(data["required_return"], "$.required_return")
    if not allowed and (remaining or children or parallel):
        raise ContractError("a disabled delegation capability must have zero budgets")
    return data


def validate_child_event(payload: Any) -> dict[str, Any]:
    data = dict(_object(payload, "$"))
    fields = ("schema_version", "event_type", "task_id", "node_id", "agent_path", "summary", "outcomes", "discovered_work", "validation", "blockers", "questions", "risks", "write_scopes", "review")
    _required(data, fields)
    _allowed(data, fields)
    _schema_version(data)
    _enum(data["event_type"], EVENTS, "$.event_type")
    _string(data["task_id"], "$.task_id")
    _string(data["node_id"], "$.node_id")
    _string(data["agent_path"], "$.agent_path")
    _string(data["summary"], "$.summary", allow_empty=data["event_type"] == "progress")
    for field in ("outcomes", "discovered_work", "validation", "blockers", "questions", "risks", "write_scopes"):
        _list(data[field], f"$.{field}")
    review = _object(data["review"], "$.review")
    _required(review, ("required", "status", "findings"), "$.review")
    _allowed(review, ("required", "status", "findings"), "$.review")
    _bool(review["required"], "$.review.required")
    _enum(review["status"], ("not_required", "pending", "passed", "failed"), "$.review.status")
    _list(review["findings"], "$.review.findings")
    return data


def validate_task_graph(payload: Any) -> dict[str, Any]:
    data = dict(_object(payload, "$"))
    fields = ("schema_version", "root_task_id", "authority_envelope", "budgets", "nodes", "outstanding_human_decisions", "external_blockers", "remaining_review")
    _required(data, fields)
    _allowed(data, fields)
    _schema_version(data)
    root_id = _string(data["root_task_id"], "$.root_task_id")
    _object(data["authority_envelope"], "$.authority_envelope")
    budgets = _object(data["budgets"], "$.budgets")
    budget_fields = ("max_depth", "max_open_threads", "max_total_spawns", "max_children_per_node", "max_parallel_children")
    _required(budgets, budget_fields, "$.budgets")
    _allowed(budgets, budget_fields, "$.budgets")
    for name in budget_fields:
        _integer(budgets[name], f"$.budgets.{name}")
    nodes = _list(data["nodes"], "$.nodes")
    ids: set[str] = set()
    dependencies: dict[str, list[str]] = {}
    for index, node_value in enumerate(nodes):
        node = _object(node_value, f"$.nodes[{index}]")
        node_fields = ("task_id", "status", "dependencies", "route_history", "required_review")
        _required(node, node_fields, f"$.nodes[{index}]")
        _allowed(node, node_fields, f"$.nodes[{index}]")
        task_id = _string(node["task_id"], f"$.nodes[{index}].task_id")
        if task_id in ids:
            raise ContractError(f"duplicate task graph node: {task_id}")
        ids.add(task_id)
        _enum(node["status"], NODE_STATUSES, f"$.nodes[{index}].status")
        dependencies[task_id] = _strings(node["dependencies"], f"$.nodes[{index}].dependencies")
        _strings(node["route_history"], f"$.nodes[{index}].route_history")
        _bool(node["required_review"], f"$.nodes[{index}].required_review")
    if root_id not in ids:
        raise ContractError("$.root_task_id must identify a node")
    for task_id, deps in dependencies.items():
        unknown = set(deps) - ids
        if unknown:
            raise ContractError(f"node {task_id} has unknown dependencies: {', '.join(sorted(unknown))}")
        if task_id in deps:
            raise ContractError(f"node {task_id} cannot depend on itself")
    for field in ("outstanding_human_decisions", "external_blockers", "remaining_review"):
        _list(data[field], f"$.{field}")
    return data


def validate_completion_record(payload: Any) -> dict[str, Any]:
    data = dict(_object(payload, "$"))
    fields = ("schema_version", "root_task_id", "status", "complete", "requested_outcomes_satisfied", "validation_passed", "required_reviews_complete", "unresolved_findings", "ready_or_running_nodes", "external_actions_taken", "residual_risks", "routes_used", "unmet_gates")
    _required(data, fields)
    _allowed(data, fields)
    _schema_version(data)
    _string(data["root_task_id"], "$.root_task_id")
    _enum(data["status"], ("complete", "partial", "failed", "cancelled"), "$.status")
    _bool(data["complete"], "$.complete")
    for field in ("requested_outcomes_satisfied", "validation_passed", "required_reviews_complete"):
        _bool(data[field], f"$.{field}")
    for field in ("unresolved_findings", "ready_or_running_nodes", "external_actions_taken", "residual_risks", "unmet_gates"):
        _list(data[field], f"$.{field}")
    _unique_strings(data["routes_used"], "$.routes_used")
    if data["complete"] != (data["status"] == "complete"):
        raise ContractError("$.complete must agree with $.status")
    if data["status"] == "complete":
        if not all(data[field] for field in ("requested_outcomes_satisfied", "validation_passed", "required_reviews_complete")):
            raise ContractError("a complete record must satisfy outcomes, validation, and required reviews")
        if data["unresolved_findings"] or data["ready_or_running_nodes"]:
            raise ContractError("a complete record cannot contain unresolved findings or open nodes")
    return data


VALIDATORS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "task-profile": validate_task_profile,
    "route-decision": validate_route_decision,
    "delegation-capability": validate_delegation_capability,
    "child-event": validate_child_event,
    "task-graph": validate_task_graph,
    "completion-record": validate_completion_record,
}


def validate_payload(contract: str, payload: Any) -> dict[str, Any]:
    """Validate and return a shallow copy of a protocol payload."""
    name = contract.removesuffix(".schema.json").replace("_", "-")
    try:
        return VALIDATORS[name](payload)
    except KeyError as error:
        raise ContractError(f"unknown protocol contract: {contract}") from error


def load_json_input(path: str) -> Any:
    import sys
    try:
        if path == "-":
            return json.load(sys.stdin)
        with Path(path).open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot load JSON input {path!r}: {error}") from error
