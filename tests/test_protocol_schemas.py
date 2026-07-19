from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts/router_contract.py"
SPEC = importlib.util.spec_from_file_location("router_contract_test", SCRIPT)
assert SPEC and SPEC.loader
contract = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = contract
SPEC.loader.exec_module(contract)


class ProtocolSchemaTests(unittest.TestCase):
    def test_all_schema_artifacts_are_valid_json(self) -> None:
        schema_dir = SCRIPT.parent.parent / "schemas"
        expected = set(contract.VALIDATORS)
        found = set()
        for path in schema_dir.glob("*.schema.json"):
            found.add(path.name.removesuffix(".schema.json"))
            data = json.loads(path.read_text())
            self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(data["type"], "object")
        self.assertEqual(found, expected)

    def test_inventory_is_loaded_from_bundled_tomls(self) -> None:
        roles = contract.load_role_inventory()
        self.assertEqual(roles["gpt56_router_luna_worker"].model, "gpt-5.6-luna")
        self.assertEqual(roles["gpt56_router_sol_advisor"].reasoning_effort, "medium")
        self.assertTrue(roles["gpt56_router_terra_explorer"].may_delegate)
        self.assertTrue(roles["gpt56_router_sol_engineer"].may_delegate)
        self.assertFalse(roles["gpt56_router_luna_worker"].may_delegate)

    def test_inventory_rejects_role_without_delegation_capability_marker(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "role.toml"
            path.write_text(
                'name = "role"\ndescription = "test role"\nmodel = "gpt-5.6-terra"\n'
                'model_reasoning_effort = "medium"\ndeveloper_instructions = "Do work."\n'
            )
            with self.assertRaisesRegex(contract.ContractError, "may_delegate"):
                contract.load_role_inventory(directory)

    def test_canonical_child_event_validates(self) -> None:
        event = {
            "schema_version": 1, "event_type": "complete", "task_id": "root", "node_id": "node-1",
            "agent_path": "/root/node-1", "summary": "Outcome complete", "outcomes": [],
            "discovered_work": [], "validation": [], "blockers": [], "questions": [], "risks": [],
            "write_scopes": [], "review": {"required": False, "status": "not_required", "findings": []},
        }
        self.assertEqual(contract.validate_child_event(event)["event_type"], "complete")

    def test_complete_record_rejects_open_work(self) -> None:
        record = {
            "schema_version": 1, "root_task_id": "root", "status": "complete",
            "complete": True,
            "requested_outcomes_satisfied": True, "validation_passed": True,
            "required_reviews_complete": True, "unresolved_findings": [],
            "ready_or_running_nodes": ["node-2"], "external_actions_taken": [],
            "residual_risks": [], "routes_used": [], "unmet_gates": [],
        }
        with self.assertRaises(contract.ContractError):
            contract.validate_completion_record(record)

    def test_route_decision_must_match_exact_toml_effort_and_permissions(self) -> None:
        decision = {
            "schema_version": 1,
            "decision": "delegate",
            "routing_mode": "custom_agent",
            "primary": {"agent": "gpt56_router_luna_worker", "model": "gpt-5.6-luna", "reasoning_effort": "high", "read_only": False},
            "review": {"required": False, "route": None},
            "advisory": {"required": False, "route": None},
            "delegation_capability": {
                "schema_version": 1, "allowed": False, "remaining_depth": 0,
                "max_children": 0, "max_parallel_children": 0, "allowed_roles": [],
                "allowed_models": [], "allowed_write_scopes": [], "may_spawn_writers": False,
                "forbidden_actions": [], "required_return": [],
            },
            "parallel_eligibility": {"eligible": True, "requires_disjoint_peers": True, "reason_code": "KNOWN_SCOPE"},
            "reason_codes": ["KIND_MECHANICAL"],
        }
        with self.assertRaisesRegex(contract.ContractError, "reasoning effort"):
            contract.validate_route_decision(decision)

    def test_route_decision_rejects_extra_fields_and_embedded_capability_matches_depth_limit(self) -> None:
        schema_dir = SCRIPT.parent.parent / "schemas"
        route_schema = json.loads((schema_dir / "route-decision.schema.json").read_text())
        capability_schema = json.loads((schema_dir / "delegation-capability.schema.json").read_text())
        self.assertEqual(
            route_schema["$defs"]["delegation_capability"]["properties"]["remaining_depth"],
            capability_schema["properties"]["remaining_depth"],
        )
        decision = {
            "schema_version": 1, "decision": "direct_execution", "routing_mode": "direct",
            "primary": None, "review": {"required": False, "route": None},
            "advisory": {"required": False, "route": None},
            "delegation_capability": {
                "schema_version": 1, "allowed": False, "remaining_depth": 0,
                "max_children": 0, "max_parallel_children": 0, "allowed_roles": [],
                "allowed_models": [], "allowed_write_scopes": [], "may_spawn_writers": False,
                "forbidden_actions": [], "required_return": [],
            },
            "parallel_eligibility": {"eligible": False, "requires_disjoint_peers": True, "reason_code": "UNKNOWN_SCOPE"},
            "reason_codes": ["DELEGATION_NOT_REQUESTED"], "unexpected": True,
        }
        with self.assertRaisesRegex(contract.ContractError, "unsupported fields"):
            contract.validate_route_decision(decision)

    def test_route_decision_rejects_nested_extras_and_invalid_reason_sets(self) -> None:
        base = {
            "schema_version": 1, "decision": "delegate", "routing_mode": "custom_agent",
            "primary": {"agent": "gpt56_router_luna_worker", "model": "gpt-5.6-luna", "reasoning_effort": "low", "read_only": False},
            "review": {"required": False, "route": None},
            "advisory": {"required": False, "route": None},
            "delegation_capability": {
                "schema_version": 1, "allowed": False, "remaining_depth": 0,
                "max_children": 0, "max_parallel_children": 0, "allowed_roles": [],
                "allowed_models": [], "allowed_write_scopes": [], "may_spawn_writers": False,
                "forbidden_actions": [], "required_return": [],
            },
            "parallel_eligibility": {"eligible": True, "requires_disjoint_peers": True, "reason_code": "KNOWN_SCOPE"},
            "reason_codes": ["KIND_MECHANICAL"],
        }
        nested_mutations = (
            ("primary", "unexpected"),
            ("review", "unexpected"),
            ("advisory", "unexpected"),
            ("parallel_eligibility", "unexpected"),
        )
        for section, field in nested_mutations:
            with self.subTest(section=section):
                decision = json.loads(json.dumps(base))
                decision[section][field] = True
                with self.assertRaisesRegex(contract.ContractError, "unsupported fields"):
                    contract.validate_route_decision(decision)
        for reason_codes in ([], ["DUPLICATE", "DUPLICATE"], ["_INVALID"]):
            with self.subTest(reason_codes=reason_codes):
                decision = json.loads(json.dumps(base))
                decision["reason_codes"] = reason_codes
                with self.assertRaises(contract.ContractError):
                    contract.validate_route_decision(decision)

    def test_delegation_capability_rejects_duplicate_unique_arrays(self) -> None:
        capability = {
            "schema_version": 1, "allowed": True, "remaining_depth": 1,
            "max_children": 1, "max_parallel_children": 1,
            "allowed_roles": ["gpt56_router_terra_explorer", "gpt56_router_terra_explorer"],
            "allowed_models": ["gpt-5.6-terra"], "allowed_write_scopes": [],
            "may_spawn_writers": False, "forbidden_actions": [], "required_return": [],
        }
        with self.assertRaisesRegex(contract.ContractError, "unique items"):
            contract.validate_delegation_capability(capability)

    def test_route_decision_identity_fields_are_independently_optional_strings(self) -> None:
        base = {
            "schema_version": 1, "decision": "direct_execution", "routing_mode": "direct",
            "primary": None, "review": {"required": False, "route": None},
            "advisory": {"required": False, "route": None},
            "delegation_capability": {
                "schema_version": 1, "allowed": False, "remaining_depth": 0,
                "max_children": 0, "max_parallel_children": 0, "allowed_roles": [],
                "allowed_models": [], "allowed_write_scopes": [], "may_spawn_writers": False,
                "forbidden_actions": [], "required_return": [],
            },
            "parallel_eligibility": {"eligible": False, "requires_disjoint_peers": True, "reason_code": "UNKNOWN_SCOPE"},
            "reason_codes": ["DELEGATION_NOT_REQUESTED"],
        }
        for identity in ({"task_id": "task"}, {"node_id": "node"}, {"task_id": "task", "node_id": "node"}):
            with self.subTest(identity=identity):
                self.assertEqual(contract.validate_route_decision({**base, **identity})[next(iter(identity))], next(iter(identity.values())))
        with self.assertRaisesRegex(contract.ContractError, "node_id must be a non-empty string"):
            contract.validate_route_decision({**base, "node_id": 7})


if __name__ == "__main__":
    unittest.main()
