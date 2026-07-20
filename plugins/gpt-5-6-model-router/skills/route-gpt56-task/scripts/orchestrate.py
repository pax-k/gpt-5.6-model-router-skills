#!/usr/bin/env python3
"""Deterministic task-graph orchestration for the GPT-5.6 model router."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


try:
    from router_contract import ContractError, load_role_inventory, validate_child_event, validate_delegation_capability, validate_task_graph
except ModuleNotFoundError:  # Supports importlib loading this script directly in tests.
    _contract_path = Path(__file__).with_name("router_contract.py")
    _contract_spec = importlib.util.spec_from_file_location("router_contract", _contract_path)
    if _contract_spec is None or _contract_spec.loader is None:  # pragma: no cover
        raise
    _contract_module = importlib.util.module_from_spec(_contract_spec)
    sys.modules.setdefault("router_contract", _contract_module)
    _contract_spec.loader.exec_module(_contract_module)
    ContractError = _contract_module.ContractError
    load_role_inventory = _contract_module.load_role_inventory
    validate_child_event = _contract_module.validate_child_event
    validate_delegation_capability = _contract_module.validate_delegation_capability
    validate_task_graph = _contract_module.validate_task_graph


SCHEMA_VERSION = 1
DEFAULT_BUDGETS = {
    "max_depth": 2,
    "max_open_threads": 6,
    "max_total_spawns": 8,
    "max_children_per_node": 3,
    "max_parallel_children": 2,
}
NODE_STATUSES = {
    "queued", "ready", "running", "waiting", "blocked", "review", "repair",
    "complete", "partial", "failed", "cancelled",
}
EVENT_TYPES = {
    "progress", "complete", "partial", "new_work", "needs_decision",
    "approval_required", "risk_discovered", "validation_failed", "blocked",
    "conflict", "budget_exhausted", "cancelled", "failed",
}
MAX_NORMALIZATION_ATTEMPTS = 1
MAX_REPAIR_CYCLES = 2


class OrchestrationError(ValueError):
    """A deterministic orchestration contract violation."""


class DurabilityError(RuntimeError):
    """A required ledger update could not be made durable."""


def _uuid(value: str | None = None) -> str:
    if value is None:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise OrchestrationError(f"task id must be a UUID: {value!r}") from error


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _new_node(profile: dict[str, Any], *, task_id: str, parent_id: str | None, depth: int) -> dict[str, Any]:
    dependencies = profile.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise OrchestrationError("dependencies must be an array")
    write_scopes = profile.get("write_scopes", [])
    read_scopes = profile.get("read_scopes", [])
    if not isinstance(write_scopes, list) or not all(isinstance(item, str) and item for item in write_scopes):
        raise OrchestrationError("write_scopes must be an array of non-empty strings")
    if not isinstance(read_scopes, list) or not all(isinstance(item, str) and item for item in read_scopes):
        raise OrchestrationError("read_scopes must be an array of non-empty strings")
    read_only = bool(profile.get("read_only", False))
    if read_only and write_scopes:
        raise OrchestrationError("read-only nodes cannot declare write scopes")
    return {
        "id": task_id,
        "task_id": task_id,
        "parent_id": parent_id,
        "objective": str(profile.get("objective", "")).strip(),
        "kind": profile.get("kind", "ambiguous"),
        "phase": profile.get("phase", "implementation"),
        "status": profile.get("status", "queued"),
        "owner": profile.get("owner"),
        "depth": depth,
        "dependencies": list(dependencies),
        "read_only": read_only,
        "read_scopes": list(read_scopes),
        "write_scopes": list(write_scopes),
        "route_history": list(profile.get("route_history", [])),
        "validation": {
            "required": bool(profile.get("validation_required", profile.get("validation", {}).get("required", True))),
            "passed": profile.get("validation", {}).get("passed"),
            "records": list(profile.get("validation", {}).get("records", [])),
        },
        "review": {
            "required": bool(profile.get("required_review", profile.get("review", {}).get("required", False))),
            "complete": bool(profile.get("review", {}).get("complete", False)),
            "status": profile.get("review", {}).get("status", "pending"),
            "findings": list(profile.get("review", {}).get("findings", [])),
        },
        "blockers": list(profile.get("blockers", [])),
        "decisions": list(profile.get("decisions", [])),
        "resolved_decisions": list(profile.get("resolved_decisions", [])),
        "repair_cycles": int(profile.get("repair_cycles", 0)),
        "normalization_attempts": int(profile.get("normalization_attempts", 0)),
        "outcomes_satisfied": bool(profile.get("outcomes_satisfied", False)),
        "result": profile.get("result"),
        "delegation": _json_copy(profile.get("delegation", profile.get("delegation_capability", {"allowed": False}))),
        "dispatch_count": int(profile.get("dispatch_count", 0)),
        "awaiting_children": bool(profile.get("awaiting_children", False)),
        "superseded": bool(profile.get("superseded", False)),
    }


def initialize(profile: dict[str, Any], ledger_path: str | None = None) -> dict[str, Any]:
    """Create orchestration state from a root profile and optional child profiles."""
    if not isinstance(profile, dict):
        raise OrchestrationError("input profile must be a JSON object")
    root_id = _uuid(profile.get("task_id") or profile.get("id"))
    root = _new_node(profile, task_id=root_id, parent_id=None, depth=0)
    root["status"] = profile.get("status", "running")
    raw_nodes = profile.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise OrchestrationError("nodes must be an array")
    nodes = {root_id: root}
    aliases: dict[str, str] = {root_id: root_id}
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise OrchestrationError("each node must be an object")
        supplied = raw.get("id") or raw.get("task_id")
        node_id = _uuid(supplied)
        if supplied:
            aliases[str(supplied)] = node_id
        if node_id in nodes:
            raise OrchestrationError(f"duplicate task id: {node_id}")
        parent_id = raw.get("parent_id", root_id)
        parent_id = aliases.get(str(parent_id), str(parent_id))
        if parent_id not in nodes:
            raise OrchestrationError(f"unknown parent task: {parent_id}")
        depth = int(raw.get("depth", nodes[parent_id]["depth"] + 1))
        nodes[node_id] = _new_node(raw, task_id=node_id, parent_id=parent_id, depth=depth)
    for node in nodes.values():
        node["dependencies"] = [aliases.get(str(item), str(item)) for item in node["dependencies"]]
        unknown = set(node["dependencies"]) - set(nodes)
        if unknown:
            raise OrchestrationError(f"unknown dependencies for {node['id']}: {sorted(unknown)}")
        delegation = node.get("delegation", {"allowed": False})
        if node["id"] != root_id and delegation != {"allowed": False}:
            try:
                validate_delegation_capability(delegation)
            except ContractError as error:
                raise OrchestrationError(f"invalid stored delegation capability for {node['id']}: {error}") from error
            if delegation["allowed"]:
                route = node.get("route_history", [])[-1:] or [None]
                role = load_role_inventory().get(route[0]) if route[0] else None
                if role is None or not role.may_delegate:
                    raise OrchestrationError(f"node {node['id']} is not routed to a delegation-capable owner")
    budgets = {**DEFAULT_BUDGETS, **profile.get("budgets", {})}
    _validate_graph(nodes, root_id, budgets)
    state = {
        "schema_version": SCHEMA_VERSION,
        "task_id": root_id,
        "objective": root["objective"],
        "root_thread_id": profile.get("root_thread_id"),
        "status": "running",
        "nodes": nodes,
        "budgets": budgets,
        "usage": {"total_spawns": sum(node["dispatch_count"] for node in nodes.values()), "open_threads": 0},
        "events": [],
        "warnings": [],
        "ledger": {"required": bool(ledger_path), "explicit": bool(ledger_path), "path": ledger_path, "triggered_by": []},
        "workspace_root": str(Path(profile.get("workspace_root", Path.cwd())).resolve()),
        "resumable": bool(profile.get("resumable", False)),
        "outstanding_human_decisions": [],
        "external_blockers": [],
        "authority_envelope": _json_copy(profile.get("human_authority", {})),
    }
    _record(state, "initialized", root_id, {"node_count": len(nodes)})
    _refresh_ready(state)
    _automatic_ledger_triggers(state)
    return state


def _validate_graph(nodes: dict[str, dict[str, Any]], root_id: str, budgets: dict[str, int]) -> None:
    if root_id not in nodes:
        raise OrchestrationError("root task is missing")
    for node in nodes.values():
        if node["status"] not in NODE_STATUSES:
            raise OrchestrationError(f"unsupported node status: {node['status']}")
        if node["depth"] > budgets["max_depth"]:
            raise OrchestrationError(f"max depth {budgets['max_depth']} exceeded by {node['id']}")
        child_count = sum(candidate.get("parent_id") == node["id"] for candidate in nodes.values())
        if child_count > budgets["max_children_per_node"]:
            raise OrchestrationError(f"max children exceeded for {node['id']}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise OrchestrationError("task dependencies contain a cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in nodes[task_id]["dependencies"]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in nodes:
        visit(task_id)


def _record(state: dict[str, Any], trigger: str, task_id: str | None, data: dict[str, Any] | None = None) -> None:
    state["events"].append({
        "sequence": len(state["events"]) + 1,
        "trigger": trigger,
        "task_id": task_id,
        "data": data or {},
    })


def _children(state: dict[str, Any], parent_id: str) -> list[dict[str, Any]]:
    return [node for node in state["nodes"].values() if node.get("parent_id") == parent_id]


def _scope(scope: str) -> PurePosixPath:
    return PurePosixPath(scope.replace("\\", "/").rstrip("/") or "/")


def _overlap(left: str, right: str) -> bool:
    a, b = _scope(left), _scope(right)
    return a == b or a in b.parents or b in a.parents


def may_run_parallel(left: dict[str, Any], right: dict[str, Any]) -> tuple[bool, str]:
    """Parallelize independent readers and writers with explicitly disjoint scopes."""
    if left["read_only"] and right["read_only"]:
        return True, "both tasks are read-only"
    if left["read_only"] != right["read_only"]:
        reader, writer = (left, right) if left["read_only"] else (right, left)
        if not writer["write_scopes"]:
            return False, "writer scope is unknown"
        if reader["read_scopes"] and any(
            _overlap(read_scope, write_scope)
            for read_scope in reader["read_scopes"]
            for write_scope in writer["write_scopes"]
        ):
            return False, "reader scope overlaps writer scope"
        return True, "reader and writer scopes are independent"
    if not left["write_scopes"] or not right["write_scopes"]:
        return False, "writer scope is unknown"
    if any(_overlap(a, b) for a in left["write_scopes"] for b in right["write_scopes"]):
        return False, "write scopes overlap"
    return True, "writer scopes are explicitly disjoint"


def _dependency_ready(state: dict[str, Any], node: dict[str, Any]) -> bool:
    return all(state["nodes"][dep]["status"] == "complete" for dep in node["dependencies"])


def _refresh_ready(state: dict[str, Any]) -> None:
    for node in state["nodes"].values():
        children = _children(state, node["id"])
        if node.get("awaiting_children") and children and all(child["status"] == "complete" for child in children):
            node["awaiting_children"] = False
            node["status"] = "ready"
            _record(state, "parent-synthesis-ready", node["id"], {"children": [child["id"] for child in children]})
    for node in state["nodes"].values():
        if node["status"] in {"queued", "ready"}:
            node["status"] = "ready" if _dependency_ready(state, node) else "queued"
    state["usage"]["open_threads"] = sum(
        node["status"] in {"running", "waiting", "review", "repair"}
        for node in state["nodes"].values() if node["id"] != state["task_id"]
    )


def ready(state: dict[str, Any]) -> dict[str, Any]:
    """Return the next deterministic concurrency-safe ready wave."""
    state = _json_copy(state)
    _refresh_ready(state)
    if state.get("status") != "running":
        candidates = sorted(
            node["id"]
            for node in state["nodes"].values()
            if node["status"] == "ready" and node["id"] != state["task_id"]
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "ready": [],
            "parallel_groups": [],
            "deferred": [{"id": task_id, "reason": f"orchestration is {state.get('status')}"} for task_id in candidates],
            "reasons": {},
            "budget_remaining": {
                "open_threads": max(0, state["budgets"]["max_open_threads"] - state["usage"]["open_threads"]),
                "total_spawns": max(0, state["budgets"]["max_total_spawns"] - state["usage"]["total_spawns"]),
            },
        }
    budgets = state["budgets"]
    remaining_open = max(0, budgets["max_open_threads"] - state["usage"]["open_threads"])
    remaining_spawns = max(0, budgets["max_total_spawns"] - state["usage"]["total_spawns"])
    width = min(budgets["max_parallel_children"], remaining_open, remaining_spawns)
    running = [node for node in state["nodes"].values() if node["status"] == "running" and node["id"] != state["task_id"]]
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, str]] = []
    candidates = sorted(
        (node for node in state["nodes"].values() if node["status"] == "ready" and node["id"] != state["task_id"]),
        key=lambda node: (node["depth"], node["id"]),
    )
    for node in candidates:
        if len(selected) >= width:
            deferred.append({"id": node["id"], "reason": "parallel or spawn budget exhausted"})
            continue
        peers = running + selected
        conflicts = [may_run_parallel(node, peer) for peer in peers]
        if all(allowed for allowed, _ in conflicts):
            selected.append(node)
        else:
            deferred.append({"id": node["id"], "reason": next(reason for allowed, reason in conflicts if not allowed)})
    return {
        "schema_version": SCHEMA_VERSION,
        "ready": [node["id"] for node in selected],
        "parallel_groups": [[node["id"] for node in selected]] if selected else [],
        "deferred": deferred,
        "reasons": {
            node["id"]: ("read-only" if node["read_only"] else "known write scope")
            for node in selected
        },
        "budget_remaining": {"open_threads": remaining_open, "total_spawns": remaining_spawns},
    }


def dispatch(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reserve the next ready wave so repeated reads cannot produce duplicate spawns."""
    state = _json_copy(state)
    wave = ready(state)
    selected = wave["ready"]
    if state["usage"]["total_spawns"] + len(selected) > state["budgets"]["max_total_spawns"]:
        raise OrchestrationError("dispatch exceeds total spawn budget")
    for task_id in selected:
        node = state["nodes"][task_id]
        if node["status"] != "ready":
            raise OrchestrationError(f"node is no longer ready: {task_id}")
        node["status"] = "running"
        node["dispatch_count"] += 1
        state["usage"]["total_spawns"] += 1
    if selected:
        _record(state, "wave-dispatched", None, {"task_ids": selected})
    _refresh_ready(state)
    _automatic_ledger_triggers(state)
    return state, wave


def apply_control(state: dict[str, Any], control: dict[str, Any]) -> dict[str, Any]:
    """Apply a root/human steering transition without accepting child free-form state."""
    state = _json_copy(state)
    if not isinstance(control, dict):
        raise OrchestrationError("control input must be an object")
    if control.get("actor", "root") != "root":
        raise OrchestrationError("only the root orchestrator may apply human control transitions")
    action = control.get("action")
    if action not in {"pause", "resume", "cancel", "redirect", "resolve_decision", "resolve_blocker", "update_scopes", "authorize_delegation"}:
        raise OrchestrationError(f"unsupported control action: {action}")
    raw_ids = control.get("task_ids", [])
    if not isinstance(raw_ids, list):
        raise OrchestrationError("control task_ids must be an array")
    targets = [str(task_id) for task_id in raw_ids]
    unknown = set(targets) - set(state["nodes"])
    if unknown:
        raise OrchestrationError(f"control references unknown tasks: {sorted(unknown)}")
    if action == "pause":
        state["status"] = "paused"
    elif action == "resume":
        state["status"] = "running"
        for task_id in targets:
            node = state["nodes"][task_id]
            if control.get("clear_blockers", False):
                node["blockers"] = []
                state["external_blockers"] = [item for item in state["external_blockers"] if item.get("task_id") != task_id]
            if node["status"] in {"running", "waiting", "blocked", "partial", "repair", "review"} and not node["blockers"] and not node["decisions"]:
                node["status"] = "queued"
    elif action == "cancel":
        selected = targets or [
            node["id"] for node in state["nodes"].values()
            if node["id"] != state["task_id"] and node["status"] not in {"complete", "failed", "cancelled"}
        ]
        for task_id in selected:
            state["nodes"][task_id]["status"] = "cancelled"
        if not targets:
            state["status"] = "cancelled"
    elif action == "redirect":
        for task_id in targets:
            if state["nodes"][task_id]["status"] != "complete":
                state["nodes"][task_id]["status"] = "cancelled"
                state["nodes"][task_id]["superseded"] = True
        profiles = control.get("profiles", [])
        if not isinstance(profiles, list) or not profiles:
            raise OrchestrationError("redirect requires one or more re-profiled replacement nodes")
        created = _add_discovered(state, state["nodes"][state["task_id"]], profiles)
        state["status"] = "running"
        control = {**control, "created": created}
    elif action == "resolve_decision":
        for task_id in targets:
            state["nodes"][task_id]["decisions"] = []
            if state["nodes"][task_id]["status"] == "waiting" and not state["nodes"][task_id]["blockers"]:
                state["nodes"][task_id]["status"] = "queued"
        state["outstanding_human_decisions"] = [item for item in state["outstanding_human_decisions"] if item.get("task_id") not in targets]
    elif action == "resolve_blocker":
        for task_id in targets:
            state["nodes"][task_id]["blockers"] = []
            if state["nodes"][task_id]["status"] == "blocked" and not state["nodes"][task_id]["decisions"]:
                state["nodes"][task_id]["status"] = "queued"
        state["external_blockers"] = [item for item in state["external_blockers"] if item.get("task_id") not in targets]
    elif action == "update_scopes":
        if len(targets) != 1:
            raise OrchestrationError("update_scopes requires exactly one task_id")
        node = state["nodes"][targets[0]]
        for field in ("read_scopes", "write_scopes"):
            if field in control:
                scopes = control[field]
                if not isinstance(scopes, list) or not all(isinstance(item, str) and item for item in scopes):
                    raise OrchestrationError(f"{field} must be an array of non-empty strings")
                node[field] = list(scopes)
        node["read_only"] = bool(control.get("read_only", node["read_only"]))
        if node["read_only"] and node["write_scopes"]:
            raise OrchestrationError("read-only nodes cannot declare write scopes")
    else:
        if len(targets) != 1:
            raise OrchestrationError("authorize_delegation requires exactly one task_id")
        capability = control.get("capability")
        try:
            validate_delegation_capability(capability)
        except ContractError as error:
            raise OrchestrationError(f"invalid delegation capability: {error}") from error
        node = state["nodes"][targets[0]]
        route = node.get("route_history", [])[-1:] or [None]
        role = load_role_inventory().get(route[0]) if route[0] else None
        if capability["allowed"] and (role is None or not role.may_delegate):
            raise OrchestrationError("delegation capability may only be attached to a delegation-capable routed owner")
        node["delegation"] = _json_copy(capability)
    _record(state, f"control-{action}", None, _json_copy(control))
    _refresh_ready(state)
    _automatic_ledger_triggers(state)
    return state


def _validate_event(state: dict[str, Any], event: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        validate_child_event(event)
    except ContractError as error:
        errors.append(str(error))
    for field in ("task_id", "node_id"):
        try:
            _uuid(event.get(field))
        except OrchestrationError as error:
            errors.append(str(error))
    if event.get("task_id") != state["task_id"]:
        errors.append("event task_id must equal the root orchestration task_id")
    node = state.get("nodes", {}).get(event.get("node_id"))
    review = event.get("review") if isinstance(event.get("review"), dict) else {}
    if node is not None and node["review"]["required"] and review.get("status") in {"passed", "failed"}:
        prior_result = node.get("result") if isinstance(node.get("result"), dict) else {}
        implementation_path = prior_result.get("agent_path")
        review_path = event.get("agent_path")
        if node["status"] != "review" or not implementation_path or review_path == implementation_path:
            errors.append(
                "mandatory review result must follow implementation and come from an independent agent_path"
            )
    return errors


def _add_discovered(state: dict[str, Any], parent: dict[str, Any], profiles: Iterable[dict[str, Any]]) -> list[str]:
    capability = parent.get("delegation", {"allowed": False})
    root_owned = parent["id"] == state["task_id"]
    if not root_owned:
        try:
            validate_delegation_capability(capability)
        except ContractError as error:
            raise OrchestrationError(f"invalid delegation capability: {error}") from error
        if not capability["allowed"] or capability["remaining_depth"] < 1:
            raise OrchestrationError("delegation capability does not authorize discovered descendants")
    created: list[str] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            raise OrchestrationError("discovered work entries must be objects")
        if parent["depth"] + 1 > state["budgets"]["max_depth"]:
            raise OrchestrationError("discovered work exceeds max depth")
        if len(_children(state, parent["id"])) >= state["budgets"]["max_children_per_node"]:
            raise OrchestrationError("discovered work exceeds max children")
        if not root_owned and len(_children(state, parent["id"])) >= capability["max_children"]:
            raise OrchestrationError("discovered work exceeds delegated child budget")
        if len(state["nodes"]) - 1 >= state["budgets"]["max_total_spawns"]:
            raise OrchestrationError("discovered work exceeds total spawn budget")
        if not root_owned:
            route = profile.get("route_decision", {}).get("primary", profile.get("route", {}))
            agent = route.get("agent") if isinstance(route, dict) else None
            model = route.get("model") if isinstance(route, dict) else None
            if agent not in capability["allowed_roles"] or model not in capability["allowed_models"]:
                raise OrchestrationError("discovered route exceeds delegated role or model authority")
            role = load_role_inventory().get(agent)
            if role is None or role.model != model:
                raise OrchestrationError("discovered route does not match the canonical role inventory")
            proposed_scopes = profile.get("write_scopes", [])
            if (proposed_scopes or not role.read_only) and not capability["may_spawn_writers"]:
                raise OrchestrationError("delegation capability forbids writer descendants")
            if any(scope not in capability["allowed_write_scopes"] for scope in proposed_scopes):
                raise OrchestrationError("discovered write scope exceeds delegation capability")
        task_id = _uuid(profile.get("task_id") or profile.get("id"))
        if task_id in state["nodes"]:
            raise OrchestrationError(f"duplicate discovered task: {task_id}")
        node = _new_node(profile, task_id=task_id, parent_id=parent["id"], depth=parent["depth"] + 1)
        unknown = set(node["dependencies"]) - set(state["nodes"])
        if unknown:
            raise OrchestrationError(f"unknown discovered dependencies: {sorted(unknown)}")
        state["nodes"][task_id] = node
        created.append(task_id)
    return created


def apply_event(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Apply a child event and deterministically transition its graph node."""
    state = _json_copy(state)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise OrchestrationError("unsupported orchestration schema version")
    event = _json_copy(event)
    task_id = event.get("node_id")
    node = state.get("nodes", {}).get(task_id)
    if node is None:
        raise OrchestrationError(f"event references unknown task: {task_id}")
    errors = _validate_event(state, event)
    if errors:
        if node["normalization_attempts"] < MAX_NORMALIZATION_ATTEMPTS:
            node["normalization_attempts"] += 1
            node["status"] = "waiting"
            _record(state, "normalization-required", task_id, {"attempt": 1, "errors": errors})
        else:
            node["status"] = "failed"
            node["blockers"].append({"kind": "invalid-event", "errors": errors})
            _record(state, "normalization-exhausted", task_id, {"errors": errors})
        _refresh_ready(state)
        _automatic_ledger_triggers(state)
        return state

    event_type = event["event_type"]
    event_review = event.get("review", {})
    node["review"]["required"] = node["review"]["required"] or bool(event_review.get("required"))
    if event_review.get("status") in {"passed", "failed"}:
        node["review"]["findings"] = _json_copy(event_review.get("findings", []))
    else:
        node["review"]["findings"].extend(event_review.get("findings", []))
    node["review"]["status"] = event_review.get("status", node["review"].get("status", "pending"))
    if event_review.get("status") == "passed":
        node["review"]["complete"] = not _unresolved_review_findings(node)
    validation = event.get("validation", [])
    if validation:
        node["validation"]["records"].extend(validation)
        statuses = {record.get("status") for record in validation if isinstance(record, dict)}
        node["validation"]["passed"] = bool(statuses) and statuses <= {"passed", "skipped"} and "passed" in statuses
    discovered = event.get("discovered_work", [])
    created: list[str] = []
    if discovered:
        try:
            trial = _json_copy(state)
            created = _add_discovered(trial, trial["nodes"][task_id], discovered)
            state["nodes"] = trial["nodes"]
            node = state["nodes"][task_id]
        except OrchestrationError as error:
            event.setdefault("undispatched_work", []).extend(discovered)
            node["blockers"].append({"kind": "delegation-or-budget", "reason": str(error)})
    node["result"] = _json_copy(event)

    if event_type == "progress":
        node["status"] = "running"
    elif event_type == "complete":
        node["outcomes_satisfied"] = True
        if node["validation"]["required"] and node["validation"]["passed"] is not True:
            node["status"] = "waiting"
            node["blockers"].append({"kind": "validation", "reason": "required validation has not passed"})
        elif node["review"]["required"] and not node["review"]["complete"]:
            node["status"] = "review"
        else:
            node["status"] = "complete"
    elif event_type in {"partial", "budget_exhausted"}:
        node["status"] = "partial"
    elif event_type == "new_work":
        node["awaiting_children"] = bool(created)
        node["status"] = "waiting" if created else "partial"
    elif event_type == "needs_decision":
        # Autonomous mode resolves semantic choices at the root and retries the
        # node with the recorded choice. A child should normally decide itself;
        # this transition is a compatibility path for older/malformed prompts.
        questions = event.get("questions") or [{"summary": event.get("summary", "")}]
        decisions = []
        for item in questions:
            question = item if isinstance(item, dict) else {"question": str(item)}
            resolution = question.get("recommendation") or question.get("default") or (
                "Use the safest reversible in-scope option supported by current evidence."
            )
            decisions.append({**question, "resolution": resolution, "resolved_by": "root-autonomy"})
        node["resolved_decisions"].extend(decisions)
        node["status"] = "queued"
        _record(state, "semantic-decision-auto-resolved", task_id, {"decisions": decisions})
    elif event_type == "approval_required":
        # Router-authored approvals are forbidden by the child prompt. Preserve
        # only a real host/tool approval as an external blocker with provenance.
        node["status"] = "blocked"
        approvals = event.get("questions") or [{"summary": event.get("summary", "")}]
        for item in approvals:
            approval = item if isinstance(item, dict) else {"summary": str(item)}
            blocker = {"task_id": task_id, "kind": "host-approval-required", **approval}
            node["blockers"].append(blocker)
            state["external_blockers"].append(blocker)
    elif event_type == "risk_discovered":
        node["review"]["required"] = True
        node["status"] = "review"
    elif event_type == "validation_failed":
        node["validation"]["passed"] = False
        if node["repair_cycles"] < MAX_REPAIR_CYCLES:
            node["repair_cycles"] += 1
            node["status"] = "repair"
        else:
            node["status"] = "blocked"
            node["blockers"].append({"kind": "repair-cap", "reason": "two review-repair cycles exhausted"})
    elif event_type == "blocked":
        node["status"] = "blocked"
        reported = event.get("blockers") or [{"summary": event.get("summary", "")}]
        for item in reported:
            blocker = {"task_id": task_id, **(item if isinstance(item, dict) else {"summary": str(item)})}
            blocker.setdefault("summary", event.get("summary", ""))
            node["blockers"].append(blocker)
            state["external_blockers"].append(blocker)
    elif event_type == "conflict":
        node["status"] = "blocked"
        node["blockers"].append({"kind": "conflict", "summary": event.get("summary", "")})
    elif event_type == "cancelled":
        node["status"] = "cancelled"
    elif event_type == "failed":
        node["status"] = "failed"

    if event_review.get("status") == "passed" and node["review"]["complete"]:
        if node["outcomes_satisfied"] and (not node["validation"]["required"] or node["validation"]["passed"]):
            node["status"] = "complete"
    _record(state, f"child-{event_type}", task_id, {"created": created})
    _refresh_ready(state)
    _automatic_ledger_triggers(state)
    return state


def _automatic_ledger_triggers(state: dict[str, Any]) -> list[str]:
    triggers: list[str] = []
    if len(state["nodes"]) > 3:
        triggers.append("graph-over-three-nodes")
    if any(node.get("delegation", {}).get("allowed") for node in state["nodes"].values()):
        triggers.append("recursive-delegation")
    if any(event["trigger"] == "child-complete" for event in state["events"]) and any(node["status"] == "ready" for node in state["nodes"].values()):
        triggers.append("second-wave")
    if any(node["status"] in {"blocked", "waiting"} for node in state["nodes"].values()):
        triggers.append("pause-or-block")
    if state.get("resumable"):
        triggers.append("explicit-resumability")
    existing = state["ledger"].setdefault("triggered_by", [])
    for trigger in triggers:
        if trigger not in existing:
            existing.append(trigger)
    if triggers:
        state["ledger"]["required"] = True
        if not state["ledger"].get("path"):
            state["ledger"]["path"] = str(
                Path(state["workspace_root"]) / ".codex" / "gpt56-router" / f"{state['task_id']}.json"
            )
    return triggers


def _unresolved_review_findings(node: dict[str, Any]) -> list[Any]:
    unresolved: list[Any] = []
    for finding in node.get("review", {}).get("findings", []):
        if isinstance(finding, dict):
            resolved = finding.get("resolved") is True or finding.get("status") in {"resolved", "closed", "dismissed"}
        else:
            resolved = False
        if not resolved:
            unresolved.append(finding)
    return unresolved


def status(state: dict[str, Any]) -> dict[str, Any]:
    counts = {name: 0 for name in sorted(NODE_STATUSES)}
    for node in state["nodes"].values():
        counts[node["status"]] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": state["task_id"],
        "status": state["status"],
        "counts": counts,
        "usage": _json_copy(state["usage"]),
        "ready": ready(state)["ready"],
        "decisions": _json_copy(state["outstanding_human_decisions"]),
        "blockers": _json_copy(state["external_blockers"]),
        "warnings": _json_copy(state["warnings"]),
        "task_graph": task_graph_record(state),
    }


def task_graph_record(state: dict[str, Any]) -> dict[str, Any]:
    """Project internal orchestration state into the public task-graph contract."""
    remaining_review = [
        node["id"]
        for node in state["nodes"].values()
        if node["review"]["required"] and not node["review"]["complete"]
    ]
    record = {
        "schema_version": SCHEMA_VERSION,
        "root_task_id": state["task_id"],
        "authority_envelope": _json_copy(state.get("authority_envelope", {})),
        "budgets": _json_copy(state["budgets"]),
        "nodes": [
            {
                "task_id": node["id"],
                "status": node["status"],
                "dependencies": _json_copy(node["dependencies"]),
                "route_history": _json_copy(node["route_history"]),
                "required_review": bool(node["review"]["required"]),
            }
            for node in state["nodes"].values()
        ],
        "outstanding_human_decisions": _json_copy(state["outstanding_human_decisions"]),
        "external_blockers": _json_copy(state["external_blockers"]),
        "remaining_review": remaining_review,
    }
    validate_task_graph(record)
    return record


def complete_check(state: dict[str, Any], actor: str) -> dict[str, Any]:
    """Evaluate the root-only, deterministic completion gate."""
    if actor != "root":
        raise OrchestrationError("only the root orchestrator may run the completion gate")
    unmet: list[dict[str, Any]] = []
    child_nodes = [
        node for node in state["nodes"].values()
        if node["id"] != state["task_id"] and not node.get("superseded", False)
    ]
    gate_nodes = child_nodes or [state["nodes"][state["task_id"]]]
    for node in gate_nodes:
        if node["status"] != "complete":
            unmet.append({"task_id": node["id"], "gate": f"status:{node['status']}"})
        if not node["outcomes_satisfied"]:
            unmet.append({"task_id": node["id"], "gate": "outcomes-not-satisfied"})
        if node["validation"]["required"] and node["validation"]["passed"] is not True:
            unmet.append({"task_id": node["id"], "gate": "validation-not-passed"})
        if node["review"]["required"] and not node["review"]["complete"]:
            unmet.append({"task_id": node["id"], "gate": "review-not-complete"})
        for finding in _unresolved_review_findings(node):
            unmet.append({"task_id": node["id"], "gate": "unresolved-review-finding", "finding": finding})
        if node["blockers"]:
            unmet.append({"task_id": node["id"], "gate": "unresolved-blockers"})
        if node["decisions"]:
            unmet.append({"task_id": node["id"], "gate": "unresolved-decisions"})
    if state["outstanding_human_decisions"]:
        unmet.append({"task_id": state["task_id"], "gate": "outstanding-human-decisions"})
    if state["external_blockers"]:
        unmet.append({"task_id": state["task_id"], "gate": "external-blockers"})
    complete = not unmet
    open_statuses = {"queued", "ready", "running", "waiting", "blocked", "review", "repair"}
    open_nodes = [
        node["id"] for node in state["nodes"].values()
        if node["id"] != state["task_id"] and node["status"] in open_statuses
    ]
    residual_risks = [
        risk
        for node in state["nodes"].values()
        for risk in ((node.get("result") or {}).get("risks", []))
    ]
    routes_used = list(dict.fromkeys(
        route
        for node in state["nodes"].values()
        for route in node.get("route_history", [])
    ))
    return {
        "schema_version": SCHEMA_VERSION,
        "root_task_id": state["task_id"],
        "status": "complete" if complete else "partial",
        "complete": complete,
        "requested_outcomes_satisfied": complete,
        "validation_passed": not any(item["gate"] == "validation-not-passed" for item in unmet),
        "required_reviews_complete": not any(item["gate"] == "review-not-complete" for item in unmet),
        "unresolved_findings": _json_copy(unmet),
        "ready_or_running_nodes": open_nodes,
        "external_actions_taken": [],
        "residual_risks": residual_risks,
        "routes_used": routes_used,
        "unmet_gates": unmet,
    }


def load_json(path: Path | None) -> dict[str, Any]:
    text = path.read_text() if path else sys.stdin.read()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        # A ledger is JSONL; its last snapshot is authoritative.
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        if not records:
            raise OrchestrationError("JSON input is empty") from error
        value = records[-1].get("state", records[-1])
    if not isinstance(value, dict):
        raise OrchestrationError("JSON input must be an object")
    if set(value) == {"sequence", "state"} and isinstance(value["state"], dict):
        value = value["state"]
    return value


def _atomic_replace(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def persist(state: dict[str, Any], path: Path, *, required: bool = True) -> dict[str, Any]:
    """Atomically persist a state/ledger; warn only when fallback is explicit."""
    state = _json_copy(state)
    is_ledger = path.suffix == ".jsonl"
    if is_ledger:
        prior = path.read_text() if path.exists() else ""
        record = json.dumps({"sequence": len(state["events"]), "state": state}, sort_keys=True)
        payload = prior + ("" if not prior or prior.endswith("\n") else "\n") + record + "\n"
    else:
        payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
    try:
        _atomic_replace(path, payload)
    except OSError as error:
        message = f"durability update failed for {path}: {error}"
        if required:
            raise DurabilityError(message) from error
        state["warnings"].append({"kind": "durability", "message": message})
    return state


@contextmanager
def ledger_lock(path: Path) -> Iterable[None]:
    """Serialize each ledger read-modify-write transaction across processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init")
    init.add_argument("--input", type=Path)
    init.add_argument("--ledger", type=Path)
    init.add_argument("--json", action="store_true", help="emit JSON (the only supported output format)")
    for name in ("ready", "dispatch", "status", "complete-check"):
        command = subparsers.add_parser(name)
        command.add_argument("--state", type=Path)
        command.add_argument("--ledger", type=Path)
        command.add_argument("--json", action="store_true", help="emit JSON (the only supported output format)")
        if name == "complete-check":
            command.add_argument("--actor", default="root")
    apply = subparsers.add_parser("apply-event")
    apply.add_argument("--state", type=Path)
    apply.add_argument("--ledger", type=Path)
    apply.add_argument("--event", type=Path)
    apply.add_argument("--durability", choices=("required", "warning"), default="required")
    apply.add_argument("--json", action="store_true", help="emit JSON (the only supported output format)")
    control = subparsers.add_parser("control")
    control.add_argument("--state", type=Path)
    control.add_argument("--ledger", type=Path)
    control.add_argument("--control", type=Path)
    control.add_argument("--durability", choices=("required", "warning"), default="required")
    control.add_argument("--json", action="store_true", help="emit JSON (the only supported output format)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            state = initialize(load_json(args.input), str(args.ledger) if args.ledger else None)
            destination = args.ledger or (Path(state["ledger"]["path"]) if state["ledger"].get("path") else None)
            if destination:
                state = persist(state, destination, required=bool(state["ledger"].get("explicit")))
            result: dict[str, Any] = {"state": state, "task_graph": task_graph_record(state)}
        else:
            source = args.state or args.ledger
            preloaded_mutation: dict[str, Any] | None = None
            if source is not None and args.command == "apply-event":
                preloaded_mutation = load_json(args.event) if args.event else load_json(None)
            elif source is not None and args.command == "control":
                preloaded_mutation = load_json(args.control) if args.control else load_json(None)

            def execute() -> dict[str, Any]:
                if source is None:
                    envelope = load_json(None)
                    state = envelope.get("state", envelope)
                else:
                    envelope = None
                    state = load_json(source)
                if args.command == "apply-event":
                    if preloaded_mutation is not None:
                        event = preloaded_mutation
                    elif args.event:
                        event = load_json(args.event)
                    elif envelope and isinstance(envelope.get("event"), dict):
                        event = envelope["event"]
                    else:
                        event = load_json(None)
                    if not isinstance(event, dict):
                        raise OrchestrationError("apply-event requires an event object")
                    next_state = apply_event(state, event)
                    destination = args.state or args.ledger or (Path(next_state["ledger"]["path"]) if next_state["ledger"].get("path") else None)
                    if destination:
                        required = args.durability == "required" and bool(args.state or args.ledger or next_state["ledger"].get("explicit"))
                        next_state = persist(next_state, destination, required=required)
                    return next_state
                if args.command == "control":
                    if preloaded_mutation is not None:
                        control_input = preloaded_mutation
                    elif args.control:
                        control_input = load_json(args.control)
                    elif envelope and isinstance(envelope.get("control"), dict):
                        control_input = envelope["control"]
                    else:
                        control_input = load_json(None)
                    next_state = apply_control(state, control_input)
                    destination = args.state or args.ledger or (Path(next_state["ledger"]["path"]) if next_state["ledger"].get("path") else None)
                    if destination:
                        required = args.durability == "required" and bool(args.state or args.ledger or next_state["ledger"].get("explicit"))
                        next_state = persist(next_state, destination, required=required)
                    return next_state
                if args.command == "dispatch":
                    next_state, wave = dispatch(state)
                    destination = args.state or args.ledger or (Path(next_state["ledger"]["path"]) if next_state["ledger"].get("path") else None)
                    if destination:
                        next_state = persist(next_state, destination, required=bool(args.state or args.ledger or next_state["ledger"].get("explicit")))
                    return {**wave, "state": next_state}
                if args.command == "ready":
                    return ready(state)
                if args.command == "status":
                    return status(state)
                return complete_check(state, args.actor)

            if source is not None and args.command in {"apply-event", "control", "dispatch"}:
                with ledger_lock(source):
                    result = execute()
            else:
                result = execute()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OrchestrationError, DurabilityError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
