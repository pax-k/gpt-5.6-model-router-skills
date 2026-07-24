from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts"
sys.path.insert(0, str(SCRIPTS))
import route_guard  # noqa: E402
import route_task  # noqa: E402


AGENTS = list(route_task.ROLES.values())
MODELS = ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]
FIXTURES = json.loads((ROOT / "tests/fixtures/hook-events-v4.json").read_text())


class RouteGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plugin_data = self.root / "plugin-data"
        self.cwd = self.root / "repo"
        self.cwd.mkdir()
        self.session_id = "session-1"
        self.turn_id = "turn-1"
        self.root_transcript = str(self.root / "root.jsonl")
        self.environment = mock.patch.dict(os.environ, {"PLUGIN_DATA": str(self.plugin_data)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @property
    def state_dir(self) -> Path:
        return self.plugin_data / "governor"

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

    def intent(self, **overrides):
        value = {
            "schema_version": 4,
            "profile": self.profile(),
            "execution_mode": "delegate",
            "task_name": "bounded-work",
            "objective": "Complete the bounded work.",
            "references": ["README.md"],
            "owned_paths": ["src/a"],
            "constraints": ["Preserve public behavior."],
            "verification": ["python3 -m unittest"],
            "fork_turns": "none",
            "delegation_grant": "none",
            "commit_authority": False,
            "supported_spawn_fields": ["agent_type"],
        }
        value.update(overrides)
        return value

    def activate(self, prompt="$route-gpt56-task Complete the task."):
        return route_guard.hook_user_prompt(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "prompt": prompt,
                "transcript_path": self.root_transcript,
                "cwd": str(self.cwd),
                "model": "gpt-5.6-sol",
            }
        )

    def prepare(self, payload=None):
        return route_guard.prepare(
            payload or self.intent(),
            state_dir=self.state_dir,
            session_id=self.session_id,
            turn_id=self.turn_id,
            cwd=self.cwd,
        )

    def pre_agent(self, request, transcript=None, tool_use_id="tool-1"):
        return route_guard.hook_pre_tool(
            {
                "hook_event_name": "PreToolUse",
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "transcript_path": transcript or self.root_transcript,
                "cwd": str(self.cwd),
                "tool_name": "Agent",
                "tool_use_id": tool_use_id,
                "tool_input": request,
            }
        )

    def post_agent(self, request, agent_id, tool_use_id="tool-1"):
        return route_guard.hook_post_tool(
            {
                "hook_event_name": "PostToolUse",
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "transcript_path": self.root_transcript,
                "cwd": str(self.cwd),
                "tool_name": "Agent",
                "tool_use_id": tool_use_id,
                "tool_input": request,
                "tool_response": {"agent_id": agent_id},
            }
        )

    def start_agent(self, prepared, agent_id, transcript):
        route = prepared["data"]["selected_route"]
        return route_guard.hook_subagent_start(
            {
                "hook_event_name": "SubagentStart",
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "agent_id": agent_id,
                "agent_type": route["agent"],
                "transcript_path": transcript,
                "cwd": str(self.cwd),
                "model": route["model"],
                "model_reasoning_effort": route["reasoning_effort"],
            }
        )

    def stop_agent(self, intent_id, agent_id, result):
        return route_guard.hook_subagent_stop(
            {
                "hook_event_name": "SubagentStop",
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "agent_id": agent_id,
                "cwd": str(self.cwd),
                "last_assistant_message": result,
            }
        )

    def test_every_turn_gets_spawn_enforcement_but_only_exact_invocation_is_explicit(self):
        ordinary = self.activate("ordinary delegation request")
        self.assertIn("Before every Agent spawn", ordinary["hookSpecificOutput"]["additionalContext"])
        ordinary_state = route_guard._load_state(
            route_guard._state_path(self.state_dir, self.session_id, self.turn_id)
        )
        self.assertFalse(ordinary_state["explicit_invocation"])

        self.turn_id = "turn-2"
        near_match = self.activate("$route-gpt56-task-extra is not the skill")
        self.assertIn("Before every Agent spawn", near_match["hookSpecificOutput"]["additionalContext"])
        near_state = route_guard._load_state(
            route_guard._state_path(self.state_dir, self.session_id, self.turn_id)
        )
        self.assertFalse(near_state["explicit_invocation"])

        self.turn_id = "turn-3"
        output = self.activate()
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        explicit_state = route_guard._load_state(
            route_guard._state_path(self.state_dir, self.session_id, self.turn_id)
        )
        self.assertTrue(explicit_state["explicit_invocation"])

    def test_missing_plugin_data_fails_closed_for_agent_spawns(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            output = route_guard.hook_pre_tool(
                {
                    "session_id": "ordinary",
                    "turn_id": "ordinary",
                    "tool_name": "Agent",
                    "tool_input": {"task_name": "ordinary", "message": "ordinary"},
                }
            )
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("state is unavailable", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_missing_prompt_hook_state_fails_closed_only_for_agent(self):
        denied = self.pre_agent(
            {"task_name": "unprepared", "message": "no intent", "fork_turns": "none"}
        )
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("prompt hook", denied["hookSpecificOutput"]["permissionDecisionReason"])
        unaffected = route_guard.hook_pre_tool(
            {
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "tool_name": "Bash",
                "tool_input": {"command": "git status --short"},
            }
        )
        self.assertEqual(unaffected, {})

    def test_sanitized_hook_event_fixtures_cover_global_spawn_boundary(self):
        ordinary = dict(FIXTURES["ordinary_prompt"])
        ordinary.update(cwd=str(self.cwd), transcript_path=self.root_transcript)
        ordinary_output = route_guard.hook_user_prompt(ordinary)
        self.assertIn("Before every Agent spawn", ordinary_output["hookSpecificOutput"]["additionalContext"])
        routed = dict(FIXTURES["router_prompt"])
        routed.update(cwd=str(self.cwd), transcript_path=self.root_transcript)
        route_guard.hook_user_prompt(routed)
        invalid = dict(FIXTURES["invalid_agent"])
        invalid.update(cwd=str(self.cwd), transcript_path=self.root_transcript)
        denied = route_guard.hook_pre_tool(invalid)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_valid_custom_agent_spawn_is_allowed_exactly_once(self):
        self.activate("ordinary request that may need delegation")
        prepared = self.prepare()
        self.assertTrue(prepared["ok"])
        request = prepared["data"]["spawn_request"]
        self.assertEqual(self.pre_agent(request), {})
        denied = self.pre_agent(request, tool_use_id="tool-2")
        self.assertEqual(
            denied["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )

    def test_ordinary_root_only_turn_closes_without_route_intent(self):
        self.activate("Answer this directly without delegation.")
        closed = route_guard.hook_stop(
            {
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "cwd": str(self.cwd),
            }
        )
        self.assertTrue(closed["continue"])

    def test_missing_modified_and_sensitive_handoffs_are_denied(self):
        self.activate()
        missing = self.pre_agent(
            {"task_name": "x", "message": "no intent", "fork_turns": "none", "agent_type": "default"}
        )
        self.assertEqual(missing["hookSpecificOutput"]["permissionDecision"], "deny")

        # Use a clean turn because denials are retained as structural violations.
        self.turn_id = "turn-2"
        self.activate()
        prepared = self.prepare(self.intent(task_name="exact-request"))
        request = dict(prepared["data"]["spawn_request"])
        request["task_name"] = "changed"
        changed = self.pre_agent(request)
        self.assertEqual(changed["hookSpecificOutput"]["permissionDecision"], "deny")

        self.turn_id = "turn-3"
        self.activate()
        secret = "sk-" + "A" * 24
        prepared = self.prepare(self.intent(task_name="secret-work", objective=f"Use {secret}"))
        denied = self.pre_agent(prepared["data"]["spawn_request"])
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        state_text = route_guard._state_path(self.state_dir, self.session_id, self.turn_id).read_text()
        self.assertNotIn(secret, state_text)
        self.assertNotIn("Complete the bounded work.", state_text)
        self.assertNotIn(self.session_id, state_text)
        self.assertNotIn(self.turn_id, state_text)

    def test_model_override_requires_exact_model_and_effort(self):
        self.activate()
        runtime = {
            "custom_agent": False,
            "model_override": True,
            "available_agents": [],
            "available_models": MODELS,
        }
        prepared = self.prepare(
            self.intent(
                task_name="model-override",
                profile=self.profile(runtime_capabilities=runtime),
                supported_spawn_fields=["model", "reasoning_effort"],
            )
        )
        self.assertTrue(prepared["ok"])
        request = prepared["data"]["spawn_request"]
        self.assertEqual(self.pre_agent(request), {})

    def test_inherited_root_execution_is_valid_but_custom_full_history_is_not(self):
        self.activate()
        inherited = self.intent(
            execution_mode="inherited",
            task_name="inherited-root",
            fork_turns="all",
            owned_paths=[],
            override={
                "reason_code": "INHERITED_ROOT_EXECUTION",
                "rationale": "The child needs the complete root execution context.",
                "authority": {"authority": "user", "reference": "approved task contract"},
            },
        )
        prepared = self.prepare(inherited)
        self.assertTrue(prepared["ok"])
        request = prepared["data"]["spawn_request"]
        self.assertNotIn("agent_type", request)
        self.assertNotIn("model", request)
        self.assertEqual(self.pre_agent(request), {})

        self.turn_id = "turn-2"
        self.activate()
        custom = self.intent(task_name="custom-all", fork_turns="all")
        with self.assertRaisesRegex(route_guard.ContractError, "requires inherited execution"):
            self.prepare(custom)

    def test_retired_specialist_route_is_rejected(self):
        selected = {
            "agent": "gpt56_router_sol_specialist_max",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "max",
            "read_only": False,
        }
        self.activate()
        with self.assertRaisesRegex(route_guard.ContractError, "not a bundled role"):
            self.prepare(self.intent(task_name="retired-max", selected_route=selected))

    def test_positive_fork_requires_recorded_rationale(self):
        self.activate()
        rejected = self.prepare(self.intent(task_name="bounded-fork", fork_turns="2"))
        self.assertFalse(rejected["ok"])
        accepted = self.prepare(
            self.intent(
                task_name="bounded-fork-rationale",
                fork_turns="2",
                override={
                    "reason_code": "BOUNDED_CONTEXT_REQUIRED",
                    "rationale": "Two recent turns contain the necessary decision context.",
                    "authority": {"authority": "root", "reference": "task brief context boundary"},
                },
            )
        )
        self.assertTrue(accepted["ok"])

    def test_route_deviation_requires_non_root_authority(self):
        self.activate("ordinary governed delegation")
        luna = {
            "agent": "gpt56_router_luna_worker",
            "model": "gpt-5.6-luna",
            "reasoning_effort": "high",
            "read_only": False,
        }
        root_override = self.prepare(
            self.intent(
                task_name="root-route-deviation",
                selected_route=luna,
                override={
                    "reason_code": "ROOT_PREFERS_LUNA",
                    "rationale": "The root prefers a cheaper worker.",
                    "authority": {"authority": "root", "reference": "root routing rationale"},
                },
            )
        )
        self.assertFalse(root_override["ok"])
        self.assertIn(
            "route deviations require user, task_contract, or recorded_failure authority",
            root_override["errors"],
        )
        user_override = self.prepare(
            self.intent(
                task_name="authorized-route-deviation",
                selected_route=luna,
                owned_paths=["src/b"],
                override={
                    "reason_code": "USER_SELECTED_LUNA",
                    "rationale": "The user selected Luna/high for this bounded task.",
                    "authority": {"authority": "user", "reference": "current user instruction"},
                },
            )
        )
        self.assertTrue(user_override["ok"])

    def test_recorded_failure_profile_authorizes_escalation(self):
        self.activate()
        escalation_profile = self.profile(
            prior_route_failure={
                "agent": "gpt56_router_sol_debugger",
                "model": "gpt-5.6-sol",
                "effort": "high",
                "evidence": "verification failure audit-1",
            }
        )
        accepted = self.prepare(
            self.intent(task_name="recorded-failure", profile=escalation_profile)
        )
        self.assertTrue(accepted["ok"])
        self.assertEqual(
            accepted["data"]["selected_route"]["reasoning_effort"],
            "high",
        )
        self.assertEqual(
            accepted["data"]["selected_route"]["agent"],
            "gpt56_router_sol_debugger",
        )

    def test_child_commit_commands_are_denied_without_authority(self):
        self.activate()
        prepared = self.prepare(self.intent(task_name="no-commit"))
        request = prepared["data"]["spawn_request"]
        self.pre_agent(request)
        self.post_agent(request, "agent-no-commit")
        transcript = str(self.root / "no-commit.jsonl")
        self.start_agent(prepared, "agent-no-commit", transcript)
        denied = route_guard.hook_pre_tool(
            {
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "transcript_path": transcript,
                "tool_name": "Bash",
                "tool_input": {"command": "git commit -am synthetic"},
            }
        )
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        for command in (
            "git -c user.name=Synthetic commit -am synthetic",
            "echo ready\ngit push origin synthetic",
            "command git tag synthetic",
        ):
            denied = route_guard.hook_pre_tool(
                {
                    "session_id": self.session_id,
                    "turn_id": self.turn_id,
                    "transcript_path": transcript,
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                }
            )
            self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_post_head_change_is_reported_as_a_violation(self):
        subprocess.run(["git", "init", "-q"], cwd=self.cwd, check=True)
        subprocess.run(["git", "config", "user.name", "Synthetic Test"], cwd=self.cwd, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.cwd, check=True)
        tracked = self.cwd / "tracked.txt"
        tracked.write_text("before\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.cwd, check=True)
        subprocess.run(["git", "commit", "-qm", "initial"], cwd=self.cwd, check=True)

        self.activate()
        prepared = self.prepare(self.intent(task_name="head-observation"))
        request = prepared["data"]["spawn_request"]
        self.pre_agent(request)
        self.post_agent(request, "agent-head")
        self.start_agent(prepared, "agent-head", str(self.root / "head.jsonl"))

        tracked.write_text("after\n")
        subprocess.run(["git", "commit", "-qam", "unauthorized"], cwd=self.cwd, check=True)
        intent_id = prepared["data"]["intent_id"]
        stopped = self.stop_agent(
            intent_id,
            "agent-head",
            f'Router-Result: {{"intent_id":"{intent_id}","outcome":"ok"}}',
        )
        self.assertFalse(stopped["continue"])
        audit = route_guard.audit(
            state_dir=self.state_dir,
            session_id=self.session_id,
            turn_id=self.turn_id,
        )
        self.assertIn("HEAD_CHANGED_WITHOUT_COMMIT_AUTHORITY", audit["errors"])

    def test_missing_runtime_metadata_is_warned_not_invented(self):
        self.activate()
        prepared = self.prepare(self.intent(task_name="missing-metadata"))
        request = prepared["data"]["spawn_request"]
        self.pre_agent(request)
        self.post_agent(request, "agent-missing")
        route = prepared["data"]["selected_route"]
        route_guard.hook_subagent_start(
            {
                "session_id": self.session_id,
                "agent_id": "agent-missing",
                "agent_type": route["agent"],
                "transcript_path": str(self.root / "missing.jsonl"),
                "cwd": str(self.cwd),
            }
        )
        audit = route_guard.audit(
            state_dir=self.state_dir,
            session_id=self.session_id,
            turn_id=self.turn_id,
        )
        self.assertIn("SUBAGENT_MODEL_METADATA_UNAVAILABLE", audit["warnings"])
        self.assertIn("SUBAGENT_EFFORT_METADATA_UNAVAILABLE", audit["warnings"])
        self.assertIn("SUBAGENT_FORK_METADATA_UNAVAILABLE", audit["warnings"])
        self.assertIn("SUBAGENT_DEPTH_METADATA_UNAVAILABLE", audit["warnings"])
        route_evidence = audit["data"]["routes"][0]
        self.assertIsNone(route_evidence["actual_model"])
        self.assertIsNone(route_evidence["actual_effort"])
        self.assertIsNone(route_evidence["actual_fork_turns"])
        self.assertIsNone(route_evidence["actual_depth"])
        state_text = route_guard._state_path(self.state_dir, self.session_id, self.turn_id).read_text()
        self.assertNotIn("agent-missing", state_text)
        self.assertNotIn("missing.jsonl", state_text)

    def test_subagent_footer_cannot_claim_another_intent(self):
        self.activate()
        first = self.prepare(self.intent(task_name="first-footer", owned_paths=["src/first"]))
        second = self.prepare(self.intent(task_name="second-footer", owned_paths=["src/second"]))
        for prepared, agent_id in ((first, "first-agent"), (second, "second-agent")):
            request = prepared["data"]["spawn_request"]
            self.pre_agent(request, tool_use_id=f"tool-{agent_id}")
            self.post_agent(request, agent_id, tool_use_id=f"tool-{agent_id}")
            self.start_agent(prepared, agent_id, str(self.root / f"{agent_id}.jsonl"))
        second_id = second["data"]["intent_id"]
        blocked = self.stop_agent(
            second_id,
            "first-agent",
            f'Router-Result: {{"intent_id":"{second_id}","outcome":"ok"}}',
        )
        self.assertFalse(blocked["continue"])
        self.assertIn("identity does not match", blocked["stopReason"])

    def test_critical_closeout_requires_runtime_floor_evidence(self):
        target = self.cwd / "critical.py"
        target.write_text("stable\n")
        self.activate()
        prepared = self.prepare(
            self.intent(
                task_name="critical-metadata",
                profile=self.profile(risk_domains=["security"]),
                owned_paths=["critical.py"],
            )
        )
        request = prepared["data"]["spawn_request"]
        self.pre_agent(request)
        self.post_agent(request, "critical-agent")
        route = prepared["data"]["selected_route"]
        route_guard.hook_subagent_start(
            {
                "session_id": self.session_id,
                "agent_id": "critical-agent",
                "agent_type": route["agent"],
                "transcript_path": str(self.root / "critical.jsonl"),
                "cwd": str(self.cwd),
            }
        )
        intent_id = prepared["data"]["intent_id"]
        self.stop_agent(
            intent_id,
            "critical-agent",
            f'Router-Result: {{"intent_id":"{intent_id}","outcome":"ok"}}',
        )
        blocked = route_guard.hook_stop(
            {"session_id": self.session_id, "turn_id": self.turn_id, "cwd": str(self.cwd)}
        )
        self.assertFalse(blocked["continue"])
        self.assertIn("runtime proof", blocked["stopReason"])

    def test_runtime_metadata_mismatches_are_structural_violations(self):
        self.activate()
        prepared = self.prepare(self.intent(task_name="runtime-mismatch"))
        request = prepared["data"]["spawn_request"]
        self.pre_agent(request)
        self.post_agent(request, "mismatch-agent")
        route_guard.hook_subagent_start(
            {
                "session_id": self.session_id,
                "agent_id": "mismatch-agent",
                "agent_type": "gpt56_router_sol_engineer",
                "transcript_path": str(self.root / "mismatch.jsonl"),
                "cwd": str(self.cwd),
                "model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "depth": 2,
                "fork_turns": "3",
            }
        )
        audit = route_guard.audit(
            state_dir=self.state_dir,
            session_id=self.session_id,
            turn_id=self.turn_id,
        )
        for code in (
            "RUNTIME_AGENT_MISMATCH",
            "RUNTIME_MODEL_MISMATCH",
            "RUNTIME_EFFORT_MISMATCH",
            "RUNTIME_DEPTH_MISMATCH",
            "RUNTIME_FORK_MISMATCH",
        ):
            self.assertIn(code, audit["errors"])

    def test_completed_state_retention_prunes_old_and_excess_turns(self):
        for index in range(4):
            path = route_guard._state_path(self.state_dir, "retention", f"turn-{index}")
            route_guard._atomic_write(
                path,
                {
                    "state_schema": route_guard.STATE_SCHEMA,
                    "active": False,
                    "completed_at": "2026-01-01T00:00:00Z",
                },
            )
            os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))
        with mock.patch.object(route_guard, "STATE_RETENTION_DAYS", 100000), mock.patch.object(
            route_guard, "STATE_MAX_COMPLETED", 2
        ):
            route_guard._prune(self.state_dir)
        self.assertEqual(len(list(self.state_dir.glob("*/*/state.json"))), 2)

    def test_duplicate_names_and_overlapping_live_writers_reject(self):
        self.activate()
        first = self.prepare(self.intent(task_name="writer-one", owned_paths=["src/service"]))
        self.assertTrue(first["ok"])
        duplicate = self.prepare(self.intent(task_name="writer-one", owned_paths=["src/other"]))
        self.assertFalse(duplicate["ok"])
        overlap = self.prepare(self.intent(task_name="writer-two", owned_paths=["src/service/api.py"]))
        self.assertFalse(overlap["ok"])
        disjoint = self.prepare(self.intent(task_name="writer-three", owned_paths=["tests/service"]))
        self.assertTrue(disjoint["ok"])

    def test_owned_paths_are_canonical_and_cannot_escape(self):
        self.activate()
        prepared = self.prepare(
            self.intent(task_name="canonical-owner", owned_paths=["src/other/../service"])
        )
        self.assertTrue(prepared["ok"])
        audit = route_guard.audit(
            state_dir=self.state_dir,
            session_id=self.session_id,
            turn_id=self.turn_id,
        )
        state_path = Path(audit["data"]["state_path"])
        self.assertIn('"src/service"', state_path.read_text())
        with self.assertRaisesRegex(route_guard.ContractError, "escapes the working directory"):
            self.prepare(self.intent(task_name="escape-owner", owned_paths=["../outside"]))

    def test_depth_one_child_cannot_delegate_and_grants_are_rejected(self):
        self.activate()
        parent = self.prepare(self.intent(task_name="parent", delegation_grant="none", owned_paths=["src/a"]))
        request = parent["data"]["spawn_request"]
        self.assertEqual(self.pre_agent(request), {})
        self.post_agent(request, "agent-parent")
        child_transcript = str(self.root / "child.jsonl")
        self.start_agent(parent, "agent-parent", child_transcript)
        descendant = self.prepare(
            self.intent(task_name="descendant", owned_paths=["src/b"], delegation_grant="none")
        )
        denied = self.pre_agent(
            descendant["data"]["spawn_request"],
            transcript=child_transcript,
            tool_use_id="tool-descendant",
        )
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

        with self.assertRaisesRegex(route_guard.ContractError, "leaves at depth one"):
            self.prepare(
                self.intent(task_name="granted-parent", delegation_grant="one-level", owned_paths=["src/c"])
            )

    def test_root_intent_is_required_and_can_close_an_active_turn(self):
        self.activate()
        blocked = route_guard.hook_stop(
            {
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "cwd": str(self.cwd),
            }
        )
        self.assertFalse(blocked["continue"])
        root_intent = self.intent(
            execution_mode="root",
            task_name="root-direct",
            owned_paths=[],
            selected_route=None,
        )
        root_intent.pop("selected_route")
        prepared = self.prepare(root_intent)
        self.assertTrue(prepared["ok"])
        closed = route_guard.hook_stop(
            {
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "cwd": str(self.cwd),
            }
        )
        self.assertTrue(closed["continue"])

    def test_critical_root_accepts_any_root_model_without_override(self):
        self.activate()
        critical = self.intent(
            execution_mode="root",
            task_name="critical-root",
            profile=self.profile(risk_domains=["authentication"]),
            owned_paths=["auth.py"],
        )
        accepted = self.prepare(critical)
        self.assertTrue(accepted["ok"])
        self.assertTrue(accepted["data"]["review_required"])

    def test_critical_review_is_manifest_bound_and_stales_on_change(self):
        target = self.cwd / "auth.py"
        target.write_text("before\n")
        self.activate()
        source = self.prepare(
            self.intent(
                task_name="critical-source",
                profile=self.profile(risk_domains=["authentication"]),
                owned_paths=["auth.py"],
            )
        )
        source_request = source["data"]["spawn_request"]
        self.pre_agent(source_request)
        self.post_agent(source_request, "source-agent")
        self.start_agent(source, "source-agent", str(self.root / "source.jsonl"))
        source_id = source["data"]["intent_id"]
        self.stop_agent(
            source_id,
            "source-agent",
            f'Router-Result: {{"intent_id":"{source_id}","outcome":"ok"}}',
        )
        snapshot = route_guard.snapshot(
            state_dir=self.state_dir,
            session_id=self.session_id,
            turn_id=self.turn_id,
            intent_id=source_id,
            cwd=self.cwd,
        )
        manifest = snapshot["evidence"]["manifest_sha256"]

        review_profile = self.profile(kind="review", risk_domains=["authentication"])
        review = self.prepare(
            self.intent(
                task_name="critical-review",
                profile=review_profile,
                owned_paths=[],
                review_target={"source_intent_id": source_id, "manifest_sha256": manifest},
            )
        )
        review_request = review["data"]["spawn_request"]
        self.pre_agent(review_request, tool_use_id="review-tool")
        self.post_agent(review_request, "review-agent", tool_use_id="review-tool")
        self.start_agent(review, "review-agent", str(self.root / "review.jsonl"))
        review_id = review["data"]["intent_id"]
        self.stop_agent(
            review_id,
            "review-agent",
            f'Router-Review: {{"intent_id":"{review_id}","manifest_sha256":"{manifest}","verdict":"pass"}}',
        )
        target.write_text("after review\n")
        blocked = route_guard.hook_stop(
            {"session_id": self.session_id, "turn_id": self.turn_id, "cwd": str(self.cwd)}
        )
        self.assertFalse(blocked["continue"])
        self.assertIn("changed after its snapshot", blocked["stopReason"])

    def test_current_critical_review_allows_closeout(self):
        target = self.cwd / "payment.py"
        target.write_text("stable\n")
        self.activate()
        source = self.prepare(
            self.intent(
                task_name="payment-source",
                profile=self.profile(risk_domains=["payment"]),
                owned_paths=["payment.py"],
            )
        )
        request = source["data"]["spawn_request"]
        self.pre_agent(request)
        self.post_agent(request, "payment-agent")
        self.start_agent(source, "payment-agent", str(self.root / "payment.jsonl"))
        source_id = source["data"]["intent_id"]
        self.stop_agent(
            source_id,
            "payment-agent",
            f'Router-Result: {{"intent_id":"{source_id}","outcome":"ok"}}',
        )
        snapshot = route_guard.snapshot(
            state_dir=self.state_dir,
            session_id=self.session_id,
            turn_id=self.turn_id,
            intent_id=source_id,
            cwd=self.cwd,
        )
        manifest = snapshot["evidence"]["manifest_sha256"]
        review = self.prepare(
            self.intent(
                task_name="payment-review",
                profile=self.profile(kind="review", risk_domains=["payment"]),
                owned_paths=[],
                review_target={"source_intent_id": source_id, "manifest_sha256": manifest},
            )
        )
        review_request = review["data"]["spawn_request"]
        self.pre_agent(review_request, tool_use_id="payment-review-tool")
        self.post_agent(review_request, "payment-reviewer", tool_use_id="payment-review-tool")
        self.start_agent(review, "payment-reviewer", str(self.root / "payment-review.jsonl"))
        review_id = review["data"]["intent_id"]
        self.stop_agent(
            review_id,
            "payment-reviewer",
            f'Router-Review: {{"intent_id":"{review_id}","manifest_sha256":"{manifest}","verdict":"pass"}}',
        )
        closed = route_guard.hook_stop(
            {"session_id": self.session_id, "turn_id": self.turn_id, "cwd": str(self.cwd)}
        )
        self.assertTrue(closed["continue"])

    def test_concurrent_root_state_registration_is_atomic(self):
        self.activate()

        def register(index):
            payload = self.intent(
                execution_mode="root",
                task_name=f"root-{index}",
                owned_paths=[],
            )
            return self.prepare(payload)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(register, range(20)))
        self.assertTrue(all(result["ok"] for result in results))
        audit = route_guard.audit(
            state_dir=self.state_dir,
            session_id=self.session_id,
            turn_id=self.turn_id,
        )
        self.assertEqual(audit["evidence"]["intent_count"], 20)


if __name__ == "__main__":
    unittest.main()
