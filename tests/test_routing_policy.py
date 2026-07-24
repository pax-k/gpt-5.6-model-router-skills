from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts"
sys.path.insert(0, str(SCRIPTS))
import route_task  # noqa: E402


AGENTS = list(route_task.ROLES.values())
MODELS = ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]


class RoutingPolicyTests(unittest.TestCase):
    def profile(self, **overrides):
        value = {
            "schema_version": 4,
            "kind": "implementation",
            "ambiguity": 1,
            "context_breadth": 1,
            "verification_strength": 3,
            "risk_domains": [],
            "quality_mode": {"level": "standard", "authority": "root", "reference": ""},
            "runtime_capabilities": {
                "custom_agent": True,
                "model_override": True,
                "available_agents": AGENTS,
                "available_models": MODELS,
            },
        }
        value.update(overrides)
        return value

    def test_base_routes(self):
        expected = {
            "mechanical": "gpt56_router_luna_worker",
            "exploration": "gpt56_router_terra_explorer",
            "implementation": "gpt56_router_terra_worker",
            "ambiguous": "gpt56_router_sol_engineer",
            "debugging": "gpt56_router_sol_debugger",
            "review": "gpt56_router_sol_reviewer",
            "advisory": "gpt56_router_sol_advisor",
        }
        for kind, agent in expected.items():
            with self.subTest(kind=kind):
                route = route_task.recommend(self.profile(kind=kind))
                self.assertEqual(route["preferred_route"]["agent"], agent)

    def test_family_follows_ambiguity_not_breadth(self):
        broad = route_task.recommend(self.profile(kind="implementation", context_breadth=3))
        self.assertEqual(broad["preferred_route"]["agent"], "gpt56_router_terra_worker")
        self.assertIn("BROAD_CONTEXT_TERRA", broad["reason_codes"])
        ambiguous = route_task.recommend(self.profile(kind="implementation", ambiguity=2))
        self.assertEqual(ambiguous["preferred_route"]["agent"], "gpt56_router_sol_engineer")

    def test_terra_high_is_narrowly_broad_and_competing(self):
        broad_only = route_task.recommend(
            self.profile(kind="exploration", ambiguity=1, context_breadth=3)
        )
        self.assertEqual(broad_only["preferred_route"]["agent"], "gpt56_router_terra_explorer")
        competing = route_task.recommend(
            self.profile(kind="exploration", ambiguity=2, context_breadth=3)
        )
        self.assertEqual(competing["preferred_route"]["agent"], "gpt56_router_terra_investigator")

    def test_critical_floor_and_review(self):
        route = route_task.recommend(self.profile(risk_domains=["authentication"]))
        self.assertEqual(route["preferred_route"]["agent"], "gpt56_router_sol_engineer")
        self.assertEqual(
            (route["constraints"]["minimum_model"], route["constraints"]["minimum_effort"]),
            ("gpt-5.6-sol", "medium"),
        )
        self.assertTrue(route["review"]["required"])
        self.assertEqual(route["review"]["preferred_reviewer"]["agent"], "gpt56_router_sol_reviewer")

    def test_weak_critical_verification_uses_debugger(self):
        route = route_task.recommend(
            self.profile(risk_domains=["concurrency"], verification_strength=1)
        )
        self.assertEqual(route["preferred_route"]["agent"], "gpt56_router_sol_debugger")

    def test_recorded_failure_ladder_and_quality_first(self):
        cases = (
            ("gpt-5.6-luna", "high", "gpt56_router_terra_worker"),
            ("gpt-5.6-terra", "medium", "gpt56_router_sol_engineer"),
            ("gpt-5.6-terra", "high", "gpt56_router_sol_engineer"),
            ("gpt-5.6-sol", "medium", "gpt56_router_sol_debugger"),
            ("gpt-5.6-sol", "high", "gpt56_router_sol_debugger"),
        )
        for model, effort, agent in cases:
            failure = {"model": model, "effort": effort, "evidence": "failed focused test"}
            with self.subTest(model=model, effort=effort):
                selected = route_task.recommend(self.profile(prior_route_failure=failure))
                self.assertEqual(selected["preferred_route"]["agent"], agent)
        quality = {
            "level": "quality_first",
            "authority": "user",
            "reference": "user requested maximum quality",
        }
        selected = route_task.recommend(self.profile(quality_mode=quality))
        self.assertEqual(selected["preferred_route"]["agent"], "gpt56_router_sol_debugger")
        self.assertEqual(selected["preferred_route"]["reasoning_effort"], "high")

    def test_availability_is_evidence_not_route_mutation(self):
        runtime = {
            "custom_agent": False,
            "model_override": False,
            "available_agents": [],
            "available_models": [],
        }
        recommendation = route_task.recommend(self.profile(runtime_capabilities=runtime))
        self.assertEqual(recommendation["availability"], "unavailable")
        self.assertEqual(recommendation["preferred_route"]["agent"], "gpt56_router_terra_worker")
        self.assertIn("PREFERRED_ROUTE_UNAVAILABLE", recommendation["reason_codes"])


if __name__ == "__main__":
    unittest.main()
