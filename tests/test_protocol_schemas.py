from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts"
sys.path.insert(0, str(SCRIPTS))
import router_contract as contract  # noqa: E402


def profile(**overrides):
    value = {
        "schema_version": 4,
        "kind": "implementation",
        "ambiguity": 1,
        "context_breadth": 1,
        "verification_strength": 3,
        "risk_domains": [],
        "quality_mode": {"level": "standard", "authority": "root", "reference": ""},
    }
    value.update(overrides)
    return value


def intent(**overrides):
    value = {
        "schema_version": 4,
        "profile": profile(),
        "execution_mode": "root",
        "task_name": "root-work",
        "objective": "Complete the bounded task.",
        "references": [],
        "owned_paths": [],
        "constraints": [],
        "verification": ["python3 -m unittest"],
        "fork_turns": "none",
        "delegation_grant": "none",
        "commit_authority": False,
        "supported_spawn_fields": ["agent_type"],
    }
    value.update(overrides)
    return value


class ProtocolSchemaTests(unittest.TestCase):
    def test_three_schema_v4_artifacts_exist(self):
        paths = sorted((SCRIPTS.parent / "schemas").glob("*.schema.json"))
        self.assertEqual(
            [path.name for path in paths],
            [
                "route-intent.schema.json",
                "route-recommendation.schema.json",
                "task-profile.schema.json",
            ],
        )
        for path in paths:
            value = json.loads(path.read_text())
            self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("v4", value["$id"])

    def test_inventory_has_ten_schema5_bounded_roles(self):
        roles = contract.load_role_inventory()
        self.assertEqual(len(roles), 10)
        for role in roles.values():
            self.assertIn("Delegation grant: one-level", role.instructions)
            self.assertIn("Delegation grant: none", role.instructions)
            self.assertIn("cannot delegate further", role.instructions)
            self.assertTrue("Router-Result" in role.instructions or "Router-Review" in role.instructions)

    def test_profile_v4_and_clean_v3_break(self):
        self.assertEqual(contract.validate_task_profile(profile())["schema_version"], 4)
        with self.assertRaisesRegex(contract.ContractError, "schema v3 is unsupported"):
            contract.validate_task_profile({**profile(), "schema_version": 3})
        with self.assertRaisesRegex(contract.ContractError, "unsupported fields"):
            contract.validate_task_profile({**profile(), "quality_first": True})

    def test_quality_first_requires_privileged_authority_and_reference(self):
        privileged = profile(
            quality_mode={
                "level": "quality_first",
                "authority": "task_contract",
                "reference": "release-plan#quality",
            }
        )
        self.assertEqual(contract.validate_task_profile(privileged), privileged)
        with self.assertRaisesRegex(contract.ContractError, "privileged authority"):
            contract.validate_task_profile(
                profile(quality_mode={"level": "quality_first", "authority": "root", "reference": "because"})
            )

    def test_route_intent_modes_and_full_history_contract(self):
        self.assertEqual(contract.validate_route_intent(intent())["execution_mode"], "root")
        inherited = intent(
            execution_mode="inherited",
            task_name="inherit",
            fork_turns="all",
            override={
                "reason_code": "INHERIT_ROOT_CONTEXT",
                "rationale": "The bounded child requires the complete active context.",
                "authority": {"authority": "root", "reference": "root decision 1"},
            },
        )
        self.assertEqual(contract.validate_route_intent(inherited)["fork_turns"], "all")
        with self.assertRaisesRegex(contract.ContractError, "requires inherited"):
            contract.validate_route_intent(intent(fork_turns="all"))

    def test_ultra_is_rejected(self):
        invalid = profile(
            prior_route_failure={
                "model": "gpt-5.6-sol",
                "effort": "ultra",
                "evidence": "failed check",
            }
        )
        with self.assertRaisesRegex(contract.ContractError, "unsupported"):
            contract.validate_task_profile(invalid)


if __name__ == "__main__":
    unittest.main()
