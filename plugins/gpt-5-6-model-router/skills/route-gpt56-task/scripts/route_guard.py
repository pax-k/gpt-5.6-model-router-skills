#!/usr/bin/env python3
"""Prepare governed routes, enforce Codex hook events, and audit router turns."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

if sys.version_info < (3, 9):
    print("GPT-5.6 Model Router requires Python 3.9 or newer", file=sys.stderr)
    raise SystemExit(2)

from route_task import recommend
from router_contract import (
    ContractError,
    PRIVILEGED_AUTHORITIES,
    canonical_sha256,
    load_json_input,
    load_role_inventory,
    validate_route_intent,
)


ROUTER_TOKEN = "$route-gpt56-task"
ROUTER_INVOCATION = re.compile(r"(?<![A-Za-z0-9_-])\$route-gpt56-task(?![A-Za-z0-9_-])")
STATE_SCHEMA = 1
STATE_RETENTION_DAYS = 30
STATE_MAX_COMPLETED = 1000
CUSTOM_AGENT_LIMIT = 6000
MODEL_OVERRIDE_LIMIT = 8000
FORBIDDEN_LABELS = (
    "source_files:",
    "parent_conversation:",
    "agents_md:",
    "repository_documentation:",
    "full_diff:",
    "raw_logs:",
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}=*\b", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:api[_-]?key|secret|token)\s*[:=]\s*[\"']?[A-Za-z0-9._~+/-]{20,}", re.IGNORECASE),
)
COMMIT_COMMAND = re.compile(
    r"(?:^|[;&|\n]\s*)(?:env\s+[^;&|\n]+\s+)?(?:command\s+|sudo\s+)?git"
    r"(?:\s+(?:-C\s+\S+|-c\s+\S+|--git-dir(?:=|\s+)\S+|--work-tree(?:=|\s+)\S+))*"
    r"\s+(?:commit|tag|push)\b",
    re.IGNORECASE,
)
INTENT_LINE = re.compile(r"^Router-Intent:\s*([a-f0-9-]{36})\s*$", re.MULTILINE)
RESULT_LINE = re.compile(r"^Router-Result:\s*(\{.*\})\s*$", re.MULTILINE)
REVIEW_LINE = re.compile(r"^Router-Review:\s*(\{.*\})\s*$", re.MULTILINE)
EFFORT_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "xhigh": 4, "max": 5}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_text(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def _id_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _state_path(root: Path, session_id: str, turn_id: str) -> Path:
    return root / _id_hash(session_id) / _id_hash(turn_id) / "state.json"


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _with_lock(path: Path, callback: Callable[[dict[str, Any]], Any]) -> Any:
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    for _ in range(200):
        try:
            descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 30:
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            time.sleep(0.01)
    if descriptor is None:
        raise ContractError("router state lock timed out")
    try:
        os.close(descriptor)
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ContractError(f"router state is unreadable: {error}") from error
            if not isinstance(state, dict) or state.get("state_schema") != STATE_SCHEMA:
                raise ContractError("router state schema is unsupported")
        else:
            state = {}
        result = callback(state)
        _atomic_write(path, state)
        return result
    finally:
        lock.unlink(missing_ok=True)


def _prune(root: Path) -> None:
    if not root.exists():
        return
    cutoff = time.time() - STATE_RETENTION_DAYS * 86400
    completed: list[Path] = []
    for path in root.glob("*/*/state.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state.get("completed_at"):
                completed.append(path)
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            continue
    remaining = sorted((path for path in completed if path.exists()), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in remaining[STATE_MAX_COMPLETED:]:
        path.unlink(missing_ok=True)


def _load_state(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) and value.get("state_schema") == STATE_SCHEMA else None


def _find_active_state(root: Path, session_id: str, turn_id: str | None) -> tuple[Path, dict[str, Any]] | None:
    if turn_id:
        exact = _state_path(root, session_id, turn_id)
        state = _load_state(exact)
        if state and state.get("active") and not state.get("completed_at"):
            return exact, state
    session = root / _id_hash(session_id)
    matches: list[tuple[float, Path, dict[str, Any]]] = []
    for path in session.glob("*/state.json") if session.exists() else ():
        state = _load_state(path)
        if state and state.get("active") and not state.get("completed_at"):
            matches.append((path.stat().st_mtime, path, state))
    if not matches:
        return None
    _, path, state = max(matches, key=lambda item: item[0])
    return path, state


def _git_head(cwd: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _normalize_owned_path(cwd: Path, value: str) -> Path:
    candidate = (cwd / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    root = cwd.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ContractError(f"owned path escapes the working directory: {value}") from error
    return candidate


def _path_manifest(cwd: Path, owned_paths: list[str]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in sorted(owned_paths):
        path = _normalize_owned_path(cwd, raw)
        paths: list[Path]
        if path.is_dir():
            paths = sorted(item for item in path.rglob("*") if item.is_file() and ".git" not in item.parts)
        else:
            paths = [path]
        if not paths:
            paths = [path]
        for item in paths:
            relative = item.relative_to(cwd.resolve()).as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            if item.is_file():
                digest = hashlib.sha256(item.read_bytes()).hexdigest()
                state = "file"
            else:
                digest = hashlib.sha256(b"<missing>").hexdigest()
                state = "missing"
            status = subprocess.run(
                ["git", "status", "--porcelain=v1", "--", relative],
                cwd=str(cwd),
                text=True,
                capture_output=True,
                check=False,
            )
            entries.append(
                {
                    "path": relative,
                    "state": state,
                    "content_sha256": digest,
                    "git_status": sorted(
                        {line[:2] for line in status.stdout.splitlines() if len(line) >= 2}
                    ),
                }
            )
    return {"schema_version": 1, "entries": entries, "sha256": canonical_sha256(entries)}


def _routes_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(left.get(key) == right.get(key) for key in ("agent", "model", "reasoning_effort", "read_only"))


def _authority(intent: Mapping[str, Any]) -> str:
    override = intent.get("override")
    if isinstance(override, Mapping):
        authority = override.get("authority")
        if isinstance(authority, Mapping):
            return str(authority.get("authority", "root"))
    quality = intent["profile"]["quality_mode"]
    if intent["profile"].get("prior_route_failure"):
        return "recorded_failure"
    return str(quality.get("authority", "root"))


def _persisted_override(intent: Mapping[str, Any]) -> dict[str, Any] | None:
    override = intent.get("override")
    if not isinstance(override, Mapping):
        return None
    authority = override.get("authority")
    authority_name = authority.get("authority") if isinstance(authority, Mapping) else None
    reference = authority.get("reference") if isinstance(authority, Mapping) else None
    return {
        "reason_code": override.get("reason_code"),
        "authority": authority_name,
        "rationale_sha256": _digest_text(str(override.get("rationale", ""))),
        "reference_sha256": _digest_text(str(reference or "")),
    }


def _critical_floor_ok(route: Mapping[str, Any]) -> bool:
    return route.get("model") == "gpt-5.6-sol" and EFFORT_ORDER.get(str(route.get("reasoning_effort")), -1) >= EFFORT_ORDER["medium"]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug:
        raise ContractError("task_name must contain an ASCII letter or number")
    return slug[:64]


def _message(
    intent_id: str,
    intent: Mapping[str, Any],
    route: Mapping[str, Any] | None,
    *,
    include_role: bool,
) -> str:
    lines = [f"Router-Intent: {intent_id}", ""]
    if include_role and route is not None:
        lines.extend(("Role:", load_role_inventory()[str(route["agent"])].instructions, ""))
    lines.extend(
        (
            f"Objective: {intent['objective']}",
            "",
            "Canonical references:",
            *([f"- {item}" for item in intent["references"]] or ["- None supplied; inspect only the owned paths."]),
            "",
            "Owned paths:",
            *([f"- {item}" for item in intent["owned_paths"]] or ["- Read-only; do not edit files."]),
            "",
            "Essential constraints:",
            *([f"- {item}" for item in intent["constraints"]] or ["- Preserve existing repository contracts."]),
            f"Delegation grant: {intent['delegation_grant']}",
            f"Commit authority: {'granted' if intent['commit_authority'] else 'none'}",
        )
    )
    lines.append("- Remain a leaf and do not delegate or spawn subagents.")
    if intent.get("review_target"):
        target = intent["review_target"]
        lines.extend(
            (
                f"Review source intent: {target['source_intent_id']}",
                f"Review manifest SHA-256: {target['manifest_sha256']}",
            )
        )
    lines.extend(
        (
            "",
            "Required verification:",
            *[f"- {item}" for item in intent["verification"]],
            "",
            "Return a concise normal result. End with exactly one machine-readable footer:",
        )
    )
    if intent.get("review_target"):
        lines.append(
            f'Router-Review: {{"intent_id":"{intent_id}","manifest_sha256":"{intent["review_target"]["manifest_sha256"]}","verdict":"pass|changes_required"}}'
        )
    else:
        lines.append(f'Router-Result: {{"intent_id":"{intent_id}","outcome":"ok|blocked|failed"}}')
    return "\n".join(lines).strip() + "\n"


def _overlap(left: list[str], right: list[str]) -> bool:
    def parts(value: str) -> tuple[str, ...]:
        return tuple(part for part in Path(value).as_posix().strip("/").split("/") if part not in ("", "."))

    for first in left:
        a = parts(first)
        for second in right:
            b = parts(second)
            if a == b or a[: len(b)] == b or b[: len(a)] == a:
                return True
    return False


def prepare(
    payload: Any,
    *,
    state_dir: Path | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    intent = validate_route_intent(payload)
    workdir = (cwd or Path.cwd()).resolve()
    normalized_owned_paths = [
        _normalize_owned_path(workdir, value).relative_to(workdir).as_posix()
        for value in intent["owned_paths"]
    ]
    if len(normalized_owned_paths) != len(set(normalized_owned_paths)):
        raise ContractError("owned_paths collapse to duplicate canonical paths")
    intent["owned_paths"] = normalized_owned_paths
    recommendation = recommend(intent["profile"])
    execution = intent["execution_mode"]
    selected = intent.get("selected_route")
    if execution == "delegate" and selected is None:
        selected = recommendation["preferred_route"]
        intent["selected_route"] = selected

    errors: list[str] = []
    warnings: list[str] = []
    override = intent.get("override")
    authority = _authority(intent)
    if execution == "delegate" and selected is not None:
        route_differs = not _routes_equal(selected, recommendation["preferred_route"])
        if route_differs:
            if not override:
                errors.append(
                    "enforced route differs from the recommendation; provide an authorized override "
                    "with reason, rationale, authority, and reference"
                )
            elif authority not in PRIVILEGED_AUTHORITIES:
                errors.append(
                    "route deviations require user, task_contract, or recorded_failure authority"
                )
        if recommendation["availability"] == "unavailable":
            if not override:
                errors.append("unavailable preferred route requires an authorized fallback override")
            elif authority not in PRIVILEGED_AUTHORITIES:
                errors.append(
                    "unavailable-route fallback requires user, task_contract, or recorded_failure authority"
                )
        if recommendation["constraints"]["critical"] and not _critical_floor_ok(selected):
            if authority not in PRIVILEGED_AUTHORITIES:
                errors.append("critical work requires at least gpt-5.6-sol/medium or privileged override authority")
    if execution == "inherited" and not override:
        errors.append("inherited full-history execution requires an accountable override")
    if intent["fork_turns"] not in ("none", "all") and not override:
        errors.append("positive bounded fork_turns requires a recorded rationale and authority")
    if intent.get("review_target"):
        if execution != "delegate" or selected is None or selected["agent"] != "gpt56_router_sol_reviewer":
            errors.append("review_target requires delegated gpt56_router_sol_reviewer")

    critical = bool(recommendation["constraints"]["critical"])
    review_required = bool(recommendation["review"]["required"])
    if critical and override and override["reason_code"] == "SKIP_CRITICAL_REVIEW":
        if authority in PRIVILEGED_AUTHORITIES:
            review_required = False
            warnings.append("critical review skipped by privileged override")
        else:
            errors.append("skipping critical review requires privileged override authority")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "evidence": {}, "data": None}

    intent_id = str(uuid.uuid4())
    state_path = None
    if state_dir is not None:
        if not session_id or not turn_id:
            raise ContractError("state registration requires session_id and turn_id")
        found = _find_active_state(state_dir, session_id, turn_id)
        if found is None:
            raise ContractError("governed turn state is not active; verify that the plugin hooks are trusted")
        state_path, _ = found

    request: dict[str, Any] | None = None
    if execution in ("delegate", "inherited"):
        request = {"task_name": _slug(intent["task_name"]), "fork_turns": intent["fork_turns"]}
        fields = set(intent["supported_spawn_fields"])
        if execution == "inherited":
            request["message"] = _message(intent_id, intent, None, include_role=False)
        elif "agent_type" in fields:
            request["agent_type"] = selected["agent"]
            request["message"] = _message(intent_id, intent, selected, include_role=False)
            if len(request["message"]) > CUSTOM_AGENT_LIMIT:
                errors.append(f"spawn message exceeds {CUSTOM_AGENT_LIMIT} characters")
        elif {"model", "reasoning_effort"}.issubset(fields):
            request["model"] = selected["model"]
            request["reasoning_effort"] = selected["reasoning_effort"]
            request["message"] = _message(intent_id, intent, selected, include_role=True)
            if len(request["message"]) > MODEL_OVERRIDE_LIMIT:
                errors.append(f"spawn message exceeds {MODEL_OVERRIDE_LIMIT} characters")
        else:
            errors.append("selected route requires agent_type or both model and reasoning_effort")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "evidence": {}, "data": None}

    if execution == "inherited":
        routing_mode = "inherited"
    elif request and "agent_type" in request:
        routing_mode = "custom_agent"
    elif request:
        routing_mode = "model_override"
    else:
        routing_mode = "root"
    record = {
        "intent_id": intent_id,
        "task_name": request["task_name"] if request else _slug(intent["task_name"]),
        "profile_sha256": recommendation["profile_sha256"],
        "intent_sha256": canonical_sha256(intent),
        "objective_sha256": _digest_text(intent["objective"]),
        "execution_mode": execution,
        "selected_route": selected,
        "preferred_route": recommendation["preferred_route"],
        "availability": recommendation["availability"],
        "reason_codes": recommendation["reason_codes"],
        "critical": critical,
        "review_required": review_required,
        "review_target": intent.get("review_target"),
        "owned_paths": intent["owned_paths"],
        "owned_paths_sha256": canonical_sha256(intent["owned_paths"]),
        "writer": bool(intent["owned_paths"])
        and (
            execution == "inherited"
            or (isinstance(selected, Mapping) and not selected.get("read_only"))
        ),
        "fork_turns": intent["fork_turns"],
        "delegation_grant": intent["delegation_grant"],
        "commit_authority": intent["commit_authority"],
        "override": _persisted_override(intent),
        "routing_mode": routing_mode,
        "request_sha256": canonical_sha256(request) if request else None,
        "status": "prepared" if request else "root",
        "prepared_at": _now(),
        "baseline_head": _git_head(workdir),
        "manifest": None,
        "result": None,
    }
    if state_path is not None:
        def register(state: dict[str, Any]) -> None:
            if record["task_name"] in state.setdefault("task_names", []):
                raise ContractError(f"duplicate routed task name: {record['task_name']}")
            if record["writer"]:
                for other in state.setdefault("intents", {}).values():
                    if (
                        other.get("status") in ("prepared", "spawning", "spawned", "running")
                        and other.get("writer")
                        and _overlap(intent["owned_paths"], other.get("owned_paths", []))
                    ):
                        raise ContractError(f"owned paths overlap active writer intent {other['intent_id']}")
            state["task_names"].append(record["task_name"])
            state["intents"][intent_id] = record
            state["updated_at"] = _now()

        try:
            _with_lock(state_path, register)
        except ContractError as error:
            return {
                "ok": False,
                "errors": [str(error)],
                "warnings": warnings,
                "evidence": {},
                "data": None,
            }
    elif request is not None:
        warnings.append("spawn request is not registered with an active hook state")

    return {
        "ok": True,
        "errors": [],
        "warnings": warnings,
        "evidence": {
            "profile_sha256": recommendation["profile_sha256"],
            "intent_sha256": record["intent_sha256"],
            "state_registered": state_path is not None,
        },
        "data": {
            "intent_id": intent_id,
            "recommendation": recommendation,
            "selected_route": selected,
            "review_required": review_required,
            "spawn_request": request,
        },
    }


def snapshot(
    *,
    state_dir: Path,
    session_id: str,
    turn_id: str,
    intent_id: str,
    cwd: Path,
) -> dict[str, Any]:
    found = _find_active_state(state_dir, session_id, turn_id)
    if found is None:
        raise ContractError("active router state not found")
    path, state = found
    record = state.get("intents", {}).get(intent_id)
    if not isinstance(record, Mapping):
        raise ContractError("intent not found")
    manifest = _path_manifest(cwd.resolve(), list(record.get("owned_paths", [])))

    def update(current: dict[str, Any]) -> None:
        current["intents"][intent_id]["manifest"] = manifest
        current["updated_at"] = _now()

    _with_lock(path, update)
    return {
        "ok": True,
        "errors": [],
        "warnings": [],
        "evidence": {"manifest_sha256": manifest["sha256"], "entry_count": len(manifest["entries"])},
        "data": {"intent_id": intent_id, "manifest": manifest},
    }


def audit(*, state_dir: Path, session_id: str, turn_id: str | None = None) -> dict[str, Any]:
    found = _find_active_state(state_dir, session_id, turn_id)
    if found is None and turn_id:
        path = _state_path(state_dir, session_id, turn_id)
        state = _load_state(path)
        found = (path, state) if state else None
    if found is None:
        return {"ok": False, "errors": ["router state not found"], "warnings": [], "evidence": {}, "data": None}
    path, state = found
    intents = list(state.get("intents", {}).values())
    violations = list(state.get("violations", []))
    warnings = list(state.get("warnings", []))
    return {
        "ok": not violations,
        "errors": [item.get("code", "violation") for item in violations],
        "warnings": [item.get("code", "warning") for item in warnings],
        "evidence": {
            "state_sha256": canonical_sha256(state),
            "intent_count": len(intents),
            "critical_count": sum(bool(item.get("critical")) for item in intents),
            "completed_count": sum(item.get("status") == "completed" for item in intents),
            "violation_count": len(violations),
        },
        "data": {
            "state_path": str(path),
            "active": bool(state.get("active")),
            "completed_at": state.get("completed_at"),
            "routes": [
                {
                    "intent_id": item.get("intent_id"),
                    "task_name": item.get("task_name"),
                    "execution_mode": item.get("execution_mode"),
                    "selected_route": item.get("selected_route"),
                    "actual_agent_id_sha256": item.get("actual_agent_id_sha256"),
                    "actual_agent": item.get("actual_agent"),
                    "actual_model": item.get("actual_model"),
                    "actual_effort": item.get("actual_effort"),
                    "expected_depth": item.get("expected_depth"),
                    "actual_depth": item.get("actual_depth"),
                    "actual_parent_intent_id": item.get("actual_parent_intent_id"),
                    "actual_fork_turns": item.get("actual_fork_turns"),
                    "status": item.get("status"),
                    "critical": item.get("critical"),
                    "review_required": item.get("review_required"),
                    "manifest_sha256": (item.get("manifest") or {}).get("sha256"),
                    "result": item.get("result"),
                }
                for item in intents
            ],
        },
    }


def _hook_output(
    *,
    event: str,
    decision: str | None = None,
    reason: str | None = None,
    context: str | None = None,
    continue_value: bool | None = None,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    specific: dict[str, Any] = {"hookEventName": event}
    if decision:
        specific["permissionDecision"] = decision
    if reason and decision:
        specific["permissionDecisionReason"] = reason
    if context:
        specific["additionalContext"] = context
    if len(specific) > 1:
        output["hookSpecificOutput"] = specific
    if continue_value is not None:
        output["continue"] = continue_value
    if reason and event in ("Stop", "SubagentStop"):
        output["continue"] = False
        output["stopReason"] = reason
        output["systemMessage"] = reason
    if reason and "hookSpecificOutput" not in output:
        output["systemMessage"] = reason
    return output


def _read_hook_input() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid hook input: {error}") from error
    if not isinstance(value, dict):
        raise ContractError("hook input must be an object")
    return value


def _hook_root(*, required: bool = False) -> Path | None:
    raw = os.environ.get("PLUGIN_DATA")
    if not raw:
        if required:
            raise ContractError("PLUGIN_DATA is not available")
        return None
    return Path(raw) / "governor"


def _record_warning(path: Path, code: str, details: Mapping[str, Any] | None = None) -> None:
    def update(state: dict[str, Any]) -> None:
        state.setdefault("warnings", []).append({"code": code, "at": _now(), **(dict(details or {}))})
        state["updated_at"] = _now()

    _with_lock(path, update)


def _deny(path: Path | None, code: str, message: str) -> dict[str, Any]:
    if path:
        def update(state: dict[str, Any]) -> None:
            state.setdefault("violations", []).append({"code": code, "at": _now()})
            state["updated_at"] = _now()

        _with_lock(path, update)
    return _hook_output(event="PreToolUse", decision="deny", reason=message)


def _parse_intent(message: Any) -> str | None:
    if not isinstance(message, str):
        return None
    match = INTENT_LINE.search(message)
    return match.group(1) if match else None


def _contains_sensitive_handoff(message: str) -> bool:
    lowered = message.lower()
    return any(label in lowered for label in FORBIDDEN_LABELS) or any(pattern.search(message) for pattern in SECRET_PATTERNS)


def _actor_intent(state: Mapping[str, Any], transcript_path: str | None) -> str | None:
    digest = _digest_text(transcript_path)
    if digest and digest == state.get("root_transcript_sha256"):
        return "root"
    for agent in state.get("agents", {}).values():
        if digest and agent.get("transcript_sha256") == digest:
            return str(agent.get("intent_id"))
    return None


def _extract_agent_id(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("agent_id", "thread_id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for nested in value.values():
            found = _extract_agent_id(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _extract_agent_id(nested)
            if found:
                return found
    elif isinstance(value, str):
        try:
            return _extract_agent_id(json.loads(value))
        except json.JSONDecodeError:
            match = re.search(r"\b(?:agent_id|thread_id)[=:]\s*([A-Za-z0-9_-]+)", value)
            return match.group(1) if match else None
    return None


def hook_user_prompt(event: Mapping[str, Any]) -> dict[str, Any]:
    prompt = event.get("prompt")
    explicitly_invoked = isinstance(prompt, str) and bool(ROUTER_INVOCATION.search(prompt))
    root = _hook_root()
    if root is None:
        return _hook_output(
            event="UserPromptSubmit",
            context=(
                "GPT-5.6 router state is unavailable because PLUGIN_DATA is missing. "
                "Root-direct work may continue, but trusted enforcement will deny every Agent spawn "
                "until plugin state is restored."
            ),
        )
    session_id = str(event.get("session_id", "unknown"))
    turn_id = str(event.get("turn_id", "unknown"))
    path = _state_path(root, session_id, turn_id)
    authorities = [
        marker
        for marker in ("quality-first", "override-critical-floor", "skip-critical-review")
        if f"Router authority: {marker}" in prompt
    ]

    def activate(state: dict[str, Any]) -> None:
        if state:
            raise ContractError("router state already exists for this turn")
        state.update(
            {
                "state_schema": STATE_SCHEMA,
                "active": True,
                "session_sha256": _id_hash(session_id),
                "turn_sha256": _id_hash(turn_id),
                "root_transcript_sha256": _digest_text(event.get("transcript_path")),
                "cwd_sha256": _digest_text(str(event.get("cwd", ""))),
                "root_model": event.get("model"),
                "explicit_invocation": explicitly_invoked,
                "activated_at": _now(),
                "updated_at": _now(),
                "completed_at": None,
                "authorities": authorities,
                "task_names": [],
                "intents": {},
                "pending_calls": {},
                "agents": {},
                "violations": [],
                "warnings": [],
            }
        )

    _with_lock(path, activate)
    _prune(root)
    plugin_root = os.environ.get("PLUGIN_ROOT", "<PLUGIN_ROOT>")
    command = (
        f'python3 "{plugin_root}/skills/route-gpt56-task/scripts/route_guard.py" prepare '
        f'--input <route-intent-v4.json> --state-dir "{root}" '
        f'--session-id "{session_id}" --turn-id "{turn_id}" --json'
    )
    context = (
        "GPT-5.6 router enforcement is active. Before every Agent spawn, register a v4 route "
        f"intent and use the exact spawn_request returned by this command: {command}"
    )
    if explicitly_invoked:
        context += " This explicit router turn must also register root-direct execution before closeout if no Agent is spawned."
    return _hook_output(event="UserPromptSubmit", context=context)


def hook_pre_tool(event: Mapping[str, Any]) -> dict[str, Any]:
    tool_name = str(event.get("tool_name", ""))
    root = _hook_root()
    if root is None:
        if tool_name == "Agent":
            return _deny(
                None,
                "ROUTER_STATE_UNAVAILABLE",
                "Agent spawning is denied because governed router state is unavailable. "
                "Restore PLUGIN_DATA and trusted plugin hooks, then prepare a v4 route intent.",
            )
        return {}
    session_id = str(event.get("session_id", "unknown"))
    turn_id = str(event.get("turn_id")) if event.get("turn_id") is not None else None
    found = _find_active_state(root, session_id, turn_id)
    if found is None:
        if tool_name == "Agent":
            return _deny(
                None,
                "MISSING_GOVERNED_TURN",
                "Agent spawning requires the GPT-5.6 router prompt hook and a prepared v4 route intent. "
                "Verify hook trust, then run route_guard.py prepare and retry its exact spawn_request.",
            )
        return {}
    path, state = found
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return _deny(path, "MALFORMED_TOOL_INPUT", "Router governance requires an object tool input.")

    if tool_name == "Bash":
        command = tool_input.get("command")
        actor = _actor_intent(state, event.get("transcript_path"))
        if actor and actor != "root" and isinstance(command, str) and COMMIT_COMMAND.search(command):
            record = state.get("intents", {}).get(actor, {})
            if not record.get("commit_authority"):
                return _deny(path, "CHILD_COMMIT_DENIED", "This routed child has no commit, tag, or push authority.")
        return {}

    if tool_name != "Agent":
        return {}
    message = tool_input.get("message")
    intent_id = _parse_intent(message)
    if intent_id is None:
        return _deny(
            path,
            "MISSING_ROUTE_INTENT",
            "Active router turns require a registered Router-Intent in every Agent message.",
        )
    record = state.get("intents", {}).get(intent_id)
    if not isinstance(record, Mapping):
        return _deny(path, "UNKNOWN_ROUTE_INTENT", "The Router-Intent is not registered for this active turn.")
    if not isinstance(message, str) or _contains_sensitive_handoff(message):
        return _deny(path, "SENSITIVE_HANDOFF", "The routed handoff contains forbidden copied context or secret-like material.")

    actual = dict(tool_input)
    expected_task = record.get("task_name")
    if actual.get("task_name") != expected_task:
        return _deny(path, "TASK_NAME_MISMATCH", "Agent task_name does not match the registered route intent.")
    if str(actual.get("fork_turns", "none")) != str(record.get("fork_turns")):
        return _deny(path, "FORK_MISMATCH", "Agent fork_turns does not match the registered route intent.")
    route = record.get("selected_route")
    routing_mode = record.get("routing_mode")
    if record.get("execution_mode") == "inherited":
        if any(name in actual for name in ("agent_type", "model", "reasoning_effort")):
            return _deny(path, "INHERITED_ROUTE_FIELDS", "Inherited full-history spawns cannot select agent, model, or effort.")
    elif isinstance(route, Mapping):
        if routing_mode == "custom_agent":
            if actual.get("agent_type") != route.get("agent"):
                return _deny(path, "AGENT_MISMATCH", "Agent type does not match the registered route intent.")
            if any(name in actual for name in ("model", "reasoning_effort")):
                return _deny(path, "ROUTING_MODE_MISMATCH", "Custom-agent routes cannot also set model or effort.")
        elif routing_mode == "model_override":
            if actual.get("model") != route.get("model") or actual.get("reasoning_effort") != route.get("reasoning_effort"):
                return _deny(path, "MODEL_EFFORT_MISMATCH", "Model and effort must match the registered route intent.")
            if "agent_type" in actual:
                return _deny(path, "ROUTING_MODE_MISMATCH", "Model-override routes cannot also set agent_type.")
        if "agent_type" in actual and actual.get("agent_type") != route.get("agent"):
            return _deny(path, "AGENT_MISMATCH", "Agent type does not match the registered route intent.")
        if "model" in actual and actual.get("model") != route.get("model"):
            return _deny(path, "MODEL_MISMATCH", "Model does not match the registered route intent.")
        if "reasoning_effort" in actual and actual.get("reasoning_effort") != route.get("reasoning_effort"):
            return _deny(path, "EFFORT_MISMATCH", "Reasoning effort does not match the registered route intent.")
    if actual.get("fork_turns") == "all" and any(name in actual for name in ("agent_type", "model", "reasoning_effort")):
        return _deny(path, "CUSTOM_FULL_HISTORY", "Full-history forks inherit the parent and cannot select a routed role.")
    if canonical_sha256(actual) != record.get("request_sha256"):
        return _deny(
            path,
            "SPAWN_REQUEST_MISMATCH",
            "Agent arguments differ from the registered request. Run prepare again and use spawn_request exactly.",
        )

    actor = _actor_intent(state, event.get("transcript_path"))
    if actor is None:
        return _deny(path, "UNKNOWN_DELEGATOR", "Could not prove the delegating actor for this routed spawn.")
    if actor != "root":
        return _deny(path, "UNAUTHORIZED_DESCENDANT", "Depth-one routed children are leaves and cannot delegate.")

    tool_use_id = str(event.get("tool_use_id", uuid.uuid4()))

    def mark(state_now: dict[str, Any]) -> None:
        current = state_now["intents"][intent_id]
        if current.get("status") not in ("prepared", "failed_spawn"):
            raise ContractError("route intent has already been used")
        current["status"] = "spawning"
        current["spawn_tool_use_id_sha256"] = _digest_text(tool_use_id)
        current["delegator_intent_id"] = actor
        state_now["pending_calls"][_id_hash(tool_use_id)] = intent_id
        state_now["updated_at"] = _now()

    try:
        _with_lock(path, mark)
    except ContractError as error:
        return _deny(path, "INTENT_REUSE", str(error))
    return {}


def hook_post_tool(event: Mapping[str, Any]) -> dict[str, Any]:
    if str(event.get("tool_name", "")) != "Agent":
        return {}
    root = _hook_root()
    if root is None:
        return {}
    found = _find_active_state(
        root,
        str(event.get("session_id", "unknown")),
        str(event.get("turn_id")) if event.get("turn_id") is not None else None,
    )
    if found is None:
        return {}
    path, state = found
    intent_id = _parse_intent((event.get("tool_input") or {}).get("message") if isinstance(event.get("tool_input"), Mapping) else None)
    if not intent_id or intent_id not in state.get("intents", {}):
        return {}
    agent_id = _extract_agent_id(event.get("tool_response"))

    def mark(current: dict[str, Any]) -> None:
        record = current["intents"][intent_id]
        current["pending_calls"].pop(_id_hash(str(event.get("tool_use_id", ""))), None)
        record["status"] = "spawned" if agent_id else "failed_spawn"
        record["spawned_at"] = _now() if agent_id else None
        record["failed_spawn_at"] = _now() if not agent_id else None
        if agent_id:
            current["agents"][_id_hash(agent_id)] = {
                "intent_id": intent_id,
                "agent_id_sha256": _id_hash(agent_id),
            }
        else:
            current["warnings"].append({"code": "SPAWN_AGENT_ID_UNAVAILABLE", "at": _now()})
        current["updated_at"] = _now()

    _with_lock(path, mark)
    return {}


def hook_subagent_start(event: Mapping[str, Any]) -> dict[str, Any]:
    root = _hook_root()
    if root is None:
        return {}
    found = _find_active_state(root, str(event.get("session_id", "unknown")), None)
    if found is None:
        return {}
    path, state = found
    agent_id = str(event.get("agent_id", ""))
    agent_type = str(event.get("agent_type", ""))
    mapped = state.get("agents", {}).get(_id_hash(agent_id))
    intent_id = mapped.get("intent_id") if isinstance(mapped, Mapping) else None
    if intent_id is None:
        candidates = [
            item["intent_id"]
            for item in state.get("intents", {}).values()
            if item.get("status") in ("spawning", "spawned")
            and (
                item.get("execution_mode") == "inherited"
                or (item.get("selected_route") or {}).get("agent") == agent_type
            )
        ]
        if len(candidates) == 1:
            intent_id = candidates[0]
    if intent_id is None:
        _record_warning(path, "SUBAGENT_START_UNMAPPED")
        return {"systemMessage": "Router governance could not map this subagent start to an intent."}

    def mark(current: dict[str, Any]) -> None:
        record = current["intents"][intent_id]
        raw_depth = event.get("depth") if event.get("depth") is not None else event.get("agent_depth")
        actual_depth = int(raw_depth) if isinstance(raw_depth, str) and raw_depth.isdigit() else raw_depth
        parent_agent_id = event.get("parent_agent_id")
        parent_mapping = (
            current.get("agents", {}).get(_id_hash(str(parent_agent_id)))
            if parent_agent_id is not None
            else None
        )
        record["status"] = "running"
        record["actual_agent_id_sha256"] = _id_hash(agent_id)
        record["actual_agent"] = agent_type
        record["actual_model"] = event.get("model")
        record["actual_effort"] = event.get("reasoning_effort") or event.get("model_reasoning_effort")
        record["expected_depth"] = 1
        record["actual_depth"] = actual_depth
        record["expected_parent_intent_id"] = record.get("delegator_intent_id")
        record["actual_parent_intent_id"] = (
            parent_mapping.get("intent_id") if isinstance(parent_mapping, Mapping) else None
        )
        record["actual_parent_agent_id_sha256"] = _id_hash(str(parent_agent_id)) if parent_agent_id else None
        record["actual_fork_turns"] = event.get("fork_turns")
        record["started_at"] = _now()
        current["agents"][_id_hash(agent_id)] = {
            "intent_id": intent_id,
            "agent_id_sha256": _id_hash(agent_id),
            "transcript_sha256": _digest_text(event.get("transcript_path")),
        }
        current["updated_at"] = _now()
        selected = record.get("selected_route") or {}
        if record.get("routing_mode") == "custom_agent" and agent_type != selected.get("agent"):
            current["violations"].append({"code": "RUNTIME_AGENT_MISMATCH", "at": _now()})
        if event.get("model") and selected and event.get("model") != selected.get("model"):
            current["violations"].append({"code": "RUNTIME_MODEL_MISMATCH", "at": _now()})
        if record["actual_effort"] and selected and record["actual_effort"] != selected.get("reasoning_effort"):
            current["violations"].append({"code": "RUNTIME_EFFORT_MISMATCH", "at": _now()})
        if record["actual_fork_turns"] and str(record["actual_fork_turns"]) != str(record.get("fork_turns")):
            current["violations"].append({"code": "RUNTIME_FORK_MISMATCH", "at": _now()})
        if record["actual_depth"] is not None and record["actual_depth"] != record["expected_depth"]:
            current["violations"].append({"code": "RUNTIME_DEPTH_MISMATCH", "at": _now()})
        if not record["actual_model"]:
            current["warnings"].append({"code": "SUBAGENT_MODEL_METADATA_UNAVAILABLE", "at": _now()})
        if not record["actual_effort"]:
            current["warnings"].append({"code": "SUBAGENT_EFFORT_METADATA_UNAVAILABLE", "at": _now()})
        if record["actual_fork_turns"] is None:
            current["warnings"].append({"code": "SUBAGENT_FORK_METADATA_UNAVAILABLE", "at": _now()})
        if record["actual_depth"] is None:
            current["warnings"].append({"code": "SUBAGENT_DEPTH_METADATA_UNAVAILABLE", "at": _now()})
        if record["actual_parent_intent_id"] is None:
            current["warnings"].append({"code": "SUBAGENT_PARENT_METADATA_UNAVAILABLE", "at": _now()})

    _with_lock(path, mark)
    return {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": f"Governed route intent {intent_id} is active. Preserve its footer contract.",
        }
    }


def _footer(message: Any) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(message, str):
        return None
    for kind, pattern in (("review", REVIEW_LINE), ("result", RESULT_LINE)):
        match = pattern.search(message)
        if not match:
            continue
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        if isinstance(value, dict):
            return kind, value
    return None


def hook_subagent_stop(event: Mapping[str, Any]) -> dict[str, Any]:
    root = _hook_root()
    if root is None:
        return {}
    found = _find_active_state(root, str(event.get("session_id", "unknown")), None)
    if found is None:
        return {}
    path, state = found
    parsed = _footer(event.get("last_assistant_message"))
    if parsed is None:
        return _hook_output(
            event="SubagentStop",
            reason="Return the required Router-Result or Router-Review footer before stopping.",
        )
    kind, value = parsed
    intent_id = value.get("intent_id")
    record = state.get("intents", {}).get(intent_id)
    if not isinstance(record, Mapping):
        return _hook_output(event="SubagentStop", reason="Footer intent_id is not registered for this router turn.")
    agent_id = str(event.get("agent_id", ""))
    mapped = state.get("agents", {}).get(_id_hash(agent_id)) if agent_id else None
    if isinstance(mapped, Mapping) and mapped.get("intent_id") != intent_id:
        return _hook_output(
            event="SubagentStop",
            reason="Subagent identity does not match the intent in its result footer.",
        )
    if not isinstance(mapped, Mapping):
        _record_warning(path, "SUBAGENT_STOP_UNMAPPED", {"intent_id": intent_id})
    if kind == "review":
        target = record.get("review_target")
        if not isinstance(target, Mapping):
            return _hook_output(event="SubagentStop", reason="Router-Review footer used by a non-review intent.")
        if value.get("manifest_sha256") != target.get("manifest_sha256"):
            return _hook_output(event="SubagentStop", reason="Router-Review manifest does not match the registered target.")
        if value.get("verdict") not in ("pass", "changes_required"):
            return _hook_output(event="SubagentStop", reason="Router-Review verdict must be pass or changes_required.")
        result = {
            "kind": "review",
            "verdict": value["verdict"],
            "manifest_sha256": value["manifest_sha256"],
        }
    else:
        if value.get("outcome") not in ("ok", "blocked", "failed"):
            return _hook_output(event="SubagentStop", reason="Router-Result outcome must be ok, blocked, or failed.")
        result = {"kind": "result", "outcome": value["outcome"]}

    current_head = _git_head(Path(str(event.get("cwd", Path.cwd()))))
    head_changed = (
        not record.get("commit_authority")
        and record.get("baseline_head")
        and current_head
        and record.get("baseline_head") != current_head
    )

    def mark(current: dict[str, Any]) -> None:
        active = current["intents"][intent_id]
        active["status"] = "completed"
        active["result"] = result
        active["completed_at"] = _now()
        if head_changed:
            current["violations"].append({"code": "HEAD_CHANGED_WITHOUT_COMMIT_AUTHORITY", "at": _now()})
        current["updated_at"] = _now()

    _with_lock(path, mark)
    if head_changed:
        return _hook_output(
            event="SubagentStop",
            reason="Git HEAD changed while this child lacked commit authority; return control to the root for repair.",
            continue_value=False,
        )
    return {"continue": True}


def hook_stop(event: Mapping[str, Any]) -> dict[str, Any]:
    root = _hook_root()
    if root is None:
        return {}
    found = _find_active_state(
        root,
        str(event.get("session_id", "unknown")),
        str(event.get("turn_id")) if event.get("turn_id") is not None else None,
    )
    if found is None:
        return {}
    path, state = found
    intents = state.get("intents", {})
    if not intents:
        if not state.get("explicit_invocation"):
            def complete_unrouted(current: dict[str, Any]) -> None:
                current["active"] = False
                current["completed_at"] = _now()
                current["updated_at"] = _now()

            _with_lock(path, complete_unrouted)
            return {"continue": True}
        return _hook_output(
            event="Stop",
            reason="Register at least one v4 route intent, including root-direct execution, before closeout.",
        )
    running = [
        item["intent_id"]
        for item in intents.values()
        if item.get("execution_mode") != "root" and item.get("status") not in ("completed", "failed_spawn")
    ]
    if running:
        return _hook_output(event="Stop", reason="Wait for or resolve routed intents before closeout: " + ", ".join(running))

    cwd = Path(str(event.get("cwd", Path.cwd()))).resolve()
    for item in intents.values():
        if not item.get("critical") or not item.get("review_required"):
            continue
        if item.get("execution_mode") == "delegate":
            actual_model = item.get("actual_model")
            actual_effort = item.get("actual_effort")
            if actual_model != "gpt-5.6-sol" or EFFORT_ORDER.get(str(actual_effort), -1) < EFFORT_ORDER["medium"]:
                return _hook_output(
                    event="Stop",
                    reason=(
                        f"Critical intent {item['intent_id']} lacks persisted runtime proof "
                        "of the Sol/medium execution floor."
                    ),
                )
        manifest = item.get("manifest")
        if not isinstance(manifest, Mapping):
            return _hook_output(
                event="Stop",
                reason=f"Critical intent {item['intent_id']} requires a path snapshot and independent review.",
            )
        try:
            current = _path_manifest(cwd, list(item.get("owned_paths", [])))
        except (OSError, ContractError) as error:
            _record_warning(path, "MANIFEST_AUDIT_UNAVAILABLE", {"intent_id": item["intent_id"]})
            return _hook_output(
                event="Stop",
                reason=(
                    f"Critical manifest audit is unavailable for {item['intent_id']}: {error}. "
                    "Restore audit access or prepare a privileged accountable exception."
                ),
            )
        if current["sha256"] != manifest.get("sha256"):
            return _hook_output(
                event="Stop",
                reason=f"Critical intent {item['intent_id']} changed after its snapshot; snapshot and review again.",
            )
        reviewer = next(
            (
                review
                for review in intents.values()
                if (review.get("review_target") or {}).get("source_intent_id") == item["intent_id"]
                and (review.get("result") or {}).get("kind") == "review"
                and (review.get("result") or {}).get("verdict") == "pass"
                and (review.get("result") or {}).get("manifest_sha256") == current["sha256"]
                and review.get("actual_agent") == "gpt56_router_sol_reviewer"
                and review.get("actual_model") == "gpt-5.6-sol"
                and review.get("actual_effort") == "high"
                and review.get("actual_agent_id_sha256") != item.get("actual_agent_id_sha256")
            ),
            None,
        )
        if reviewer is None:
            return _hook_output(
                event="Stop",
                reason=f"Critical intent {item['intent_id']} lacks a passing independent Sol/high review for the current manifest.",
            )
    if state.get("violations"):
        codes = sorted({item.get("code", "violation") for item in state["violations"]})
        return _hook_output(event="Stop", reason="Resolve router violations before closeout: " + ", ".join(codes))

    def complete(current: dict[str, Any]) -> None:
        current["active"] = False
        current["completed_at"] = _now()
        current["updated_at"] = _now()

    _with_lock(path, complete)
    return {"continue": True}


def run_hook(event_name: str) -> dict[str, Any]:
    event = _read_hook_input()
    handlers = {
        "UserPromptSubmit": hook_user_prompt,
        "PreToolUse": hook_pre_tool,
        "PostToolUse": hook_post_tool,
        "SubagentStart": hook_subagent_start,
        "SubagentStop": hook_subagent_stop,
        "Stop": hook_stop,
    }
    if event_name not in handlers:
        raise ContractError(f"unsupported hook event: {event_name}")
    return handlers[event_name](event)


def _render(result: Mapping[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result.get("ok"):
        print("ok")
    else:
        print("; ".join(str(item) for item in result.get("errors", ["failed"])))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--input", required=True, metavar="PATH|-")
    prepare_parser.add_argument("--state-dir", type=Path)
    prepare_parser.add_argument("--session-id")
    prepare_parser.add_argument("--turn-id")
    prepare_parser.add_argument("--cwd", type=Path, default=Path.cwd())
    prepare_parser.add_argument("--json", action="store_true")

    snapshot_parser = commands.add_parser("snapshot")
    snapshot_parser.add_argument("--state-dir", type=Path, required=True)
    snapshot_parser.add_argument("--session-id", required=True)
    snapshot_parser.add_argument("--turn-id", required=True)
    snapshot_parser.add_argument("--intent-id", required=True)
    snapshot_parser.add_argument("--cwd", type=Path, default=Path.cwd())
    snapshot_parser.add_argument("--json", action="store_true")

    audit_parser = commands.add_parser("audit")
    audit_parser.add_argument("--state-dir", type=Path, required=True)
    audit_parser.add_argument("--session-id", required=True)
    audit_parser.add_argument("--turn-id")
    audit_parser.add_argument("--json", action="store_true")

    status_parser = commands.add_parser("status")
    status_parser.add_argument("--state-dir", type=Path, required=True)
    status_parser.add_argument("--session-id", required=True)
    status_parser.add_argument("--turn-id")
    status_parser.add_argument("--json", action="store_true")

    hook_parser = commands.add_parser("hook", help=argparse.SUPPRESS)
    hook_parser.add_argument("--event", required=True)

    try:
        args = parser.parse_args(argv)
        if args.command == "prepare":
            result = prepare(
                load_json_input(args.input),
                state_dir=args.state_dir,
                session_id=args.session_id,
                turn_id=args.turn_id,
                cwd=args.cwd,
            )
            _render(result, args.json)
            return 0 if result["ok"] else 1
        if args.command == "snapshot":
            result = snapshot(
                state_dir=args.state_dir,
                session_id=args.session_id,
                turn_id=args.turn_id,
                intent_id=args.intent_id,
                cwd=args.cwd,
            )
            _render(result, args.json)
            return 0
        if args.command in ("audit", "status"):
            result = audit(state_dir=args.state_dir, session_id=args.session_id, turn_id=args.turn_id)
            _render(result, args.json)
            return 0 if result["ok"] else 1
        result = run_hook(args.event)
        if result:
            print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return 0
    except (ContractError, OSError, subprocess.SubprocessError) as error:
        if "args" in locals() and getattr(args, "command", None) == "hook":
            event = getattr(args, "event", "PreToolUse")
            if event == "PreToolUse":
                failure = _hook_output(event=event, decision="deny", reason=f"Router guard internal error: {error}")
            elif event == "PostToolUse":
                failure = {
                    "continue": False,
                    "stopReason": f"Router guard internal error: {error}",
                    "systemMessage": "GPT-5.6 router post-tool audit failed safely.",
                }
            elif event in ("Stop", "SubagentStop"):
                failure = _hook_output(event=event, reason=f"Router guard internal error: {error}")
            elif event == "SubagentStart":
                failure = {"systemMessage": f"Router guard internal error: {error}"}
            else:
                failure = {
                    "continue": False,
                    "stopReason": f"Router guard internal error: {error}",
                    "systemMessage": "GPT-5.6 router hook failed safely.",
                }
            print(json.dumps(failure, separators=(",", ":"), sort_keys=True))
            return 0
        failure = {
            "ok": False,
            "errors": [str(error)],
            "warnings": [],
            "evidence": {},
            "data": None,
        }
        if "args" in locals() and getattr(args, "json", False):
            print(json.dumps(failure, indent=2, sort_keys=True))
        else:
            print(f"route_guard.py: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
