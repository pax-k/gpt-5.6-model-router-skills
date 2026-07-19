from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INSPECTOR = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts/inspect_spawn.py"


def write_rollout(
    root: Path,
    *,
    thread_id: str,
    agent_path: str,
    timestamp: str,
    agent_role: str | None,
    model: str = "gpt-5.6-terra",
    effort: str = "medium",
    depth: int = 1,
    sandbox: str = "read-only",
    parent_thread_id: str = "parent-thread",
    spawn_parent_thread_id: str | None = None,
) -> Path:
    rollout = root / "nested" / f"rollout-{thread_id}.jsonl"
    rollout.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "timestamp": timestamp,
            "type": "session_meta",
            "payload": {
                "id": thread_id,
                "timestamp": timestamp,
                "parent_thread_id": parent_thread_id,
                "source": {
                    "subagent": {
                        "thread_spawn": {
                            "parent_thread_id": spawn_parent_thread_id or parent_thread_id,
                            "depth": depth,
                            "agent_path": agent_path,
                            "agent_role": agent_role,
                        }
                    }
                },
            },
        },
        {
            "timestamp": timestamp,
            "type": "turn_context",
            "payload": {
                "model": model,
                "effort": effort,
                "sandbox_policy": {"type": sandbox},
            },
        },
    ]
    rollout.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return rollout


def inspect(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(INSPECTOR),
            "--agent-path",
            "/root/graph_task__trace_auth",
            "--not-before",
            "2026-07-19T10:00:00Z",
            "--expected-agent",
            "gpt56_router_terra_explorer",
            "--routing-mode",
            "custom-agent",
            "--sessions-root",
            str(root),
            "--json",
            *extra,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


class InspectSpawnTests(unittest.TestCase):
    def test_recovers_child_thread_from_agent_path_and_verifies_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rollout = write_rollout(
                root,
                thread_id="fresh-child",
                agent_path="/root/graph_task__trace_auth",
                timestamp="2026-07-19T10:48:25Z",
                agent_role="gpt56_router_terra_explorer",
            )
            completed = inspect(root, "--parent-thread-id", "parent-thread")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rollout_path"], str(rollout))
        self.assertEqual(result["thread_id"], "fresh-child")
        self.assertEqual(result["parent_thread_id"], "parent-thread")
        self.assertEqual(result["agent_path"], "/root/graph_task__trace_auth")
        self.assertEqual(result["agent_role"], "gpt56_router_terra_explorer")
        self.assertEqual(result["model"], result["expected_model"])
        self.assertEqual(result["effort"], result["expected_effort"])
        self.assertEqual(result["depth"], result["expected_depth"])
        self.assertEqual(result["sandbox"], "read-only")
        self.assertIsNone(result["expected_sandbox"])
        self.assertEqual(result["failure_reasons"], [])

    def test_excludes_stale_rollout_and_selects_fresh_match_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_rollout(
                root / "stale",
                thread_id="stale-child",
                agent_path="/root/graph_task__trace_auth",
                timestamp="2026-07-18T10:48:25Z",
                agent_role="gpt56_router_terra_explorer",
            )
            write_rollout(
                root / "fresh",
                thread_id="fresh-child",
                agent_path="/root/graph_task__trace_auth",
                timestamp="2026-07-19T10:48:25Z",
                agent_role="gpt56_router_terra_explorer",
            )
            completed = inspect(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["thread_id"], "fresh-child")

    def test_optional_thread_id_cross_checks_recovered_child(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_rollout(
                root,
                thread_id="fresh-child",
                agent_path="/root/graph_task__trace_auth",
                timestamp="2026-07-19T10:48:25Z",
                agent_role="gpt56_router_terra_explorer",
            )
            completed = inspect(root, "--thread-id", "fresh-child")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["thread_id"], "fresh-child")

    def test_model_override_requires_null_role_and_pinned_model_effort(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_rollout(
                root,
                thread_id="override-child",
                agent_path="/root/graph_task__trace_auth",
                timestamp="2026-07-19T10:48:25Z",
                agent_role=None,
                sandbox="workspace-write",
            )
            completed = inspect(root, "--routing-mode", "model-override")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["agent_role"])
        self.assertIsNone(result["expected_sandbox"])

    def test_broader_inherited_sandbox_is_observational_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_rollout(
                root,
                thread_id="full-access-child",
                agent_path="/root/graph_task__trace_auth",
                timestamp="2026-07-19T10:48:25Z",
                agent_role="gpt56_router_terra_explorer",
                sandbox="danger-full-access",
            )
            completed = inspect(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(result["sandbox"], "danger-full-access")
        self.assertIsNone(result["expected_sandbox"])
        self.assertEqual(result["failure_reasons"], [])

    def test_fails_on_stale_only_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_rollout(
                root,
                thread_id="stale-child",
                agent_path="/root/graph_task__trace_auth",
                timestamp="2026-07-18T10:48:25Z",
                agent_role="gpt56_router_terra_explorer",
            )
            completed = inspect(root)

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(
            json.loads(completed.stdout)["failure_reasons"],
            ["fresh rollout not found for agent path"],
        )

    def test_ignores_non_subagent_session_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "root-rollout.jsonl").write_text(
                json.dumps(
                    {
                        "timestamp": "2026-07-19T10:30:00Z",
                        "type": "session_meta",
                        "payload": {"id": "root-thread", "source": "cli"},
                    }
                )
                + "\n"
            )
            write_rollout(
                root,
                thread_id="fresh-child",
                agent_path="/root/graph_task__trace_auth",
                timestamp="2026-07-19T10:48:25Z",
                agent_role="gpt56_router_terra_explorer",
            )
            completed = inspect(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["thread_id"], "fresh-child")

    def test_fails_on_role_model_effort_depth_sandbox_and_parent_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_rollout(
                root,
                thread_id="bad-child",
                agent_path="/root/graph_task__trace_auth",
                timestamp="2026-07-19T10:48:25Z",
                agent_role="gpt56_router_terra_worker",
                model="gpt-5.6-sol",
                effort="high",
                depth=2,
                sandbox="workspace-write",
                spawn_parent_thread_id="different-parent",
            )
            completed = inspect(
                root,
                "--parent-thread-id", "expected-parent",
                "--expected-sandbox", "read-only",
            )

        self.assertEqual(completed.returncode, 1)
        reasons = json.loads(completed.stdout)["failure_reasons"]
        self.assertIn("agent role did not match expected agent", reasons)
        self.assertIn("model did not match expected pinned model", reasons)
        self.assertIn("reasoning effort did not match expected pinned effort", reasons)
        self.assertIn("spawn depth did not match expected depth", reasons)
        self.assertIn("sandbox did not match expected sandbox", reasons)
        self.assertIn("parent provenance was missing or inconsistent", reasons)
        self.assertIn("parent thread ID did not match expected parent", reasons)


if __name__ == "__main__":
    unittest.main()
