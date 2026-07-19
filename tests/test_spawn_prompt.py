from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("build_spawn_prompt", SCRIPTS / "build_spawn_prompt.py")
assert SPEC and SPEC.loader
prompt_builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prompt_builder)


DECISION = {
    "schema_version": 1,
    "task_id": "auth-session-migration",
    "node_id": "trace loader",
    "decision": "delegate",
    "primary": {"agent": "gpt56_router_terra_explorer"},
}
CONTEXT = {"objective": "Trace session loading", "read_scopes": ["packages/auth"], "current_sandbox": "read-only"}
ACCEPTANCE = ["Identify the initialization path", "Cite exact files"]
VALIDATION = ["Run the focused auth test without modifying files"]


def delegation_capability(**overrides: object) -> dict[str, object]:
    capability: dict[str, object] = {
        "schema_version": 1,
        "allowed": True,
        "remaining_depth": 1,
        "max_children": 2,
        "max_parallel_children": 1,
        "allowed_roles": ["gpt56_router_terra_explorer"],
        "allowed_models": ["gpt-5.6-terra"],
        "allowed_write_scopes": [],
        "may_spawn_writers": False,
        "forbidden_actions": ["external-writes", "destructive-actions"],
        "required_return": ["child-results"],
    }
    capability.update(overrides)
    return capability


class SpawnPromptTests(unittest.TestCase):
    def test_prefers_custom_agent_and_uses_unique_graph_task_name(self) -> None:
        request = prompt_builder.build_spawn_request(
            DECISION,
            CONTEXT,
            ACCEPTANCE,
            VALIDATION,
            supported_spawn_fields={"agent_type", "model", "reasoning_effort"},
        )

        self.assertEqual(request["task_name"], "auth_session_migration__trace_loader__b6f967fa39")
        self.assertEqual(request["agent_type"], "gpt56_router_terra_explorer")
        self.assertEqual(request["fork_turns"], "none")
        self.assertNotIn("model", request)
        self.assertNotIn("reasoning_effort", request)
        self.assertIn('"routing_mode": "custom-agent"', request["message"])
        self.assertIn('"agent_path": "/root/auth_session_migration__trace_loader__b6f967fa39"', request["message"])

    def test_model_override_inlines_role_contract_and_forces_empty_fork(self) -> None:
        request = prompt_builder.build_spawn_request(
            DECISION,
            CONTEXT,
            ACCEPTANCE,
            VALIDATION,
            supported_spawn_fields={"model", "reasoning_effort"},
        )

        self.assertEqual(request["fork_turns"], "none")
        self.assertEqual(request["model"], "gpt-5.6-terra")
        self.assertEqual(request["reasoning_effort"], "medium")
        self.assertNotIn("agent_type", request)
        self.assertIn('"routing_mode": "model-override"', request["message"])
        self.assertIn("Explore without changing files or external state.", request["message"])

    def test_depth_two_spawn_requires_parent_proof_and_uses_nested_agent_path(self) -> None:
        context = {**CONTEXT, "parent_agent_path": "/root/owner", "parent_depth": 1}
        with self.assertRaisesRegex(ValueError, "requires the parent's delegation capability proof"):
            prompt_builder.build_spawn_request(
                DECISION, context, ACCEPTANCE, VALIDATION,
                supported_spawn_fields={"agent_type"},
            )
        parent = delegation_capability(remaining_depth=1)
        request = prompt_builder.build_spawn_request(
            DECISION, context, ACCEPTANCE, VALIDATION,
            supported_spawn_fields={"agent_type"},
            parent_delegation_capability=parent,
        )
        self.assertIn('"agent_path": "/root/owner/auth_session_migration__trace_loader__b6f967fa39"', request["message"])
        self.assertIn('"depth": 2', request["message"])

    def test_parent_agent_path_must_be_canonical_and_match_depth(self) -> None:
        parent = delegation_capability(remaining_depth=1)
        invalid_contexts = (
            {**CONTEXT, "parent_agent_path": "/root/owner", "parent_depth": 0},
            {**CONTEXT, "parent_agent_path": "/root/a/b", "parent_depth": 1},
            {**CONTEXT, "parent_agent_path": "/root/../spoof", "parent_depth": 1},
            {**CONTEXT, "parent_agent_path": "/root/Owner", "parent_depth": 1},
        )
        for context in invalid_contexts:
            with self.subTest(context=context), self.assertRaisesRegex(ValueError, "canonical"):
                prompt_builder.build_spawn_request(
                    DECISION, context, ACCEPTANCE, VALIDATION,
                    supported_spawn_fields={"agent_type"},
                    parent_delegation_capability=parent,
                )

    def test_fails_closed_when_runtime_cannot_enforce_route(self) -> None:
        with self.assertRaisesRegex(
            prompt_builder.UnsupportedSpawnContract,
            "expected agent_type or both model and reasoning_effort",
        ):
            prompt_builder.build_spawn_request(
                DECISION,
                CONTEXT,
                ACCEPTANCE,
                VALIDATION,
                supported_spawn_fields={"task_name", "message", "fork_turns"},
            )

    def test_read_only_role_inherits_parent_sandbox_without_manual_gate(self) -> None:
        full_access_context = {"objective": "Trace session loading", "current_sandbox": "danger-full-access"}
        request = prompt_builder.build_spawn_request(
            DECISION, full_access_context, ACCEPTANCE, VALIDATION,
            supported_spawn_fields={"agent_type"},
        )
        self.assertEqual(request["agent_type"], "gpt56_router_terra_explorer")
        self.assertIn('"read_only": true', request["message"])
        self.assertIn('"current_sandbox": "danger-full-access"', request["message"])

    def test_prompt_contains_bounded_inputs_and_exact_terminal_json_contract(self) -> None:
        capability = delegation_capability()
        message = prompt_builder.build_spawn_prompt(
            DECISION,
            CONTEXT,
            ACCEPTANCE,
            VALIDATION,
            capability,
            supported_spawn_fields={"agent_type"},
        )

        self.assertIn(json.dumps(CONTEXT, indent=2, sort_keys=True), message)
        self.assertIn(json.dumps(ACCEPTANCE, indent=2, sort_keys=True), message)
        self.assertIn(json.dumps(VALIDATION, indent=2, sort_keys=True), message)
        self.assertIn(json.dumps(capability, indent=2, sort_keys=True), message)
        self.assertIn("Return exactly one JSON object and no Markdown fences.", message)
        for field in prompt_builder.TERMINAL_EVENT_SCHEMA:
            self.assertIn(f'"{field}"', message)
        for event_type in prompt_builder.EVENT_TYPES:
            self.assertIn(event_type, message)
        self.assertIn("Execute it autonomously", message)
        self.assertIn("Do not manufacture preview, permission, or approval gates", message)
        self.assertIn("Do not emit needs_decision for an ordinary semantic choice", message)

    def test_default_leaf_capability_denies_delegation(self) -> None:
        message = prompt_builder.build_spawn_prompt(
            DECISION,
            CONTEXT,
            ACCEPTANCE,
            VALIDATION,
            supported_spawn_fields={"agent_type"},
        )
        self.assertIn('"allowed": false', message)
        self.assertIn('"max_children": 0', message)
        self.assertIn('"schema_version": 1', message)
        self.assertIn("Do not delegate unless the capability explicitly sets allowed=true", message)

    def test_explicit_delegation_capability_is_allowed_for_eligible_role(self) -> None:
        message = prompt_builder.build_spawn_prompt(
            DECISION,
            CONTEXT,
            ACCEPTANCE,
            VALIDATION,
            delegation_capability(),
            supported_spawn_fields={"agent_type"},
        )
        self.assertIn('"allowed": true', message)

    def test_explicit_delegation_capability_is_rejected_for_leaf_role(self) -> None:
        decision = {
            **DECISION,
            "primary": {"agent": "gpt56_router_terra_worker"},
        }
        with self.assertRaisesRegex(ValueError, "selected agent is a leaf"):
            prompt_builder.build_spawn_request(
                decision,
                CONTEXT,
                ACCEPTANCE,
                VALIDATION,
                delegation_capability(),
                supported_spawn_fields={"agent_type"},
            )

    def test_rejects_capability_that_fails_canonical_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            prompt_builder.build_spawn_prompt(
                DECISION,
                CONTEXT,
                ACCEPTANCE,
                VALIDATION,
                {"allowed": True, "remaining_depth": 1},
                supported_spawn_fields={"agent_type"},
            )

    def test_enforces_v02_child_budget_maxima(self) -> None:
        for overrides, message in (
            ({"remaining_depth": 2}, "remaining_depth must be <= 1"),
            ({"max_children": 4}, "max_children must be <= 3"),
            (
                {"max_children": 3, "max_parallel_children": 3},
                "max_parallel_children must be <= 2",
            ),
        ):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, message):
                prompt_builder.build_spawn_prompt(
                    DECISION,
                    CONTEXT,
                    ACCEPTANCE,
                    VALIDATION,
                    delegation_capability(**overrides),
                    supported_spawn_fields={"agent_type"},
                )

    def test_requires_allowed_roles_and_models_to_match(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed_models must exactly match"):
            prompt_builder.build_spawn_prompt(
                DECISION,
                CONTEXT,
                ACCEPTANCE,
                VALIDATION,
                delegation_capability(allowed_models=["gpt-5.6-luna"]),
                supported_spawn_fields={"agent_type"},
            )

    def test_rejects_writer_role_without_writer_permission(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot allow writer roles"):
            prompt_builder.build_spawn_prompt(
                DECISION,
                CONTEXT,
                ACCEPTANCE,
                VALIDATION,
                delegation_capability(
                    allowed_roles=["gpt56_router_terra_worker"],
                    allowed_models=["gpt-5.6-terra"],
                ),
                supported_spawn_fields={"agent_type"},
            )

    def test_child_capability_must_attenuate_parent_authority(self) -> None:
        parent = delegation_capability(
            remaining_depth=2,
            max_children=3,
            max_parallel_children=2,
            allowed_write_scopes=["packages/auth"],
            may_spawn_writers=True,
        )
        child = delegation_capability(
            allowed_write_scopes=["packages/payments"],
        )
        with self.assertRaisesRegex(ValueError, "allowed_write_scopes exceeds parent"):
            prompt_builder.build_spawn_prompt(
                DECISION,
                CONTEXT,
                ACCEPTANCE,
                VALIDATION,
                child,
                supported_spawn_fields={"agent_type"},
                parent_delegation_capability=parent,
            )

        message = prompt_builder.build_spawn_prompt(
            DECISION,
            CONTEXT,
            ACCEPTANCE,
            VALIDATION,
            delegation_capability(
                max_children=1,
                allowed_write_scopes=["packages/auth"],
            ),
            supported_spawn_fields={"agent_type"},
            parent_delegation_capability=parent,
        )
        self.assertIn('"max_children": 1', message)

    def test_cli_enforces_root_capability_attenuation(self) -> None:
        envelope = {
            "decision": DECISION,
            "bounded_context": CONTEXT,
            "acceptance_criteria": ACCEPTANCE,
            "validation_requirements": VALIDATION,
            "delegation_capability": delegation_capability(max_children=3),
            "root_delegation_capability": delegation_capability(max_children=1),
            "supported_spawn_fields": ["agent_type"],
        }
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_spawn_prompt.py"), "--input", "-", "--json"],
            input=json.dumps(envelope),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("max_children exceeds parent", completed.stdout)

    def test_unknown_role_is_rejected_from_canonical_inventory(self) -> None:
        decision = {**DECISION, "primary": {"agent": "invented_agent"}}
        with self.assertRaisesRegex(ValueError, "unknown selected agent"):
            prompt_builder.build_spawn_request(
                decision,
                CONTEXT,
                ACCEPTANCE,
                VALIDATION,
                supported_spawn_fields={"agent_type"},
            )

    def test_task_name_hash_prevents_sanitized_id_collisions(self) -> None:
        left = prompt_builder.make_task_name("task-a", "node-a")
        right = prompt_builder.make_task_name("task_a", "node_a")
        self.assertNotEqual(left, right)
        self.assertRegex(left, r"^task_a__node_a__[0-9a-f]{10}$")

    def test_terminal_template_matches_canonical_child_event_validator(self) -> None:
        from router_contract import validate_child_event

        template = prompt_builder.terminal_event_template(
            DECISION,
            DECISION["task_id"],
            DECISION["node_id"],
            "/root/example",
        )
        template["event_type"] = "complete"
        template["summary"] = "Traced session loading."
        self.assertEqual(validate_child_event(template), template)

    def test_file_and_stdin_envelope_cli_emit_stable_spawn_output(self) -> None:
        envelope = {
            "decision": DECISION,
            "bounded_context": CONTEXT,
            "acceptance_criteria": ACCEPTANCE,
            "validation_requirements": VALIDATION,
            "delegation_capability": None,
            "supported_spawn_fields": ["model", "reasoning_effort"],
        }
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_spawn_prompt.py"), "--input", "-", "--json"],
            input=json.dumps(envelope),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual(output["routing_mode"], "model-override")
        self.assertEqual(output["task_name"], output["spawn_request"]["task_name"])
        self.assertEqual(output["prompt"], output["spawn_request"]["message"])
        self.assertEqual(output["spawn_request"]["fork_turns"], "none")

        with tempfile.TemporaryDirectory() as temp_dir:
            envelope_path = Path(temp_dir) / "spawn-envelope.json"
            envelope_path.write_text(json.dumps(envelope))
            from_file = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "build_spawn_prompt.py"),
                    "--input",
                    str(envelope_path),
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(from_file.returncode, 0, from_file.stderr)
        self.assertEqual(json.loads(from_file.stdout), output)


if __name__ == "__main__":
    unittest.main()
