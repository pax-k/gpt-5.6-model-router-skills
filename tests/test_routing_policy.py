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
            "schema_version": 3,
            "kind": "implementation",
            "ambiguity": 1,
            "context_breadth": 1,
            "verification_strength": 3,
            "risk_domains": [],
            "quality_first": False,
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
                self.assertEqual(route_task.recommend(self.profile(kind=kind))["preferred_route"]["agent"], agent)

    def test_mechanical_luna_eligibility(self):
        for override in ({"ambiguity": 2}, {"context_breadth": 2}, {"verification_strength": 1}):
            with self.subTest(override=override):
                route = route_task.recommend(self.profile(kind="mechanical", **override))
                self.assertEqual(route["preferred_route"]["agent"], "gpt56_router_terra_worker")

    def test_broad_competing_exploration_uses_terra_high(self):
        route = route_task.recommend(self.profile(kind="exploration", ambiguity=2, context_breadth=3))
        self.assertEqual(route["preferred_route"]["agent"], "gpt56_router_terra_investigator")

    def test_critical_floor_and_review(self):
        route = route_task.recommend(self.profile(risk_domains=["authentication"]))
        self.assertEqual(route["preferred_route"]["agent"], "gpt56_router_sol_engineer")
        self.assertTrue(route["review"]["recommended"])
        self.assertEqual(route["review"]["preferred_reviewer"]["agent"], "gpt56_router_sol_reviewer")

    def test_weak_critical_verification_uses_debugger(self):
        route = route_task.recommend(self.profile(risk_domains=["concurrency"], verification_strength=1))
        self.assertEqual(route["preferred_route"]["agent"], "gpt56_router_sol_debugger")

    def test_noncritical_contract_domains_do_not_force_review(self):
        for domain in ("public_api", "schema", "compatibility", "persistent_data"):
            with self.subTest(domain=domain):
                route = route_task.recommend(self.profile(risk_domains=[domain]))
                self.assertEqual(route["preferred_route"]["agent"], "gpt56_router_terra_worker")
                self.assertFalse(route["review"]["recommended"])

    def test_recorded_failure_ladder_and_quality_first(self):
        cases = (
            ("gpt-5.6-luna", "low", "gpt56_router_terra_worker"),
            ("gpt-5.6-terra", "medium", "gpt56_router_sol_engineer"),
            ("gpt-5.6-sol", "medium", "gpt56_router_sol_debugger"),
            ("gpt-5.6-sol", "high", "gpt56_router_sol_specialist_xhigh"),
            ("gpt-5.6-sol", "xhigh", "gpt56_router_sol_specialist_max"),
        )
        for model, effort, agent in cases:
            failure = {"model": model, "effort": effort, "evidence": "failed focused test"}
            with self.subTest(effort=effort):
                self.assertEqual(route_task.recommend(self.profile(prior_route_failure=failure))["preferred_route"]["agent"], agent)
        self.assertEqual(route_task.recommend(self.profile(quality_first=True))["preferred_route"]["agent"], "gpt56_router_sol_specialist_max")

    def test_custom_agent_preferred_and_override_fallback(self):
        custom = route_task.recommend(self.profile())
        self.assertEqual(custom["availability"], "custom_agent")
        runtime = {"custom_agent": False, "model_override": True, "available_agents": [], "available_models": MODELS}
        override = route_task.recommend(self.profile(runtime_capabilities=runtime))
        self.assertEqual(override["availability"], "model_override")

    def test_unavailable_route_remains_visible_and_nonblocking(self):
        runtime = {"custom_agent": False, "model_override": False, "available_agents": [], "available_models": []}
        recommendation = route_task.recommend(self.profile(runtime_capabilities=runtime))
        self.assertEqual(recommendation["availability"], "unavailable")
        self.assertEqual(recommendation["preferred_route"]["agent"], "gpt56_router_terra_worker")
        self.assertIn("PREFERRED_ROUTE_UNAVAILABLE", recommendation["reason_codes"])

    def test_runtime_capabilities_are_optional(self):
        profile = self.profile()
        del profile["runtime_capabilities"]
        recommendation = route_task.recommend(profile)
        self.assertEqual(recommendation["availability"], "unknown")
        self.assertIsNotNone(recommendation["preferred_route"])

    def test_repeated_ordinary_workstreams_add_no_review(self):
        decisions = [route_task.recommend(self.profile()) for _ in range(5)]
        self.assertTrue(all(not decision["review"]["recommended"] for decision in decisions))


if __name__ == "__main__":
    unittest.main()
