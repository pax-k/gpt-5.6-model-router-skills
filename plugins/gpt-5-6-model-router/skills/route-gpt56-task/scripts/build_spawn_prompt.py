#!/usr/bin/env python3
"""Build a bounded, runtime-enforceable GPT-5.6 child spawn request."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import PurePosixPath
import re
import sys
from typing import Any, Iterable, Mapping, Sequence


EVENT_TYPES = (
    "complete",
    "partial",
    "new_work",
    "needs_decision",
    "approval_required",
    "risk_discovered",
    "validation_failed",
    "blocked",
    "conflict",
    "budget_exhausted",
    "cancelled",
    "failed",
)
TERMINAL_EVENT_SCHEMA = (
    "schema_version",
    "event_type",
    "task_id",
    "node_id",
    "agent_path",
    "summary",
    "outcomes",
    "discovered_work",
    "validation",
    "blockers",
    "questions",
    "risks",
    "write_scopes",
    "review",
)
DELEGATION_CAPABILITY_FIELDS = frozenset(
    {
        "schema_version",
        "allowed",
        "remaining_depth",
        "max_children",
        "max_parallel_children",
        "allowed_roles",
        "allowed_models",
        "allowed_write_scopes",
        "may_spawn_writers",
        "forbidden_actions",
        "required_return",
    }
)


class UnsupportedSpawnContract(ValueError):
    """Raised when the runtime cannot enforce the selected model and effort."""


def load_inventory() -> Mapping[str, Any]:
    try:
        from router_contract import load_role_inventory
    except (ImportError, AttributeError) as error:  # pragma: no cover - install error
        raise RuntimeError("canonical router role inventory is unavailable") from error
    try:
        inventory = load_role_inventory()
    except (OSError, ValueError) as error:
        raise RuntimeError(f"canonical router role inventory is invalid: {error}") from error
    if not isinstance(inventory, Mapping):
        raise RuntimeError("canonical router role inventory is invalid")
    return inventory


def disabled_delegation_capability() -> dict[str, Any]:
    """Return the canonical validated shape used when a child cannot delegate."""
    return {
        "schema_version": 1,
        "allowed": False,
        "remaining_depth": 0,
        "max_children": 0,
        "max_parallel_children": 0,
        "allowed_roles": [],
        "allowed_models": [],
        "allowed_write_scopes": [],
        "may_spawn_writers": False,
        "forbidden_actions": [],
        "required_return": [],
    }


def validate_child_delegation_capability(
    capability: Mapping[str, Any] | None,
    inventory: Mapping[str, Any],
    parent_capability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the capability that will be embedded and its authority attenuation."""
    try:
        from router_contract import validate_delegation_capability
    except (ImportError, AttributeError) as error:  # pragma: no cover - install error
        raise RuntimeError("canonical delegation capability validator is unavailable") from error

    if capability is None:
        candidate = disabled_delegation_capability()
        if isinstance(parent_capability, Mapping):
            candidate["forbidden_actions"] = list(parent_capability.get("forbidden_actions", []))
            candidate["required_return"] = list(parent_capability.get("required_return", []))
    else:
        candidate = capability
    if isinstance(candidate, Mapping):
        if candidate.get("remaining_depth", 0) > 1:
            raise ValueError("child delegation capability remaining_depth must be <= 1")
        if candidate.get("max_children", 0) > 3:
            raise ValueError("child delegation capability max_children must be <= 3")
        if candidate.get("max_parallel_children", 0) > 2:
            raise ValueError("child delegation capability max_parallel_children must be <= 2")
    validated = validate_delegation_capability(candidate)
    unexpected = set(validated) - DELEGATION_CAPABILITY_FIELDS
    if unexpected:
        raise ValueError(
            "delegation capability contains unsupported fields: "
            + ", ".join(sorted(unexpected))
        )
    if validated["remaining_depth"] > 1:
        raise ValueError("child delegation capability remaining_depth must be <= 1")
    if validated["max_children"] > 3:
        raise ValueError("child delegation capability max_children must be <= 3")
    if validated["max_parallel_children"] > 2:
        raise ValueError("child delegation capability max_parallel_children must be <= 2")

    if not validated["allowed"] and (
        validated["allowed_roles"]
        or validated["allowed_models"]
        or validated["allowed_write_scopes"]
        or validated["may_spawn_writers"]
    ):
        raise ValueError("disabled delegation capability cannot retain child authority")

    role_models = {
        str(role_value(inventory[name], "model")) for name in validated["allowed_roles"]
    }
    declared_models = set(validated["allowed_models"])
    if declared_models != role_models:
        raise ValueError(
            "delegation capability allowed_models must exactly match allowed_roles models"
        )
    if not validated["may_spawn_writers"]:
        writers = [
            name
            for name in validated["allowed_roles"]
            if not bool(role_value(inventory[name], "read_only"))
        ]
        if writers:
            raise ValueError(
                "delegation capability may_spawn_writers=false cannot allow writer roles: "
                + ", ".join(sorted(writers))
            )

    if parent_capability is not None:
        parent = validate_delegation_capability(parent_capability)
        unexpected_parent = set(parent) - DELEGATION_CAPABILITY_FIELDS
        if unexpected_parent:
            raise ValueError(
                "parent delegation capability contains unsupported fields: "
                + ", ".join(sorted(unexpected_parent))
            )
        if parent["max_children"] > 3 or parent["max_parallel_children"] > 2:
            raise ValueError("parent delegation capability exceeds v0.2 child budgets")
        if not parent["allowed"] and (
            parent["allowed_roles"]
            or parent["allowed_models"]
            or parent["allowed_write_scopes"]
            or parent["may_spawn_writers"]
        ):
            raise ValueError("disabled parent delegation capability retains child authority")
        parent_role_models = {
            str(role_value(inventory[name], "model")) for name in parent["allowed_roles"]
        }
        if set(parent["allowed_models"]) != parent_role_models:
            raise ValueError(
                "parent delegation capability allowed_models must exactly match allowed_roles models"
            )
        if not parent["may_spawn_writers"] and any(
            not bool(role_value(inventory[name], "read_only"))
            for name in parent["allowed_roles"]
        ):
            raise ValueError(
                "parent delegation capability may_spawn_writers=false cannot allow writer roles"
            )
        if validated["allowed"] and not parent["allowed"]:
            raise ValueError("child delegation capability cannot enable delegation denied by parent")
        for field in ("remaining_depth", "max_children", "max_parallel_children"):
            if validated[field] > parent[field]:
                raise ValueError(f"child delegation capability {field} exceeds parent")
        for field in ("allowed_roles", "allowed_models", "allowed_write_scopes"):
            if not set(validated[field]).issubset(parent[field]):
                raise ValueError(f"child delegation capability {field} exceeds parent")
        if validated["may_spawn_writers"] and not parent["may_spawn_writers"]:
            raise ValueError("child delegation capability writer permission exceeds parent")
        if not set(parent["forbidden_actions"]).issubset(validated["forbidden_actions"]):
            raise ValueError("child delegation capability removes parent forbidden actions")
        if not set(parent["required_return"]).issubset(validated["required_return"]):
            raise ValueError("child delegation capability removes parent return requirements")
    return validated


def role_value(role: Any, *names: str) -> Any:
    for name in names:
        value = role.get(name) if isinstance(role, Mapping) else getattr(role, name, None)
        if value is not None:
            return value
    return None


def nested_value(data: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value: Any = data
        for component in path:
            if not isinstance(value, Mapping) or component not in value:
                break
            value = value[component]
        else:
            if value is not None:
                return value
    return None


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not result:
        raise ValueError("task and node IDs must contain an alphanumeric character")
    return result


def make_task_name(task_id: str, node_id: str) -> str:
    """Preserve both graph identifiers in the runtime-unique child task name."""
    digest = hashlib.sha256(f"{task_id}\0{node_id}".encode()).hexdigest()[:10]
    return f"{slug(task_id)[:32]}__{slug(node_id)[:32]}__{digest}"


def validate_parent_agent_path(parent_agent_path: str, parent_depth: int) -> str:
    """Require the canonical runtime path shape for the claimed graph depth."""
    parent = PurePosixPath(parent_agent_path)
    if (
        not parent.is_absolute()
        or str(parent) != parent_agent_path
        or parent.parts[:2] != ("/", "root")
        or len(parent.parts) != parent_depth + 2
    ):
        raise ValueError("parent agent path must be canonical and match parent_depth")
    if any(re.fullmatch(r"[a-z0-9_]+", component) is None for component in parent.parts[2:]):
        raise ValueError("parent agent path contains a non-canonical component")
    return str(parent)


def make_agent_path(parent_agent_path: str, task_name: str) -> str:
    parent = PurePosixPath(parent_agent_path)
    return str(parent / task_name)


def normalize_spawn_fields(fields: Iterable[str] | None, decision: Mapping[str, Any]) -> set[str]:
    if fields is not None:
        return {str(field) for field in fields}
    declared = decision.get("supported_spawn_fields") or decision.get("spawn_fields")
    if declared:
        return {str(field) for field in declared}
    mode = str(decision.get("routing_mode") or "").replace("_", "-")
    if mode == "custom-agent":
        return {"agent_type"}
    if mode == "model-override":
        return {"model", "reasoning_effort"}
    return set()


def choose_routing_mode(fields: set[str]) -> str:
    if "agent_type" in fields:
        return "custom-agent"
    if {"model", "reasoning_effort"}.issubset(fields):
        return "model-override"
    missing = sorted({"agent_type", "model", "reasoning_effort"} - fields)
    raise UnsupportedSpawnContract(
        "unsupported spawn contract: expected agent_type or both model and "
        f"reasoning_effort; missing fields: {', '.join(missing)}"
    )


def render_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def terminal_event_template(
    decision: Mapping[str, Any], task_id: str, node_id: str, agent_path: str
) -> dict[str, Any]:
    review = decision.get("review") or {}
    review_required = bool(review.get("required")) if isinstance(review, Mapping) else False
    return {
        "schema_version": 1,
        "event_type": f"one of: {', '.join(EVENT_TYPES)}",
        "task_id": task_id,
        "node_id": node_id,
        "agent_path": agent_path,
        "summary": "string",
        "outcomes": [],
        "discovered_work": [],
        "validation": [],
        "blockers": [],
        "questions": [],
        "risks": [],
        "write_scopes": [],
        "review": {
            "required": review_required,
            "status": "pending" if review_required else "not_required",
            "findings": [],
        },
    }


def build_spawn_prompt(
    decision: Mapping[str, Any],
    bounded_context: Any,
    acceptance_criteria: Sequence[str],
    validation_requirements: Sequence[str],
    delegation_capability: Mapping[str, Any] | None = None,
    *,
    supported_spawn_fields: Iterable[str] | None = None,
    parent_delegation_capability: Mapping[str, Any] | None = None,
) -> str:
    """Return the exact child message for an enforceable route decision."""
    task_id = str(decision.get("task_id") or "").strip()
    node_id = str(decision.get("node_id") or "").strip()
    if not task_id or not node_id:
        raise ValueError("route decision must include non-empty task_id and node_id")
    agent = nested_value(
        decision,
        ("primary", "agent"),
        ("primary_agent",),
        ("agent",),
        ("expected_agent",),
    )
    if not agent:
        raise ValueError("route decision does not select an agent")
    inventory = load_inventory()
    try:
        role = inventory[str(agent)]
    except KeyError as error:
        raise ValueError(f"unknown selected agent: {agent}") from error
    context = bounded_context if isinstance(bounded_context, Mapping) else {}
    parent_path = str(context.get("parent_agent_path") or "/root")
    parent_depth = int(context.get("parent_depth", 0))
    if parent_depth < 0 or parent_depth >= 2:
        raise ValueError("parent_depth must be 0 or 1 for a depth-two router")
    parent_path = validate_parent_agent_path(parent_path, parent_depth)
    descendant = parent_depth > 0 or parent_path != "/root"
    if descendant:
        if parent_delegation_capability is None:
            raise ValueError("descendant spawn requires the parent's delegation capability proof")
        from router_contract import validate_delegation_capability
        parent_proof = validate_delegation_capability(parent_delegation_capability)
        if not parent_proof["allowed"] or parent_proof["remaining_depth"] < 1:
            raise ValueError("parent delegation capability does not authorize a descendant spawn")
    delegated = validate_child_delegation_capability(
        delegation_capability, inventory, parent_delegation_capability
    )
    if delegated["allowed"] and role_value(role, "may_delegate") is False:
        raise ValueError(f"selected agent is a leaf and may not delegate: {agent}")
    fields = normalize_spawn_fields(supported_spawn_fields, decision)
    mode = choose_routing_mode(fields)
    task_name = make_task_name(task_id, node_id)
    agent_path = make_agent_path(parent_path, task_name)

    role_contract: dict[str, Any] = {
        "agent": str(agent),
        "model": role_value(role, "model"),
        "reasoning_effort": role_value(role, "reasoning_effort", "effort", "model_reasoning_effort"),
        "read_only": bool(role_value(role, "read_only")),
    }
    if mode == "model-override":
        role_contract["description"] = role_value(role, "description")
        role_contract["developer_instructions"] = role_value(role, "instructions", "developer_instructions")

    lines = [
        "You own one bounded router task. Execute it autonomously within the supplied scope and authority.",
        "Use repository and runtime evidence, make reasonable reversible assumptions, choose the best supported option, and continue without asking the human for routine clarification or router-specific approval.",
        "Do not manufacture preview, permission, or approval gates. If the host itself requires confirmation, preserve the requesting action and provenance and let the host mechanism handle it.",
        "Return newly discovered out-of-scope work instead of silently expanding authority. Correctness, validation, review, scope, and budget gates remain mandatory.",
        "",
        "Assignment",
        render_json(
            {
                "schema_version": 1,
                "task_id": task_id,
                "node_id": node_id,
                "agent_path": agent_path,
                "depth": parent_depth + 1,
                "task_name": task_name,
                "routing_mode": mode,
                "role": role_contract,
            }
        ),
        "",
        "Bounded context",
        render_json(bounded_context),
        "",
        "Acceptance criteria",
        render_json(list(acceptance_criteria)),
        "",
        "Validation requirements",
        render_json(list(validation_requirements)),
        "",
        "Delegation capability",
        render_json(delegated),
        "",
        "Do not delegate unless the capability explicitly sets allowed=true, and never exceed its depth, child, role, model, write-scope, or action limits.",
        "Do not emit needs_decision for an ordinary semantic choice: select and record the best evidence-backed reversible option. Emit approval_required only when an actual host/tool approval is presently required, never for a router-authored policy gate.",
        "",
        "Return exactly one JSON object and no Markdown fences. It must contain every key in this schema:",
        render_json(terminal_event_template(decision, task_id, node_id, agent_path)),
        "Use event_type=complete only when every acceptance criterion is satisfied and the required validation has passed. Do not claim completion of the parent task.",
    ]
    return "\n".join(lines)


def build_spawn_request(
    decision: Mapping[str, Any],
    bounded_context: Any,
    acceptance_criteria: Sequence[str],
    validation_requirements: Sequence[str],
    delegation_capability: Mapping[str, Any] | None = None,
    *,
    supported_spawn_fields: Iterable[str] | None = None,
    parent_delegation_capability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fields = normalize_spawn_fields(supported_spawn_fields, decision)
    mode = choose_routing_mode(fields)
    message = build_spawn_prompt(
        decision,
        bounded_context,
        acceptance_criteria,
        validation_requirements,
        delegation_capability,
        supported_spawn_fields=fields,
        parent_delegation_capability=parent_delegation_capability,
    )
    task_id = str(decision["task_id"])
    node_id = str(decision["node_id"])
    agent = nested_value(decision, ("primary", "agent"), ("primary_agent",), ("agent",), ("expected_agent",))
    role = load_inventory()[str(agent)]
    request: dict[str, Any] = {
        "task_name": make_task_name(task_id, node_id),
        "message": message,
        "fork_turns": "none",
    }
    if mode == "custom-agent":
        request["agent_type"] = str(agent)
    else:
        request["model"] = role_value(role, "model")
        request["reasoning_effort"] = role_value(role, "reasoning_effort", "effort", "model_reasoning_effort")
    return request


def parse_json_object(raw: str, label: str) -> Mapping[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON envelope path, or - for stdin.")
    parser.add_argument("--json", action="store_true", help="Emit the JSON spawn envelope.")
    parser.add_argument("--decision-json")
    parser.add_argument("--bounded-context-json")
    parser.add_argument("--acceptance-criterion", action="append")
    parser.add_argument("--validation-requirement", action="append")
    parser.add_argument("--delegation-capability-json")
    parser.add_argument("--supported-spawn-field", action="append")
    return parser.parse_args()


def load_input(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def delegation_capability_from_envelope(value: Any) -> Any:
    """Accept either the capability itself or a named parent/root wrapper."""
    if isinstance(value, Mapping):
        for name in ("delegation_capability", "delegation"):
            if name in value:
                return value[name]
    return value


def build_output(
    decision: Mapping[str, Any],
    bounded_context: Any,
    acceptance_criteria: Sequence[str],
    validation_requirements: Sequence[str],
    delegation_capability: Mapping[str, Any] | None,
    supported_spawn_fields: Iterable[str] | None,
    parent_delegation_capability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    request = build_spawn_request(
        decision,
        bounded_context,
        acceptance_criteria,
        validation_requirements,
        delegation_capability,
        supported_spawn_fields=supported_spawn_fields,
        parent_delegation_capability=parent_delegation_capability,
    )
    routing_mode = "custom-agent" if "agent_type" in request else "model-override"
    return {
        "prompt": request["message"],
        "routing_mode": routing_mode,
        "spawn_request": request,
        "task_name": request["task_name"],
    }


def main() -> int:
    args = parse_args()
    try:
        if args.input:
            envelope = parse_json_object(
                json.dumps(load_input(args.input)), "input envelope"
            )
            required = (
                "decision",
                "bounded_context",
                "acceptance_criteria",
                "validation_requirements",
                "supported_spawn_fields",
            )
            missing = [name for name in required if name not in envelope]
            if missing:
                raise ValueError(f"input envelope missing fields: {', '.join(missing)}")
            decision = envelope["decision"]
            context = envelope["bounded_context"]
            acceptance = envelope["acceptance_criteria"]
            validation = envelope["validation_requirements"]
            capability = envelope.get("delegation_capability")
            parent_capability = delegation_capability_from_envelope(
                envelope.get(
                    "parent_delegation_capability",
                    envelope.get(
                        "root_delegation_capability",
                        envelope.get(
                            "parent_delegation_envelope",
                            envelope.get("root_delegation_envelope"),
                        ),
                    ),
                )
            )
            spawn_fields = envelope["supported_spawn_fields"]
            if not isinstance(decision, Mapping):
                raise ValueError("input envelope decision must be a JSON object")
            if capability is not None and not isinstance(capability, Mapping):
                raise ValueError("input envelope delegation_capability must be a JSON object or null")
            if parent_capability is not None and not isinstance(parent_capability, Mapping):
                raise ValueError("input envelope parent/root delegation capability must be a JSON object or null")
            if not isinstance(acceptance, list) or not all(isinstance(item, str) for item in acceptance):
                raise ValueError("input envelope acceptance_criteria must be an array of strings")
            if not isinstance(validation, list) or not all(isinstance(item, str) for item in validation):
                raise ValueError("input envelope validation_requirements must be an array of strings")
            if not isinstance(spawn_fields, list) or not all(isinstance(item, str) for item in spawn_fields):
                raise ValueError("input envelope supported_spawn_fields must be an array of strings")
        else:
            if not args.decision_json or args.bounded_context_json is None:
                raise ValueError("use --input or supply --decision-json and --bounded-context-json")
            if not args.acceptance_criterion or not args.validation_requirement:
                raise ValueError("inline mode requires acceptance and validation requirements")
            decision = parse_json_object(args.decision_json, "decision")
            context = json.loads(args.bounded_context_json)
            acceptance = args.acceptance_criterion
            validation = args.validation_requirement
            capability = (
                parse_json_object(args.delegation_capability_json, "delegation capability")
                if args.delegation_capability_json
                else None
            )
            parent_capability = None
            spawn_fields = args.supported_spawn_field
        output = build_output(
            decision,
            context,
            acceptance,
            validation,
            capability,
            spawn_fields,
            parent_capability,
        )
    except (json.JSONDecodeError, KeyError, OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
