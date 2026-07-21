from __future__ import annotations
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts"
sys.path.insert(0, str(SCRIPTS))
import router_contract as contract  # noqa: E402


class ProtocolSchemaTests(unittest.TestCase):
    def profile(self):
        return {"schema_version": 3, "kind": "implementation", "ambiguity": 1, "context_breadth": 1, "verification_strength": 3, "risk_domains": []}

    def test_only_two_schema_v3_artifacts_exist(self):
        paths = sorted((SCRIPTS.parent / "schemas").glob("*.schema.json"))
        self.assertEqual([path.name for path in paths], ["route-recommendation.schema.json", "task-profile.schema.json"])
        for path in paths:
            value = json.loads(path.read_text())
            self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("v3", value["$id"])

    def test_inventory_has_ten_schema4_bounded_roles(self):
        roles = contract.load_role_inventory()
        self.assertEqual(len(roles), 10)
        for role in roles.values():
            self.assertIn("Delegation grant: one-level", role.instructions)
            self.assertIn("Delegation grant: none", role.instructions)
            self.assertIn("cannot delegate further", role.instructions)

    def test_profile_runtime_is_optional_and_old_or_extra_fields_reject(self):
        self.assertEqual(contract.validate_task_profile(self.profile())["schema_version"], 3)
        with self.assertRaisesRegex(contract.ContractError, "unsupported fields"):
            contract.validate_task_profile({**self.profile(), "task_id": "legacy"})
        with self.assertRaisesRegex(contract.ContractError, "equal 3"):
            contract.validate_task_profile({**self.profile(), "schema_version": 2})

    def test_recommendation_surface_is_advisory(self):
        recommendation = {
            "schema_version": 3,
            "preferred_route": {"agent": "gpt56_router_terra_worker", "model": "gpt-5.6-terra", "reasoning_effort": "medium", "read_only": False},
            "availability": "unavailable",
            "review": {"recommended": False, "preferred_reviewer": None},
            "reason_codes": ["KIND_IMPLEMENTATION", "PREFERRED_ROUTE_UNAVAILABLE"],
        }
        self.assertEqual(contract.validate_route_recommendation(recommendation), recommendation)
        for forbidden in ("decision", "required", "blocked"):
            with self.subTest(forbidden=forbidden), self.assertRaisesRegex(contract.ContractError, "unsupported fields"):
                contract.validate_route_recommendation({**recommendation, forbidden: True})

    def test_ultra_is_rejected(self):
        profile = {**self.profile(), "prior_route_failure": {"model": "gpt-5.6-sol", "effort": "ultra", "evidence": "failure"}}
        with self.assertRaisesRegex(contract.ContractError, "unsupported"): contract.validate_task_profile(profile)


if __name__ == "__main__": unittest.main()
