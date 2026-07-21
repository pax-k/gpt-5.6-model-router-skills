from __future__ import annotations
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts"
sys.path.insert(0, str(SCRIPTS))
import build_spawn_prompt  # noqa: E402
import route_task  # noqa: E402


def selected(agent="gpt56_router_terra_worker"):
    role = route_task.load_role_inventory()[agent]
    return {"agent": role.name, "model": role.model, "reasoning_effort": role.reasoning_effort, "read_only": role.read_only}


def handoff():
    return {
        "selected_route": selected(), "task_name": "motif-1804-implementation",
        "objective": "Implement MOTIF-1804 using the canonical issue and repository contracts.",
        "references": ["Jira MOTIF-1804", "src/session/service.ts"], "owned_paths": ["src/session/"],
        "constraints": ["Preserve the public session API"], "verification": ["npm test -- tests/session/service.test.ts"],
        "supported_spawn_fields": ["agent_type", "model", "reasoning_effort"],
    }


class SpawnPromptTests(unittest.TestCase):
    def test_defaults_to_empty_fork_and_leaf(self):
        request = build_spawn_prompt.build_spawn_request(handoff())
        self.assertEqual(request["fork_turns"], "none")
        self.assertEqual(request["agent_type"], "gpt56_router_terra_worker")
        self.assertIn("Delegation grant: none", request["message"])
        self.assertIn("Remain a leaf", request["message"])

    def test_custom_forks_and_one_level_grant(self):
        for fork in (3, "2"):
            value = handoff(); value.update({"fork_turns": fork, "delegation_grant": "one-level"})
            request = build_spawn_prompt.build_spawn_request(value)
            self.assertEqual(request["fork_turns"], str(fork))
            self.assertIn("Delegation grant: one-level", request["message"])
            self.assertIn("every descendant must receive Delegation grant: none", request["message"])

    def test_rejects_full_history_for_both_routing_modes(self):
        for fields in (["agent_type"], ["model", "reasoning_effort"]):
            value = handoff(); value.update({"fork_turns": "all", "supported_spawn_fields": fields})
            with self.subTest(fields=fields), self.assertRaisesRegex(
                build_spawn_prompt.UnsupportedSpawnContract,
                'routed spawns cannot use fork_turns "all"',
            ):
                build_spawn_prompt.build_spawn_request(value)

    def test_any_bundled_route_can_be_a_root_override(self):
        value = handoff(); value["selected_route"] = selected("gpt56_router_sol_specialist_max")
        request = build_spawn_prompt.build_spawn_request(value)
        self.assertEqual(request["agent_type"], "gpt56_router_sol_specialist_max")

    def test_model_override_includes_role(self):
        value = handoff(); value["supported_spawn_fields"] = ["model", "reasoning_effort"]
        request = build_spawn_prompt.build_spawn_request(value)
        self.assertEqual((request["model"], request["reasoning_effort"]), ("gpt-5.6-terra", "medium"))
        self.assertIn("Role:", request["message"])
        self.assertLessEqual(len(request["message"]), 8000)

    def test_rejects_pasted_context_and_oversize_messages(self):
        for field in build_spawn_prompt.FORBIDDEN_LABELS:
            value = handoff(); value[field] = ["pasted"]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "forbidden"):
                build_spawn_prompt.build_spawn_request(value)
        value = handoff(); value["constraints"] = ["x" * 6000]
        with self.assertRaisesRegex(ValueError, "6000"): build_spawn_prompt.build_spawn_request(value)

    def test_rejects_invalid_fork_grant_and_route_fields(self):
        for fork in (0, -1, "recent"):
            value = handoff(); value["fork_turns"] = fork
            with self.assertRaisesRegex(ValueError, "fork_turns"): build_spawn_prompt.build_spawn_request(value)
        value = handoff(); value["delegation_grant"] = "recursive"
        with self.assertRaisesRegex(ValueError, "delegation_grant"): build_spawn_prompt.build_spawn_request(value)
        value = handoff(); value["supported_spawn_fields"] = ["message"]
        with self.assertRaises(build_spawn_prompt.UnsupportedSpawnContract): build_spawn_prompt.build_spawn_request(value)


if __name__ == "__main__": unittest.main()
