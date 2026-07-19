from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts/route_task.py"
SPEC = importlib.util.spec_from_file_location("route_task", MODULE_PATH)
assert SPEC and SPEC.loader
route_task = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = route_task
SPEC.loader.exec_module(route_task)


class RoutingPolicyTests(unittest.TestCase):
    def profile(self, **overrides):
        dimension = lambda rating: {"rating": rating, "evidence": "recorded evidence"}
        profile = {
            "schema_version": 1,
            "task_id": "00000000-0000-4000-8000-000000000001",
            "objective": "Implement the bounded change",
            "kind": "implementation",
            "phase": "implementation",
            "dimensions": {
                "ambiguity": dimension(1), "consequence": dimension(1),
                "context_breadth": dimension(1), "irreversibility": dimension(1),
                "verification_strength": dimension(3), "latency_sensitivity": dimension(1),
            },
            "risk_domains": [], "prior_attempts": [], "read_scopes": ["src"],
            "write_scopes": ["src/feature.py"],
            "human_authority": {"local_writes": True, "external_writes": False, "destructive_actions": False, "quality_first": False},
            "orchestrator": {"model": "gpt-5.6-sol", "effort": "medium"}, "depth": 0,
            "delegation_request": {"requested": True},
            "runtime_capabilities": {"agent_type": True, "model_override": True, "current_sandbox": "workspace-write", "read_only_agent_sandbox_enforced": True},
        }
        profile.update(overrides)
        return profile

    def test_base_routes(self) -> None:
        expected = {
            "mechanical": "gpt56_router_luna_worker",
            "exploration": "gpt56_router_terra_explorer",
            "implementation": "gpt56_router_terra_worker",
            "ambiguous": "gpt56_router_sol_engineer",
            "debugging": "gpt56_router_sol_debugger",
            "review": "gpt56_router_sol_reviewer",
        }
        for kind, agent in expected.items():
            with self.subTest(kind=kind):
                decision = route_task.decide(self.profile(kind=kind))
                self.assertEqual(decision["primary"]["agent"], agent)

    def test_routes_expose_v2_model_override_values(self) -> None:
        expected = {
            "mechanical": ("gpt-5.6-luna", "low"),
            "exploration": ("gpt-5.6-terra", "medium"),
            "implementation": ("gpt-5.6-terra", "medium"),
            "ambiguous": ("gpt-5.6-sol", "medium"),
            "debugging": ("gpt-5.6-sol", "high"),
            "review": ("gpt-5.6-sol", "high"),
        }
        for kind, (model, effort) in expected.items():
            with self.subTest(kind=kind):
                route = route_task.decide(self.profile(kind=kind))["primary"]
                self.assertEqual(route["model"], model)
                self.assertEqual(route["reasoning_effort"], effort)

    def test_validation_failure_escalates_mechanical_and_implementation(self) -> None:
        luna_failure = [{"model": "gpt-5.6-luna", "effort": "low", "outcome": "failed validation", "evidence": "test output"}]
        terra_failure = [{"model": "gpt-5.6-terra", "effort": "medium", "outcome": "failed validation", "evidence": "test output"}]
        sol_failure = [{"model": "gpt-5.6-sol", "effort": "medium", "outcome": "failed validation", "evidence": "test output"}]
        mechanical = route_task.decide(self.profile(kind="mechanical", prior_attempts=luna_failure))
        implementation = route_task.decide(self.profile(prior_attempts=terra_failure))
        ambiguous = route_task.decide(self.profile(kind="ambiguous", prior_attempts=sol_failure))
        self.assertEqual(mechanical["primary"]["agent"], "gpt56_router_terra_worker")
        self.assertEqual(implementation["primary"]["agent"], "gpt56_router_sol_engineer")
        self.assertEqual(ambiguous["primary"]["agent"], "gpt56_router_sol_debugger")

    def test_luna_requires_clear_low_risk_mechanical_profile(self) -> None:
        dimensions = self.profile()["dimensions"]
        dimensions["ambiguity"] = {"rating": 2, "evidence": "two plausible transformations"}
        decision = route_task.decide(self.profile(kind="mechanical", dimensions=dimensions))
        self.assertEqual(decision["primary"]["agent"], "gpt56_router_terra_worker")
        self.assertIn("LUNA_LOW_ELIGIBILITY_EXCEEDED", decision["reason_codes"])

    def test_consequential_work_adds_independent_review(self) -> None:
        route = route_task.decide(self.profile(risk_domains=["authentication"]))
        self.assertEqual(route["review"]["route"]["agent"], "gpt56_router_sol_reviewer")
        self.assertEqual(route["review"]["route"]["model"], "gpt-5.6-sol")
        self.assertEqual(route["review"]["route"]["reasoning_effort"], "high")

    def test_review_does_not_review_itself_twice(self) -> None:
        route = route_task.decide(self.profile(kind="review", risk_domains=["authentication"]))
        self.assertFalse(route["review"]["required"])
        self.assertIsNone(route["review"]["route"])

    def test_security_review_keeps_read_only_reviewer_as_primary(self) -> None:
        dimensions = self.profile()["dimensions"]
        dimensions["consequence"] = {"rating": 3, "evidence": "security-sensitive review"}
        authority = dict(self.profile()["human_authority"], quality_first=True)
        decision = route_task.decide(
            self.profile(
                kind="review",
                phase="review",
                dimensions=dimensions,
                risk_domains=["security", "authentication"],
                read_only=True,
                write_scopes=[],
                human_authority=authority,
            )
        )
        self.assertEqual(decision["primary"]["agent"], "gpt56_router_sol_reviewer")
        self.assertEqual(decision["primary"]["reasoning_effort"], "high")
        self.assertTrue(decision["primary"]["read_only"])

    def test_overlapping_write_scopes_cannot_run_in_parallel(self) -> None:
        self.assertFalse(route_task.may_parallelize([["/repo/app"], ["/repo/app/api.py"]]))
        self.assertFalse(route_task.may_parallelize([["C:\\repo\\app"], ["C:\\repo\\app\\api.py"]]))

    def test_disjoint_or_explicitly_read_only_scopes_may_run_in_parallel(self) -> None:
        self.assertTrue(route_task.may_parallelize([["/repo/app"], ["/repo/tests"]]))
        self.assertTrue(route_task.may_parallelize([[], ["/repo/app"]], [True, False]))

    def test_empty_unknown_writer_scope_cannot_run_in_parallel(self) -> None:
        self.assertFalse(route_task.may_parallelize([[], ["/repo/app"]]))

    def test_consequential_domain_forces_review(self) -> None:
        decision = route_task.decide(self.profile(risk_domains=["authentication"]))
        self.assertTrue(decision["review"]["required"])
        self.assertEqual(decision["review"]["route"]["agent"], "gpt56_router_sol_reviewer")
        self.assertIn("INDEPENDENT_REVIEW_REQUIRED", decision["reason_codes"])

    def test_consequential_read_only_work_still_requires_independent_review(self) -> None:
        decision = route_task.decide(self.profile(risk_domains=["personal_data"], read_only=True, write_scopes=[]))
        self.assertTrue(decision["review"]["required"])

    def test_decision_exposes_delegation_and_parallel_contracts(self) -> None:
        request = {
            "requested": True,
            "authorize_descendants": True,
            "allowed_roles": ["gpt56_router_terra_explorer"],
            "max_children": 3,
            "max_parallel_children": 2,
            "allowed_write_scopes": [],
            "may_spawn_writers": False,
        }
        decision = route_task.decide(self.profile(kind="ambiguous", delegation_request=request))
        self.assertTrue(decision["delegation_capability"]["allowed"])
        self.assertEqual(decision["delegation_capability"]["remaining_depth"], 1)
        self.assertTrue(decision["parallel_eligibility"]["eligible"])

    def test_delegation_does_not_invent_router_specific_forbidden_actions(self) -> None:
        request = {
            "requested": True,
            "authorize_descendants": True,
            "allowed_roles": ["gpt56_router_terra_explorer"],
            "max_children": 1,
            "max_parallel_children": 1,
            "may_spawn_writers": False,
        }
        decision = route_task.decide(self.profile(kind="ambiguous", delegation_request=request))
        self.assertEqual(decision["delegation_capability"]["forbidden_actions"], [])

    def test_writer_descendant_authority_is_never_emitted_without_writer_permission(self) -> None:
        request = {
            "requested": True,
            "authorize_descendants": True,
            "allowed_roles": ["gpt56_router_luna_worker"],
            "max_children": 1,
            "max_parallel_children": 1,
            "may_spawn_writers": False,
        }
        decision = route_task.decide(self.profile(kind="ambiguous", delegation_request=request))
        self.assertFalse(decision["delegation_capability"]["allowed"])
        self.assertEqual(decision["delegation_capability"]["allowed_roles"], [])

    def test_duplicate_delegation_request_roles_are_rejected_before_decision_output(self) -> None:
        request = {
            "requested": True, "authorize_descendants": True,
            "allowed_roles": ["gpt56_router_terra_explorer", "gpt56_router_terra_explorer"],
            "max_children": 1, "max_parallel_children": 1,
            "may_spawn_writers": False,
        }
        with self.assertRaisesRegex(route_task.ContractError, "unique items"):
            route_task.decide(self.profile(kind="ambiguous", delegation_request=request))

    def test_route_decision_capability_is_accepted_by_spawn_builder(self) -> None:
        request = {
            "requested": True, "authorize_descendants": True,
            "allowed_roles": ["gpt56_router_terra_explorer"],
            "max_children": 1, "max_parallel_children": 1,
            "may_spawn_writers": False,
        }
        decision = route_task.decide(self.profile(kind="ambiguous", delegation_request=request))
        envelope = {
            "decision": decision,
            "bounded_context": {"objective": "Own a bounded workstream"},
            "acceptance_criteria": ["Return evidence"],
            "validation_requirements": ["Validate the evidence"],
            "delegation_capability": decision["delegation_capability"],
            "supported_spawn_fields": ["agent_type"],
        }
        completed = subprocess.run(
            [sys.executable, str(MODULE_PATH.with_name("build_spawn_prompt.py")), "--input", "-", "--json"],
            input=json.dumps(envelope), text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout or completed.stderr)

    def test_unavailable_model_fails_closed(self) -> None:
        runtime = {"agent_type": False, "model_override": True, "available_models": ["gpt-5.6-luna"]}
        decision = route_task.decide(self.profile(runtime_capabilities=runtime))
        self.assertEqual(decision["decision"], "unsupported")
        self.assertIn("MODEL_UNAVAILABLE", decision["reason_codes"])

    def test_missing_runtime_capability_evidence_fails_closed(self) -> None:
        profile = self.profile()
        profile.pop("runtime_capabilities")
        decision = route_task.decide(profile)
        self.assertEqual(decision["decision"], "unsupported")
        self.assertEqual(decision["routing_mode"], "unsupported")
        self.assertIsNone(decision["primary"])
        self.assertIn("NO_ENFORCEABLE_ROUTE", decision["reason_codes"])

    def test_read_only_route_delegates_without_permission_mode_gate(self) -> None:
        runtime = {"agent_type": True, "model_override": True, "current_sandbox": "danger-full-access", "read_only_agent_sandbox_enforced": False}
        decision = route_task.decide(
            self.profile(kind="exploration", phase="exploration", read_only=True, write_scopes=[], runtime_capabilities=runtime)
        )
        self.assertEqual(decision["decision"], "delegate")
        self.assertEqual(decision["primary"]["agent"], "gpt56_router_terra_explorer")
        self.assertNotIn("READ_ONLY_SANDBOX_UNENFORCEABLE", decision["reason_codes"])

    def test_required_advisor_does_not_gate_on_parent_sandbox(self) -> None:
        dimensions = self.profile()["dimensions"]
        dimensions["ambiguity"] = {"rating": 2, "evidence": "several designs"}
        runtime = {"agent_type": True, "model_override": True, "current_sandbox": "danger-full-access", "read_only_agent_sandbox_enforced": False}
        decision = route_task.decide(
            self.profile(dimensions=dimensions, orchestrator={"model": "gpt-5.6-terra", "effort": "medium"}, runtime_capabilities=runtime)
        )
        self.assertEqual(decision["decision"], "delegate")
        self.assertTrue(decision["advisory"]["required"])
        self.assertEqual(decision["advisory"]["route"]["agent"], "gpt56_router_sol_advisor")
        self.assertNotIn("ADVISOR_ROUTE_UNENFORCEABLE", decision["reason_codes"])

    def test_direct_execution_does_not_require_runtime_capability_evidence(self) -> None:
        profile = self.profile(delegation_request={"requested": False})
        profile.pop("runtime_capabilities")
        decision = route_task.decide(profile)
        self.assertEqual(decision["decision"], "direct_execution")
        self.assertEqual(decision["routing_mode"], "direct")

    def test_decide_cli_accepts_stdin_and_legacy_cli_is_rejected(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(MODULE_PATH), "decide", "--input", "-", "--json"],
            input=json.dumps(self.profile()), text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["decision"], "delegate")

        legacy = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--kind", "implementation", "--json"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(legacy.returncode, 2)
        self.assertIn("legacy flag(s) no longer supported", legacy.stderr)

    def test_below_sol_ambiguous_writer_gets_read_only_advisor(self) -> None:
        dimensions = self.profile()["dimensions"]
        dimensions["ambiguity"] = {"rating": 2, "evidence": "two plausible designs"}
        decision = route_task.decide(self.profile(dimensions=dimensions, orchestrator={"model": "gpt-5.6-terra", "effort": "medium"}))
        self.assertEqual(decision["advisory"]["route"]["agent"], "gpt56_router_sol_advisor")
        self.assertTrue(decision["advisory"]["route"]["read_only"])

    def test_advanced_routes_require_recorded_gates(self) -> None:
        dimensions = self.profile()["dimensions"]
        dimensions["context_breadth"] = {"rating": 2, "evidence": "several packages"}
        investigation = route_task.decide(self.profile(kind="exploration", phase="exploration", dimensions=dimensions, write_scopes=[]))
        self.assertEqual(investigation["primary"]["agent"], "gpt56_router_terra_investigator")

        attempts = [{"model": "gpt-5.6-sol", "effort": "high", "outcome": "failed validation", "evidence": "test output"}]
        dimensions["ambiguity"] = {"rating": 3, "evidence": "architecture unresolved"}
        xhigh = route_task.decide(self.profile(dimensions=dimensions, prior_attempts=attempts))
        self.assertEqual(xhigh["primary"]["agent"], "gpt56_router_sol_specialist_xhigh")

        authority = dict(self.profile()["human_authority"], quality_first=True)
        maximum = route_task.decide(self.profile(dimensions=dimensions, human_authority=authority))
        self.assertEqual(maximum["primary"]["agent"], "gpt56_router_sol_specialist_max")


if __name__ == "__main__":
    unittest.main()
