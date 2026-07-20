from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts/orchestrate.py"
SPEC = importlib.util.spec_from_file_location("orchestrate", MODULE_PATH)
assert SPEC and SPEC.loader
orchestrate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = orchestrate
SPEC.loader.exec_module(orchestrate)
from router_contract import validate_completion_record, validate_task_graph

ROOT_ID = "00000000-0000-4000-8000-000000000001"
NODE_A = "00000000-0000-4000-8000-000000000002"
NODE_B = "00000000-0000-4000-8000-000000000003"
NODE_C = "00000000-0000-4000-8000-000000000004"


def profile(*nodes: dict[str, object]) -> dict[str, object]:
    return {
        "task_id": ROOT_ID,
        "objective": "Deliver the requested outcome",
        "nodes": list(nodes),
    }


def node(task_id: str = NODE_A, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_id": task_id,
        "objective": f"Work on {task_id}",
        "read_only": True,
    }
    value.update(overrides)
    return value


def event(event_type: str, node_id: str = NODE_A, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "event_type": event_type,
        "task_id": ROOT_ID,
        "node_id": node_id,
        "agent_path": "/root/worker",
        "summary": f"{event_type} result",
        "outcomes": [],
        "discovered_work": [],
        "validation": [],
        "blockers": [],
        "questions": [],
        "risks": [],
        "write_scopes": [],
        "review": {"required": False, "status": "not_required", "findings": []},
    }
    value.update(overrides)
    return value


class OrchestrationTests(unittest.TestCase):
    def test_init_uses_uuid_ids_and_locked_budgets(self) -> None:
        state = orchestrate.initialize(profile(node()))
        self.assertEqual(state["task_id"], ROOT_ID)
        self.assertEqual(
            state["budgets"],
            {
                "max_depth": 2,
                "max_open_threads": 6,
                "max_total_spawns": 8,
                "max_children_per_node": 3,
                "max_parallel_children": 2,
            },
        )
        self.assertEqual(state["nodes"][NODE_A]["status"], "ready")
        with self.assertRaisesRegex(orchestrate.OrchestrationError, "must be a UUID"):
            orchestrate.initialize({"task_id": "friendly-name", "objective": "invalid"})

    def test_dependencies_gate_readiness(self) -> None:
        state = orchestrate.initialize(
            profile(node(NODE_A), node(NODE_B, dependencies=[NODE_A]))
        )
        self.assertEqual(orchestrate.ready(state)["ready"], [NODE_A])
        state = orchestrate.apply_event(
            state,
            event("complete", validation=[{"command": "tests", "status": "passed"}]),
        )
        self.assertEqual(orchestrate.ready(state)["ready"], [NODE_B])

    def test_parallel_wave_allows_readers_and_known_disjoint_writers(self) -> None:
        readers = orchestrate.initialize(profile(node(NODE_A), node(NODE_B)))
        self.assertEqual(len(orchestrate.ready(readers)["ready"]), 2)

        writers = orchestrate.initialize(
            profile(
                node(NODE_A, read_only=False, write_scopes=["packages/api"]),
                node(NODE_B, read_only=False, write_scopes=["packages/web"]),
            )
        )
        self.assertEqual(len(orchestrate.ready(writers)["ready"]), 2)

        overlap = orchestrate.initialize(
            profile(
                node(NODE_A, read_only=False, write_scopes=["packages/api"]),
                node(NODE_B, read_only=False, write_scopes=["packages/api/tests"]),
            )
        )
        wave = orchestrate.ready(overlap)
        self.assertEqual(wave["ready"], [NODE_A])
        self.assertEqual(wave["deferred"], [{"id": NODE_B, "reason": "write scopes overlap"}])

        mixed = orchestrate.initialize(
            profile(
                node(NODE_A, read_only=True, read_scopes=["packages/api"]),
                node(NODE_B, read_only=False, write_scopes=["packages/api"]),
            )
        )
        mixed_wave = orchestrate.ready(mixed)
        self.assertEqual(mixed_wave["ready"], [NODE_A])
        self.assertEqual(mixed_wave["deferred"][0]["reason"], "reader scope overlaps writer scope")

    def test_every_plan_event_has_a_deterministic_transition(self) -> None:
        expected = {
            "progress": "running",
            "complete": "complete",
            "partial": "partial",
            "new_work": "partial",
            "needs_decision": "ready",
            "approval_required": "blocked",
            "risk_discovered": "review",
            "validation_failed": "repair",
            "blocked": "blocked",
            "conflict": "blocked",
            "budget_exhausted": "partial",
            "cancelled": "cancelled",
            "failed": "failed",
        }
        for event_type, target in expected.items():
            with self.subTest(event_type=event_type):
                state = orchestrate.initialize(profile(node()))
                overrides: dict[str, object] = {}
                if event_type == "complete":
                    overrides["validation"] = [{"command": "tests", "status": "passed"}]
                if event_type == "new_work":
                    overrides["discovered_work"] = [node(NODE_B)]
                if event_type in {"needs_decision", "approval_required"}:
                    overrides["questions"] = [{"question": "Choose a direction"}]
                result = orchestrate.apply_event(state, event(event_type, **overrides))
                self.assertEqual(result["nodes"][NODE_A]["status"], target)

    def test_semantic_decision_is_autonomously_resolved_and_requeued(self) -> None:
        state = orchestrate.initialize(profile(node()))
        result = orchestrate.apply_event(
            state,
            event("needs_decision", questions=[{"question": "Choose A or B", "recommendation": "A"}]),
        )
        self.assertEqual(result["nodes"][NODE_A]["status"], "ready")
        self.assertEqual(result["nodes"][NODE_A]["resolved_decisions"][0]["resolution"], "A")
        self.assertEqual(result["nodes"][NODE_A]["resolved_decisions"][0]["resolved_by"], "root-autonomy")
        self.assertEqual(result["nodes"][NODE_A]["decisions"], [])
        self.assertEqual(result["outstanding_human_decisions"], [])

        completed = orchestrate.apply_event(
            result,
            event("complete", validation=[{"command": "tests", "status": "passed"}]),
        )
        self.assertTrue(orchestrate.complete_check(completed, "root")["complete"])

    def test_host_approval_preserves_provenance_as_external_blocker(self) -> None:
        state = orchestrate.initialize(profile(node(read_only=False, write_scopes=["release.py"])))
        result = orchestrate.apply_event(
            state,
            event("approval_required", questions=[{"action": "deploy", "requesting_agent": "/root/worker"}]),
        )
        self.assertEqual(result["nodes"][NODE_A]["status"], "blocked")
        self.assertEqual(result["external_blockers"][0]["kind"], "host-approval-required")
        self.assertEqual(result["external_blockers"][0]["action"], "deploy")

    def test_invalid_child_event_gets_exactly_one_normalization_attempt(self) -> None:
        state = orchestrate.initialize(profile(node()))
        invalid = {"task_id": ROOT_ID, "node_id": NODE_A}
        state = orchestrate.apply_event(state, invalid)
        self.assertEqual(state["nodes"][NODE_A]["status"], "waiting")
        self.assertEqual(state["nodes"][NODE_A]["normalization_attempts"], 1)
        self.assertEqual(state["events"][-1]["trigger"], "normalization-required")
        state = orchestrate.apply_event(state, invalid)
        self.assertEqual(state["nodes"][NODE_A]["status"], "failed")
        self.assertEqual(state["nodes"][NODE_A]["normalization_attempts"], 1)
        self.assertEqual(state["events"][-1]["trigger"], "normalization-exhausted")

    def test_retired_event_alias_is_rejected_and_normalized_once(self) -> None:
        state = orchestrate.initialize(profile(node()))
        old = {
            "schema_version": 1,
            "event": "complete",
            "task_id": NODE_A,
            "agent_route": {"agent": "worker"},
            "summary": "done",
            "evidence": [],
            "validation": [{"status": "passed"}],
            "changes": [],
            "discovered_work": [],
            "escalation_signals": [],
            "human_decisions": [],
            "residual_risks": [],
            "undispatched_work": [],
        }
        with self.assertRaisesRegex(orchestrate.OrchestrationError, "unknown task"):
            orchestrate.apply_event(state, old)

    def test_review_repair_loop_stops_after_two_cycles(self) -> None:
        state = orchestrate.initialize(profile(node()))
        failure = event("validation_failed", validation=[{"status": "failed"}])
        state = orchestrate.apply_event(state, failure)
        self.assertEqual(state["nodes"][NODE_A]["status"], "repair")
        state = orchestrate.apply_event(state, failure)
        self.assertEqual(state["nodes"][NODE_A]["status"], "repair")
        state = orchestrate.apply_event(state, failure)
        self.assertEqual(state["nodes"][NODE_A]["status"], "blocked")
        self.assertEqual(state["nodes"][NODE_A]["repair_cycles"], 2)

    def test_completion_gate_is_root_only_and_enumerates_failures(self) -> None:
        state = orchestrate.initialize(profile(node(required_review=True)))
        incomplete = orchestrate.complete_check(state, "root")
        self.assertFalse(incomplete["complete"])
        self.assertIn("status:ready", {item["gate"] for item in incomplete["unmet_gates"]})
        with self.assertRaisesRegex(orchestrate.OrchestrationError, "only the root"):
            orchestrate.complete_check(state, "worker")

        implemented = orchestrate.apply_event(
            state,
            event(
                "complete",
                validation=[{"status": "passed"}],
                review={"required": True, "status": "pending", "findings": []},
            ),
        )
        finished = orchestrate.apply_event(
            implemented,
            event(
                "complete",
                agent_path="/root/reviewer",
                validation=[{"status": "passed"}],
                review={"required": True, "status": "passed", "findings": []},
            ),
        )
        completion = orchestrate.complete_check(finished, "root")
        self.assertTrue(completion["complete"])
        validate_completion_record(completion)

    def test_implementer_cannot_satisfy_its_own_mandatory_review(self) -> None:
        state = orchestrate.initialize(
            profile(node(required_review=True, route_history=["gpt56_router_sol_debugger"]))
        )
        self_review = event(
            "complete",
            agent_path="/root/implementer",
            validation=[{"status": "passed"}],
            review={"required": True, "status": "passed", "findings": []},
        )
        rejected = orchestrate.apply_event(state, self_review)
        self.assertEqual(rejected["nodes"][NODE_A]["status"], "waiting")
        self.assertFalse(rejected["nodes"][NODE_A]["review"]["complete"])
        self.assertIn("independent", rejected["events"][-1]["data"]["errors"][0])

        implemented = orchestrate.apply_event(
            rejected,
            event(
                "complete",
                agent_path="/root/implementer",
                validation=[{"status": "passed"}],
                review={"required": True, "status": "pending", "findings": []},
            ),
        )
        self.assertEqual(implemented["nodes"][NODE_A]["status"], "review")
        reviewed = orchestrate.apply_event(
            implemented,
            event(
                "complete",
                agent_path="/root/reviewer",
                validation=[{"status": "passed"}],
                review={"required": True, "status": "passed", "findings": []},
            ),
        )
        self.assertEqual(reviewed["nodes"][NODE_A]["status"], "complete")
        self.assertTrue(orchestrate.complete_check(reviewed, "root")["complete"])

    def test_status_exposes_valid_public_task_graph_projection(self) -> None:
        state = orchestrate.initialize(profile(node(required_review=True)))
        graph = orchestrate.status(state)["task_graph"]
        validate_task_graph(graph)
        self.assertEqual(graph["root_task_id"], ROOT_ID)
        self.assertEqual(graph["remaining_review"], [NODE_A])
        self.assertEqual(graph["budgets"], orchestrate.DEFAULT_BUDGETS)

    def test_unresolved_review_findings_block_completion_until_clean_rereview(self) -> None:
        state = orchestrate.initialize(profile(node(required_review=True)))
        state = orchestrate.apply_event(
            state,
            event("complete", validation=[{"status": "passed"}], review={"required": True, "status": "pending", "findings": []}),
        )
        finding = {"severity": "HIGH", "summary": "unsafe edge case"}
        state = orchestrate.apply_event(
            state,
            event("complete", agent_path="/root/reviewer-1", validation=[{"status": "passed"}], review={"required": True, "status": "passed", "findings": [finding]}),
        )
        self.assertFalse(orchestrate.complete_check(state, "root")["complete"])
        self.assertFalse(state["nodes"][NODE_A]["review"]["complete"])
        state = orchestrate.apply_event(
            state,
            event("validation_failed", agent_path="/root/repair", validation=[{"status": "failed"}], review={"required": True, "status": "pending", "findings": [finding]}),
        )
        state = orchestrate.apply_event(
            state,
            event("complete", agent_path="/root/repair", validation=[{"status": "passed"}], review={"required": True, "status": "pending", "findings": [finding]}),
        )
        state = orchestrate.apply_event(
            state,
            event("complete", agent_path="/root/reviewer-2", validation=[{"status": "passed"}], review={"required": True, "status": "passed", "findings": []}),
        )
        self.assertTrue(orchestrate.complete_check(state, "root")["complete"])

    def test_leaf_cannot_turn_discovered_work_into_schedulable_descendants(self) -> None:
        state = orchestrate.initialize(profile(node()))
        state = orchestrate.apply_event(state, event("new_work", discovered_work=[node(NODE_B)]))
        self.assertNotIn(NODE_B, state["nodes"])
        self.assertEqual(state["nodes"][NODE_A]["status"], "partial")
        self.assertEqual(state["nodes"][NODE_A]["result"]["undispatched_work"][0]["task_id"], NODE_B)

    def test_discovered_batch_is_all_or_nothing(self) -> None:
        capability = {
            "schema_version": 1, "allowed": True, "remaining_depth": 1,
            "max_children": 1, "max_parallel_children": 1,
            "allowed_roles": ["gpt56_router_terra_explorer"],
            "allowed_models": ["gpt-5.6-terra"], "allowed_write_scopes": [],
            "may_spawn_writers": False, "forbidden_actions": [], "required_return": [],
        }
        owner = node(delegation_capability=capability, route_history=["gpt56_router_sol_engineer"])
        state = orchestrate.initialize(profile(owner))
        work = [
            node(NODE_B, route={"agent": "gpt56_router_terra_explorer", "model": "gpt-5.6-terra"}),
            node(NODE_C, route={"agent": "gpt56_router_terra_explorer", "model": "gpt-5.6-terra"}),
        ]
        state = orchestrate.apply_event(state, event("new_work", discovered_work=work))
        self.assertNotIn(NODE_B, state["nodes"])
        self.assertNotIn(NODE_C, state["nodes"])
        self.assertEqual(len(state["nodes"][NODE_A]["result"]["undispatched_work"]), 2)

    def test_authorized_owner_creates_leaf_then_returns_for_synthesis(self) -> None:
        capability = {
            "schema_version": 1,
            "allowed": True,
            "remaining_depth": 1,
            "max_children": 3,
            "max_parallel_children": 2,
            "allowed_roles": ["gpt56_router_luna_worker"],
            "allowed_models": ["gpt-5.6-luna"],
            "allowed_write_scopes": [],
            "may_spawn_writers": True,
            "forbidden_actions": ["external writes"],
            "required_return": ["child event"],
        }
        state = orchestrate.initialize(profile(node(delegation_capability=capability, route_history=["gpt56_router_sol_engineer"])))
        discovered = node(
            NODE_B,
            route={"agent": "gpt56_router_luna_worker", "model": "gpt-5.6-luna"},
        )
        state = orchestrate.apply_event(state, event("new_work", discovered_work=[discovered]))
        self.assertEqual(state["nodes"][NODE_A]["status"], "waiting")
        state = orchestrate.apply_event(state, event("complete", NODE_B, validation=[{"status": "passed"}]))
        self.assertEqual(state["nodes"][NODE_A]["status"], "ready")

    def test_dispatch_reserves_wave_and_prevents_duplicate_spawns(self) -> None:
        state = orchestrate.initialize(profile(node()))
        state, first = orchestrate.dispatch(state)
        self.assertEqual(first["ready"], [NODE_A])
        self.assertEqual(state["nodes"][NODE_A]["status"], "running")
        self.assertEqual(state["usage"]["total_spawns"], 1)
        state, second = orchestrate.dispatch(state)
        self.assertEqual(second["ready"], [])
        self.assertEqual(state["usage"]["total_spawns"], 1)

    def test_human_control_pause_resume_redirect_and_external_blocker_resolution(self) -> None:
        state = orchestrate.initialize(profile(node(status="running"), node(NODE_B)))
        state = orchestrate.apply_control(state, {"action": "pause", "reason": "user requested pause"})
        self.assertEqual(orchestrate.ready(state)["ready"], [])
        state = orchestrate.apply_control(state, {"action": "resume", "task_ids": [NODE_A]})
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["nodes"][NODE_A]["status"], "ready")

        replacement = node(NODE_C)
        state = orchestrate.apply_control(state, {"action": "redirect", "task_ids": [NODE_B], "profiles": [replacement]})
        self.assertEqual(state["nodes"][NODE_B]["status"], "cancelled")
        self.assertTrue(state["nodes"][NODE_B]["superseded"])
        self.assertEqual(state["nodes"][NODE_C]["status"], "ready")

        state = orchestrate.apply_event(
            state,
            event("blocked", NODE_C, blockers=[{"summary": "vendor", "owner": "vendor", "resume_condition": "online"}]),
        )
        self.assertEqual(state["external_blockers"][0]["owner"], "vendor")
        state = orchestrate.apply_control(state, {"action": "resolve_blocker", "task_ids": [NODE_C]})
        self.assertEqual(state["external_blockers"], [])
        self.assertEqual(state["nodes"][NODE_C]["status"], "ready")

    def test_redirected_node_does_not_block_completion_but_plain_cancellation_does(self) -> None:
        redirected = orchestrate.initialize(profile(node(NODE_A)))
        redirected = orchestrate.apply_control(
            redirected,
            {"action": "redirect", "task_ids": [NODE_A], "profiles": [node(NODE_B)]},
        )
        redirected = orchestrate.apply_event(
            redirected,
            event("complete", NODE_B, validation=[{"status": "passed"}]),
        )
        self.assertTrue(orchestrate.complete_check(redirected, "root")["complete"])

        cancelled = orchestrate.initialize(profile(node(NODE_A)))
        cancelled = orchestrate.apply_control(cancelled, {"action": "cancel", "task_ids": [NODE_A]})
        self.assertFalse(orchestrate.complete_check(cancelled, "root")["complete"])

    def test_direct_execution_must_complete_the_root_node(self) -> None:
        state = orchestrate.initialize(profile())
        self.assertFalse(orchestrate.complete_check(state, "root")["complete"])
        state = orchestrate.apply_event(
            state,
            event("complete", ROOT_ID, validation=[{"status": "passed"}]),
        )
        self.assertTrue(orchestrate.complete_check(state, "root")["complete"])

    def test_atomic_persistence_has_required_failure_and_warning_fallback(self) -> None:
        state = orchestrate.initialize(profile(node()))
        with mock.patch.object(orchestrate, "_atomic_replace", side_effect=OSError("disk offline")):
            with self.assertRaisesRegex(orchestrate.DurabilityError, "durability update failed"):
                orchestrate.persist(state, Path("state.json"), required=True)
            fallback = orchestrate.persist(state, Path("state.json"), required=False)
        self.assertEqual(fallback["warnings"][0]["kind"], "durability")

    def test_parallel_cli_events_are_serialized_without_lost_updates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "state.json"
            initial = orchestrate.initialize(profile(node(NODE_A), node(NODE_B)), str(ledger))
            orchestrate.persist(initial, ledger)
            waiting = subprocess.Popen(
                [sys.executable, str(MODULE_PATH), "apply-event", "--ledger", str(ledger), "--json"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                time.sleep(0.1)  # The first process is blocked on stdin and must not hold the ledger lock.
                completed = subprocess.run(
                    [sys.executable, str(MODULE_PATH), "apply-event", "--ledger", str(ledger), "--json"],
                    input=json.dumps(event("complete", NODE_B, validation=[{"status": "passed"}])),
                    text=True, capture_output=True, check=False, timeout=5,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
                stdout, stderr = waiting.communicate(
                    json.dumps(event("complete", NODE_A, validation=[{"status": "passed"}])),
                    timeout=5,
                )
                self.assertEqual(waiting.returncode, 0, stderr or stdout)
            finally:
                if waiting.poll() is None:
                    waiting.kill()
                    waiting.communicate(timeout=5)
            restored = orchestrate.load_json(ledger)
            self.assertEqual(restored["nodes"][NODE_A]["status"], "complete")
            self.assertEqual(restored["nodes"][NODE_B]["status"], "complete")

    def test_complexity_trigger_assigns_workspace_ledger_path(self) -> None:
        state = orchestrate.initialize(profile(node(NODE_A), node(NODE_B), node(NODE_C)))
        self.assertTrue(state["ledger"]["required"])
        self.assertIn("graph-over-three-nodes", state["ledger"]["triggered_by"])
        self.assertEqual(
            Path(state["ledger"]["path"]),
            Path.cwd() / ".codex" / "gpt56-router" / f"{ROOT_ID}.json",
        )

    def test_cli_automatically_persists_complex_workflow_in_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "profile.json"
            automatic = profile(node(NODE_A), node(NODE_B), node(NODE_C))
            automatic["workspace_root"] = directory
            input_path.write_text(json.dumps(automatic))
            completed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "init", "--input", str(input_path)],
                cwd=directory, text=True, capture_output=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            ledger = Path(directory) / ".codex" / "gpt56-router" / f"{ROOT_ID}.json"
            self.assertTrue(ledger.is_file())
            self.assertEqual(json.loads(ledger.read_text())["task_id"], ROOT_ID)

    def test_cli_supports_json_state_and_jsonl_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "profile.json"
            ledger = Path(directory) / "orchestration.jsonl"
            input_path.write_text(json.dumps(profile(node())))
            initialized = subprocess.run(
                [sys.executable, str(MODULE_PATH), "init", "--input", str(input_path), "--ledger", str(ledger), "--json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            self.assertIn("task_graph", json.loads(initialized.stdout))
            ready = subprocess.run(
                [sys.executable, str(MODULE_PATH), "ready", "--ledger", str(ledger), "--json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertEqual(json.loads(ready.stdout)["ready"], [NODE_A])
            applied = subprocess.run(
                [sys.executable, str(MODULE_PATH), "apply-event", "--ledger", str(ledger), "--json"],
                input=json.dumps(event("complete", validation=[{"status": "passed"}])),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(json.loads(applied.stdout)["nodes"][NODE_A]["status"], "complete")
            status_result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "status", "--ledger", str(ledger), "--json"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(status_result.returncode, 0, status_result.stderr)
            validate_task_graph(json.loads(status_result.stdout)["task_graph"])
            completion_result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "complete-check", "--ledger", str(ledger), "--json"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(completion_result.returncode, 0, completion_result.stderr)
            validate_completion_record(json.loads(completion_result.stdout))


if __name__ == "__main__":
    unittest.main()
