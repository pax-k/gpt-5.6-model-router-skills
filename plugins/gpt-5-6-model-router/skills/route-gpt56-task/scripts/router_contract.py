#!/usr/bin/env python3
"""Schema-v4 contracts shared by the governed GPT-5.6 router."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

if sys.version_info < (3, 9):
    print("GPT-5.6 Model Router requires Python 3.9 or newer", file=sys.stderr)
    raise SystemExit(2)

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10
    plugin_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(plugin_root / "vendor"))
    import tomli as tomllib  # type: ignore[no-redef]


SCHEMA_VERSION = 4
KINDS = (
    "mechanical",
    "exploration",
    "implementation",
    "ambiguous",
    "debugging",
    "review",
    "advisory",
)
EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")
AVAILABILITY = ("custom_agent", "model_override", "unavailable", "unknown")
EXECUTION_MODES = ("root", "delegate", "inherited")
DELEGATION_GRANTS = ("none",)
AUTHORITIES = ("root", "user", "task_contract", "recorded_failure")
PRIVILEGED_AUTHORITIES = frozenset(("user", "task_contract", "recorded_failure"))
QUALITY_LEVELS = ("standard", "quality_first")
OVERRIDE_REASON = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


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
            r"# Managed by gpt-5-6-model-router; agent=[a-z0-9_]+; schema=5",
            text.splitlines()[0] if text.splitlines() else "",
        ):
            raise ContractError(f"{path.name}: expected a schema-5 managed role")
        raw = tomllib.loads(text)
        required = ("name", "description", "model", "model_reasoning_effort", "developer_instructions")
        missing = [name for name in required if not isinstance(raw.get(name), str) or not raw[name].strip()]
        if missing:
            raise ContractError(f"{path.name}: missing role fields: {', '.join(missing)}")
        effort = raw["model_reasoning_effort"]
        if effort not in EFFORTS:
            raise ContractError(f"{path.name}: unsupported effort: {effort}")
        role = Role(
            name=raw["name"],
            description=raw["description"],
            model=raw["model"],
            reasoning_effort=effort,
            instructions=raw["developer_instructions"].strip(),
            read_only=raw.get("sandbox_mode") == "read-only",
            source=str(path),
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


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a non-empty string")
    return value.strip()


def _rating(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3:
        raise ContractError(f"{path} must be an integer from 0 to 3")
    return value


def _strings(value: Any, path: str, *, required: bool = False) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ContractError(f"{path} must be an array of non-empty strings")
    normalized = [item.strip() for item in value]
    if len(normalized) != len(set(normalized)):
        raise ContractError(f"{path} must contain unique items")
    return normalized


def _validate_runtime(value: Any) -> dict[str, Any]:
    runtime = dict(_mapping(value, "$.runtime_capabilities"))
    required = {"custom_agent", "model_override", "available_agents", "available_models"}
    _required(runtime, required, "$.runtime_capabilities")
    _allowed(runtime, required, "$.runtime_capabilities")
    for name in ("custom_agent", "model_override"):
        if not isinstance(runtime[name], bool):
            raise ContractError(f"$.runtime_capabilities.{name} must be a boolean")
    runtime["available_agents"] = _strings(
        runtime["available_agents"], "$.runtime_capabilities.available_agents", required=True
    )
    runtime["available_models"] = _strings(
        runtime["available_models"], "$.runtime_capabilities.available_models", required=True
    )
    return runtime


def _validate_authority(value: Any, path: str, *, privileged: bool = False) -> dict[str, str]:
    authority = dict(_mapping(value, path))
    _required(authority, {"authority", "reference"}, path)
    _allowed(authority, {"authority", "reference"}, path)
    if authority["authority"] not in AUTHORITIES:
        raise ContractError(f"{path}.authority must be one of: {', '.join(AUTHORITIES)}")
    if privileged and authority["authority"] not in PRIVILEGED_AUTHORITIES:
        raise ContractError(f"{path}.authority must be user, task_contract, or recorded_failure")
    authority["reference"] = _string(authority["reference"], f"{path}.reference")
    return authority


def validate_task_profile(payload: Any) -> dict[str, Any]:
    data = dict(_mapping(payload, "$"))
    required = {
        "schema_version",
        "kind",
        "ambiguity",
        "context_breadth",
        "verification_strength",
        "risk_domains",
        "quality_mode",
    }
    allowed = required | {"prior_route_failure", "runtime_capabilities"}
    _required(data, required)
    _allowed(data, allowed)
    if data["schema_version"] != SCHEMA_VERSION:
        raise ContractError(
            f"$.schema_version must equal {SCHEMA_VERSION}; schema v3 is unsupported, "
            "see references/migration-v0.4.md"
        )
    if data["kind"] not in KINDS:
        raise ContractError(f"$.kind must be one of: {', '.join(KINDS)}")
    for name in ("ambiguity", "context_breadth", "verification_strength"):
        data[name] = _rating(data[name], f"$.{name}")
    data["risk_domains"] = _strings(data["risk_domains"], "$.risk_domains", required=True)

    quality = dict(_mapping(data["quality_mode"], "$.quality_mode"))
    _required(quality, {"level", "authority", "reference"}, "$.quality_mode")
    _allowed(quality, {"level", "authority", "reference"}, "$.quality_mode")
    if quality["level"] not in QUALITY_LEVELS:
        raise ContractError(f"$.quality_mode.level must be one of: {', '.join(QUALITY_LEVELS)}")
    if quality["authority"] not in AUTHORITIES:
        raise ContractError(f"$.quality_mode.authority must be one of: {', '.join(AUTHORITIES)}")
    if quality["level"] == "quality_first":
        if quality["authority"] not in PRIVILEGED_AUTHORITIES:
            raise ContractError("$.quality_mode quality_first requires privileged authority")
        quality["reference"] = _string(quality["reference"], "$.quality_mode.reference")
    elif quality["authority"] != "root" or quality["reference"] not in ("", None):
        raise ContractError("$.quality_mode standard must use root authority and an empty reference")
    else:
        quality["reference"] = ""
    data["quality_mode"] = quality

    failure = data.get("prior_route_failure")
    if failure is not None:
        failure = dict(_mapping(failure, "$.prior_route_failure"))
        _required(failure, {"model", "effort", "evidence"}, "$.prior_route_failure")
        _allowed(failure, {"agent", "model", "effort", "evidence"}, "$.prior_route_failure")
        if failure["effort"] not in EFFORTS:
            raise ContractError("$.prior_route_failure.effort is unsupported")
        failure["model"] = _string(failure["model"], "$.prior_route_failure.model")
        failure["evidence"] = _string(failure["evidence"], "$.prior_route_failure.evidence")
        data["prior_route_failure"] = failure
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
        raise ContractError(f"{path} does not match the bundled role")
    return route


def validate_route_recommendation(payload: Any) -> dict[str, Any]:
    data = dict(_mapping(payload, "$"))
    required = {
        "schema_version",
        "profile_sha256",
        "preferred_route",
        "availability",
        "constraints",
        "review",
        "reason_codes",
    }
    _required(data, required)
    _allowed(data, required)
    if data["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"$.schema_version must equal {SCHEMA_VERSION}")
    if not re.fullmatch(r"[0-9a-f]{64}", str(data["profile_sha256"])):
        raise ContractError("$.profile_sha256 must be a lowercase SHA-256 digest")
    data["preferred_route"] = _validate_route(data["preferred_route"], "$.preferred_route")
    if data["availability"] not in AVAILABILITY:
        raise ContractError(f"$.availability must be one of: {', '.join(AVAILABILITY)}")

    constraints = dict(_mapping(data["constraints"], "$.constraints"))
    _required(constraints, {"critical", "minimum_model", "minimum_effort"}, "$.constraints")
    _allowed(constraints, {"critical", "minimum_model", "minimum_effort"}, "$.constraints")
    if not isinstance(constraints["critical"], bool):
        raise ContractError("$.constraints.critical must be a boolean")
    if constraints["critical"]:
        if (constraints["minimum_model"], constraints["minimum_effort"]) != ("gpt-5.6-sol", "medium"):
            raise ContractError("$.constraints critical floor must be gpt-5.6-sol/medium")
    elif constraints["minimum_model"] is not None or constraints["minimum_effort"] is not None:
        raise ContractError("$.constraints noncritical floor must be null")
    data["constraints"] = constraints

    review = dict(_mapping(data["review"], "$.review"))
    _required(review, {"required", "preferred_reviewer"}, "$.review")
    _allowed(review, {"required", "preferred_reviewer"}, "$.review")
    if not isinstance(review["required"], bool):
        raise ContractError("$.review.required must be a boolean")
    if review["required"] != (review["preferred_reviewer"] is not None):
        raise ContractError("$.review.preferred_reviewer presence must match $.review.required")
    if review["preferred_reviewer"] is not None:
        review["preferred_reviewer"] = _validate_route(review["preferred_reviewer"], "$.review.preferred_reviewer")
    data["review"] = review
    data["reason_codes"] = _strings(data["reason_codes"], "$.reason_codes", required=True)
    if not data["reason_codes"]:
        raise ContractError("$.reason_codes must not be empty")
    return data


def validate_route_intent(payload: Any) -> dict[str, Any]:
    data = dict(_mapping(payload, "$"))
    required = {
        "schema_version",
        "profile",
        "execution_mode",
        "task_name",
        "objective",
        "references",
        "owned_paths",
        "constraints",
        "verification",
        "fork_turns",
        "delegation_grant",
        "commit_authority",
        "supported_spawn_fields",
    }
    allowed = required | {"selected_route", "override", "review_target"}
    _required(data, required)
    _allowed(data, allowed)
    if data["schema_version"] != SCHEMA_VERSION:
        raise ContractError(
            f"$.schema_version must equal {SCHEMA_VERSION}; schema v3 is unsupported, "
            "see references/migration-v0.4.md"
        )
    data["profile"] = validate_task_profile(data["profile"])
    if data["execution_mode"] not in EXECUTION_MODES:
        raise ContractError(f"$.execution_mode must be one of: {', '.join(EXECUTION_MODES)}")
    data["task_name"] = _string(data["task_name"], "$.task_name")
    data["objective"] = _string(data["objective"], "$.objective")
    for field in ("references", "owned_paths", "constraints", "verification", "supported_spawn_fields"):
        data[field] = _strings(data[field], f"$.{field}", required=field in ("verification", "supported_spawn_fields"))
    if data["delegation_grant"] not in DELEGATION_GRANTS:
        raise ContractError("$.delegation_grant must be none; routed children are leaves at depth one")
    if not isinstance(data["commit_authority"], bool):
        raise ContractError("$.commit_authority must be a boolean")

    fork = data["fork_turns"]
    if fork not in ("none", "all"):
        if isinstance(fork, int) and not isinstance(fork, bool) and fork > 0:
            fork = str(fork)
        elif not isinstance(fork, str) or not fork.isdigit() or int(fork) <= 0:
            raise ContractError('$.fork_turns must be "none", "all", or a positive turn count')
    data["fork_turns"] = fork
    if data["execution_mode"] != "inherited" and fork == "all":
        raise ContractError('$.fork_turns "all" requires inherited execution')
    if data["execution_mode"] == "inherited" and fork != "all":
        raise ContractError('$.execution_mode inherited requires fork_turns "all"')

    if "selected_route" in data:
        data["selected_route"] = _validate_route(data["selected_route"], "$.selected_route")
    if data["execution_mode"] == "delegate" and "selected_route" not in data:
        data["selected_route"] = None
    if data["execution_mode"] in ("root", "inherited") and data.get("selected_route") is not None:
        raise ContractError("$.selected_route is valid only for delegate execution")

    if "override" in data:
        override = dict(_mapping(data["override"], "$.override"))
        _required(override, {"reason_code", "rationale", "authority"}, "$.override")
        _allowed(override, {"reason_code", "rationale", "authority"}, "$.override")
        if not isinstance(override["reason_code"], str) or not OVERRIDE_REASON.fullmatch(override["reason_code"]):
            raise ContractError("$.override.reason_code must be an uppercase reason code")
        override["rationale"] = _string(override["rationale"], "$.override.rationale")
        override["authority"] = _validate_authority(override["authority"], "$.override.authority")
        data["override"] = override

    if "review_target" in data:
        target = dict(_mapping(data["review_target"], "$.review_target"))
        _required(target, {"source_intent_id", "manifest_sha256"}, "$.review_target")
        _allowed(target, {"source_intent_id", "manifest_sha256"}, "$.review_target")
        target["source_intent_id"] = _string(target["source_intent_id"], "$.review_target.source_intent_id")
        if not re.fullmatch(r"[0-9a-f]{64}", str(target["manifest_sha256"])):
            raise ContractError("$.review_target.manifest_sha256 must be a lowercase SHA-256 digest")
        data["review_target"] = target
    return data


def canonical_sha256(value: Any) -> str:
    import hashlib

    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_json_input(path: str) -> Any:
    try:
        return json.load(sys.stdin) if path == "-" else json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"could not read JSON input: {error}") from error
