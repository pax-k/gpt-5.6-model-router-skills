#!/usr/bin/env python3
"""Small advisory schema-v3 contracts shared by the GPT-5.6 router helpers."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 3
KINDS = ("mechanical", "exploration", "implementation", "ambiguous", "debugging", "review", "advisory")
EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")
AVAILABILITY = ("custom_agent", "model_override", "unavailable", "unknown")


class ContractError(ValueError):
    """Raised when a public router payload is invalid."""


@dataclass(frozen=True)
class Role:
    name: str
    description: str
    model: str
    reasoning_effort: str
    instructions: str
    read_only: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _agent_asset_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "setup-gpt56-model-router" / "assets" / "agents"


def load_role_inventory(asset_dir: str | Path | None = None) -> dict[str, Role]:
    directory = Path(asset_dir) if asset_dir is not None else _agent_asset_dir()
    roles: dict[str, Role] = {}
    for path in sorted(directory.glob("*.toml")):
        text = path.read_text(encoding="utf-8")
        if not re.fullmatch(
            r"# Managed by gpt-5-6-model-router; agent=[a-z0-9_]+; schema=4",
            text.splitlines()[0] if text.splitlines() else "",
        ):
            raise ContractError(f"{path.name}: expected a schema-4 managed role")
        raw = tomllib.loads(text)
        required = ("name", "description", "model", "model_reasoning_effort", "developer_instructions")
        missing = [name for name in required if not isinstance(raw.get(name), str) or not raw[name].strip()]
        if missing:
            raise ContractError(f"{path.name}: missing role fields: {', '.join(missing)}")
        effort = raw["model_reasoning_effort"]
        if effort not in EFFORTS:
            raise ContractError(f"{path.name}: unsupported effort: {effort}")
        role = Role(
            name=raw["name"], description=raw["description"], model=raw["model"],
            reasoning_effort=effort, instructions=raw["developer_instructions"].strip(),
            read_only=raw.get("sandbox_mode") == "read-only", source=str(path),
        )
        if role.name in roles:
            raise ContractError(f"duplicate role name: {role.name}")
        roles[role.name] = role
    if not roles:
        raise ContractError(f"no role TOMLs found in {directory}")
    return roles


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return value


def _allowed(data: Mapping[str, Any], allowed: set[str], path: str = "$") -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractError(f"{path} contains unsupported fields: {', '.join(extra)}")


def _required(data: Mapping[str, Any], required: set[str], path: str = "$") -> None:
    missing = sorted(required - set(data))
    if missing:
        raise ContractError(f"{path} missing required fields: {', '.join(missing)}")


def _rating(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3:
        raise ContractError(f"{path} must be an integer from 0 to 3")
    return value


def _strings(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ContractError(f"{path} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise ContractError(f"{path} must contain unique items")
    return value


def _validate_runtime(value: Any) -> dict[str, Any]:
    runtime = dict(_mapping(value, "$.runtime_capabilities"))
    required = {"custom_agent", "model_override", "available_agents", "available_models"}
    _required(runtime, required, "$.runtime_capabilities")
    _allowed(runtime, required, "$.runtime_capabilities")
    for name in ("custom_agent", "model_override"):
        if not isinstance(runtime[name], bool):
            raise ContractError(f"$.runtime_capabilities.{name} must be a boolean")
    _strings(runtime["available_agents"], "$.runtime_capabilities.available_agents")
    _strings(runtime["available_models"], "$.runtime_capabilities.available_models")
    return runtime


def validate_task_profile(payload: Any) -> dict[str, Any]:
    data = dict(_mapping(payload, "$"))
    required = {"schema_version", "kind", "ambiguity", "context_breadth", "verification_strength", "risk_domains"}
    allowed = required | {"prior_route_failure", "quality_first", "runtime_capabilities"}
    _required(data, required)
    _allowed(data, allowed)
    if data["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"$.schema_version must equal {SCHEMA_VERSION}")
    if data["kind"] not in KINDS:
        raise ContractError(f"$.kind must be one of: {', '.join(KINDS)}")
    for name in ("ambiguity", "context_breadth", "verification_strength"):
        _rating(data[name], f"$.{name}")
    _strings(data["risk_domains"], "$.risk_domains")
    if "quality_first" in data and not isinstance(data["quality_first"], bool):
        raise ContractError("$.quality_first must be a boolean")
    if failure := data.get("prior_route_failure"):
        failure = _mapping(failure, "$.prior_route_failure")
        _required(failure, {"model", "effort", "evidence"}, "$.prior_route_failure")
        _allowed(failure, {"agent", "model", "effort", "evidence"}, "$.prior_route_failure")
        if failure["effort"] not in EFFORTS:
            raise ContractError("$.prior_route_failure.effort is unsupported")
        for name in ("model", "evidence"):
            if not isinstance(failure[name], str) or not failure[name].strip():
                raise ContractError(f"$.prior_route_failure.{name} must be a non-empty string")
    if "runtime_capabilities" in data:
        data["runtime_capabilities"] = _validate_runtime(data["runtime_capabilities"])
    return data


def _validate_route(value: Any, path: str) -> dict[str, Any]:
    route = dict(_mapping(value, path))
    required = {"agent", "model", "reasoning_effort", "read_only"}
    _required(route, required, path)
    _allowed(route, required, path)
    role = load_role_inventory().get(route["agent"])
    if role is None:
        raise ContractError(f"{path}.agent is not a bundled role")
    expected = (role.model, role.reasoning_effort, role.read_only)
    actual = (route["model"], route["reasoning_effort"], route["read_only"])
    if actual != expected:
        raise ContractError(f"{path} does not match the bundled role model, effort, and read-only behavior")
    return route


def validate_route_recommendation(payload: Any) -> dict[str, Any]:
    data = dict(_mapping(payload, "$"))
    required = {"schema_version", "preferred_route", "availability", "review", "reason_codes"}
    _required(data, required)
    _allowed(data, required)
    if data["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"$.schema_version must equal {SCHEMA_VERSION}")
    data["preferred_route"] = _validate_route(data["preferred_route"], "$.preferred_route")
    if data["availability"] not in AVAILABILITY:
        raise ContractError(f"$.availability must be one of: {', '.join(AVAILABILITY)}")
    review = dict(_mapping(data["review"], "$.review"))
    _required(review, {"recommended", "preferred_reviewer"}, "$.review")
    _allowed(review, {"recommended", "preferred_reviewer"}, "$.review")
    if not isinstance(review["recommended"], bool):
        raise ContractError("$.review.recommended must be a boolean")
    if review["recommended"] != (review["preferred_reviewer"] is not None):
        raise ContractError("$.review.preferred_reviewer presence must match $.review.recommended")
    if review["preferred_reviewer"] is not None:
        review["preferred_reviewer"] = _validate_route(review["preferred_reviewer"], "$.review.preferred_reviewer")
    data["review"] = review
    _strings(data["reason_codes"], "$.reason_codes")
    if not data["reason_codes"]:
        raise ContractError("$.reason_codes must not be empty")
    return data


def load_json_input(path: str) -> Any:
    import sys
    try:
        return json.load(sys.stdin) if path == "-" else json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"could not read JSON input: {error}") from error
