#!/usr/bin/env python3
"""Verify a routed subagent from persisted Codex rollout metadata."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


ROUTING_MODES = ("custom-agent", "model-override")


def object_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def spawn_metadata(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    source = object_value(payload.get("source"))
    subagent = object_value(source.get("subagent"))
    return object_value(subagent.get("thread_spawn"))


def load_inventory() -> Mapping[str, Any]:
    """Load the canonical role inventory without duplicating routing policy."""
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


def role_value(role: Any, *names: str) -> Any:
    for name in names:
        value = role.get(name) if isinstance(role, Mapping) else getattr(role, name, None)
        if value is not None:
            return value
    return None


def parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "timestamp must be ISO 8601, for example 2026-07-19T10:48:25Z"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-path", required=True)
    parser.add_argument("--not-before", required=True, type=parse_timestamp)
    parser.add_argument("--expected-agent", required=True)
    parser.add_argument("--routing-mode", choices=ROUTING_MODES, required=True)
    parser.add_argument("--thread-id", help="Optional child thread ID cross-check.")
    parser.add_argument("--parent-thread-id", help="Expected parent thread provenance.")
    parser.add_argument("--task-name", help="Unique task name used in the parent spawn request.")
    parser.add_argument("--expected-fork-turns", help="Expected fork_turns value from the parent spawn request.")
    parser.add_argument("--expected-depth", type=int)
    parser.add_argument("--expected-sandbox")
    parser.add_argument(
        "--sessions-root",
        action="append",
        type=Path,
        help="Override a rollout search root; may be supplied more than once.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def default_roots() -> list[Path]:
    codex_home = Path.home() / ".codex"
    return [codex_home / "sessions", codex_home / "archived_sessions"]


def expected_depth_for_path(agent_path: str) -> int:
    components = [component for component in agent_path.split("/") if component]
    if not components or components[0] != "root":
        raise ValueError("agent path must be rooted at /root")
    return len(components) - 1


def iter_rollouts(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.exists():
            yield from root.rglob("*.jsonl")


def read_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open() as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {error}") from error
            if isinstance(record, dict):
                records.append(record)
    return records


def read_session_meta(path: Path) -> dict[str, Any] | None:
    """Read only through session metadata while screening rollout candidates."""
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return None
            if isinstance(record, dict) and record.get("type") == "session_meta":
                return record
    return None


def find_session_rollout(thread_id: str, roots: Iterable[Path]) -> Path | None:
    matches: list[tuple[float, Path]] = []
    for path in iter_rollouts(roots):
        try:
            record = read_session_meta(path)
        except OSError:
            continue
        if record is None:
            continue
        if object_value(record.get("payload")).get("id") == thread_id:
            matches.append((path.stat().st_mtime, path))
    if not matches:
        return None
    return max(matches, key=lambda match: match[0])[1]


def spawn_request_input(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if payload.get("type") not in ("custom_tool_call", "function_call"):
        return None
    name = payload.get("name")
    if not isinstance(name, str) or not name.endswith("spawn_agent"):
        return None
    raw = payload.get("input") if "input" in payload else payload.get("arguments")
    if isinstance(raw, Mapping):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def find_spawn_request(
    records: Iterable[Mapping[str, Any]],
    *,
    task_name: str,
    not_before: datetime,
) -> tuple[Mapping[str, Any] | None, str | None]:
    matches: list[Mapping[str, Any]] = []
    for record in records:
        if record.get("type") != "response_item":
            continue
        timestamp = metadata_timestamp(record)
        if timestamp is None or timestamp < not_before:
            continue
        request = spawn_request_input(object_value(record.get("payload")))
        if request is not None and request.get("task_name") == task_name:
            matches.append(request)
    if not matches:
        return None, "matching parent spawn request not found"
    if len(matches) > 1:
        return None, "multiple matching parent spawn requests found"
    return matches[0], None


def metadata_timestamp(record: Mapping[str, Any]) -> datetime | None:
    payload = object_value(record.get("payload"))
    raw = payload.get("timestamp") or record.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return parse_timestamp(raw)
    except argparse.ArgumentTypeError:
        return None


def find_rollout(
    agent_path: str,
    not_before: datetime,
    roots: Iterable[Path],
    thread_id: str | None = None,
) -> tuple[Path, list[dict[str, Any]]] | None:
    matches: list[tuple[datetime, float, Path]] = []
    for path in iter_rollouts(roots):
        try:
            record = read_session_meta(path)
        except OSError:
            continue
        if record is None:
            continue
        payload = object_value(record.get("payload"))
        spawn = spawn_metadata(payload)
        if spawn.get("agent_path") != agent_path:
            continue
        child_id = payload.get("id")
        if thread_id is not None and child_id != thread_id:
            continue
        timestamp = metadata_timestamp(record)
        if timestamp is None or timestamp < not_before:
            continue
        matches.append((timestamp, path.stat().st_mtime, path))
    if not matches:
        return None
    _, _, path = max(matches, key=lambda match: (match[0], match[1]))
    return path, read_records(path)


def load_runtime(path: Path, records: list[dict[str, Any]], agent_path: str) -> dict[str, Any]:
    session_meta: dict[str, Any] | None = None
    turn_context: dict[str, Any] | None = None
    for record in records:
        if record.get("type") == "session_meta":
            payload = object_value(record.get("payload"))
            spawn = spawn_metadata(payload)
            if spawn.get("agent_path") == agent_path:
                session_meta = payload
        elif record.get("type") == "turn_context":
            turn_context = dict(object_value(record.get("payload")))

    if session_meta is None:
        raise ValueError(f"rollout does not contain session metadata for {agent_path}")
    spawn = spawn_metadata(session_meta)
    context = turn_context or {}
    sandbox = context.get("sandbox_policy") or {}
    parent_in_meta = session_meta.get("parent_thread_id")
    parent_in_spawn = spawn.get("parent_thread_id")
    return {
        "rollout_path": str(path),
        "thread_id": session_meta.get("id"),
        "agent_path": spawn.get("agent_path"),
        "parent_thread_id": parent_in_spawn or parent_in_meta,
        "parent_provenance_consistent": bool(parent_in_meta)
        and parent_in_meta == parent_in_spawn,
        "agent_role": spawn.get("agent_role"),
        "model": context.get("model"),
        "effort": context.get("effort") or context.get("reasoning_effort"),
        "depth": spawn.get("depth"),
        "sandbox": sandbox.get("type") if isinstance(sandbox, Mapping) else sandbox,
    }


def inspect(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {
        "ok": False,
        "rollout_path": None,
        "thread_id": args.thread_id,
        "agent_path": args.agent_path,
        "parent_thread_id": None,
        "parent_rollout_path": None,
        "agent_role": None,
        "expected_agent": args.expected_agent,
        "model": None,
        "expected_model": None,
        "effort": None,
        "expected_effort": None,
        "depth": None,
        "expected_depth": args.expected_depth,
        "sandbox": None,
        "expected_sandbox": args.expected_sandbox,
        "task_name": args.task_name,
        "fork_turns": None,
        "expected_fork_turns": args.expected_fork_turns,
        "routing_mode": args.routing_mode,
        "failure_reasons": [],
    }
    try:
        inventory = load_inventory()
        role = inventory[args.expected_agent]
    except KeyError:
        result["failure_reasons"] = ["unknown expected agent"]
        return result, 2
    except RuntimeError as error:
        result["failure_reasons"] = [str(error)]
        return result, 2

    expected_model = role_value(role, "model")
    expected_effort = role_value(role, "reasoning_effort", "effort", "model_reasoning_effort")
    expected_depth = args.expected_depth
    if expected_depth is None:
        try:
            expected_depth = expected_depth_for_path(args.agent_path)
        except ValueError as error:
            result["failure_reasons"] = [str(error)]
            return result, 2
    expected_sandbox = args.expected_sandbox
    if args.expected_fork_turns is not None:
        if args.expected_fork_turns not in ("none", "all") and not args.expected_fork_turns.isdigit():
            result["failure_reasons"] = ["expected fork mode must be none, all, or a turn count"]
            return result, 2
        if args.task_name is None or args.parent_thread_id is None:
            result["failure_reasons"] = [
                "fork verification requires both task name and parent thread ID"
            ]
            return result, 2

    result.update(
        expected_model=expected_model,
        expected_effort=expected_effort,
        expected_depth=expected_depth,
        expected_sandbox=expected_sandbox,
    )
    found = find_rollout(args.agent_path, args.not_before, args.sessions_root or default_roots(), args.thread_id)
    if found is None:
        result["failure_reasons"] = ["fresh rollout not found for agent path"]
        return result, 2
    path, records = found
    try:
        runtime = load_runtime(path, records, args.agent_path)
    except ValueError as error:
        result["failure_reasons"] = [str(error)]
        return result, 2
    result.update({key: value for key, value in runtime.items() if key != "parent_provenance_consistent"})

    if args.expected_fork_turns is not None:
        parent_path = find_session_rollout(args.parent_thread_id, args.sessions_root or default_roots())
        if parent_path is None:
            result["failure_reasons"] = ["parent rollout not found for fork verification"]
            return result, 2
        try:
            parent_records = read_records(parent_path)
        except (OSError, ValueError) as error:
            result["failure_reasons"] = [str(error)]
            return result, 2
        request, request_error = find_spawn_request(
            parent_records,
            task_name=args.task_name,
            not_before=args.not_before,
        )
        if request_error is not None or request is None:
            result["failure_reasons"] = [request_error or "matching parent spawn request not found"]
            return result, 2
        result["parent_rollout_path"] = str(parent_path)
        result["fork_turns"] = request.get("fork_turns")

    role_ok = (
        runtime["agent_role"] == args.expected_agent
        if args.routing_mode == "custom-agent"
        else runtime["agent_role"] is None
    )
    role_failure = (
        "agent role did not match expected agent"
        if args.routing_mode == "custom-agent"
        else "model-override route unexpectedly applied a custom agent role"
    )
    checks = [
        (role_failure, role_ok),
        ("model did not match expected pinned model", runtime["model"] == expected_model),
        ("reasoning effort did not match expected pinned effort", runtime["effort"] == expected_effort),
        ("spawn depth did not match expected depth", runtime["depth"] == expected_depth),
        ("parent provenance was missing or inconsistent", runtime["parent_provenance_consistent"]),
    ]
    if args.thread_id is not None:
        checks.append(("thread ID did not match expected child thread", runtime["thread_id"] == args.thread_id))
    if args.parent_thread_id is not None:
        checks.append(("parent thread ID did not match expected parent", runtime["parent_thread_id"] == args.parent_thread_id))
    if expected_sandbox is not None:
        checks.append(("sandbox did not match expected sandbox", runtime["sandbox"] == expected_sandbox))
    if args.expected_fork_turns is not None:
        checks.append(("fork mode did not match expected value", result["fork_turns"] == args.expected_fork_turns))
    result["failure_reasons"] = [reason for reason, passed in checks if not passed]
    result["ok"] = not result["failure_reasons"]
    return result, 0 if result["ok"] else 1


def main() -> int:
    args = parse_args()
    result, status = inspect(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print(
            f"agent_path={result['agent_path']} thread_id={result['thread_id']} "
            f"agent_role={result['agent_role']} model={result['model']} "
            f"effort={result['effort']} depth={result['depth']} sandbox={result['sandbox']}"
        )
    else:
        print("; ".join(result["failure_reasons"]))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
