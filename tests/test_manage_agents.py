from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANAGER = ROOT / "plugins/gpt-5-6-model-router/skills/setup-gpt56-model-router/scripts/manage_agents.py"
EXPECTED_COUNT = 10
LEGACY_LUNA = '''# Managed by gpt-5-6-model-router; agent=gpt56_router_luna_worker; schema=2
# Router capability: may_delegate=false
name = "gpt56_router_luna_worker"
description = "Use for clear, repeatable, low-risk work with objective acceptance criteria."
model = "gpt-5.6-luna"
model_reasoning_effort = "low"
developer_instructions = """
Complete only narrow, explicit, repeatable work.
Preserve the requested scope and avoid architectural decisions.
Run objective validation and report exact evidence.
Operate autonomously within the assignment: make the safest reversible evidence-backed assumption and continue. Do not ask the human for routine clarification or router-specific approval.
Return ambiguity as discovered work only when resolving it would materially exceed the assigned scope or role capability.
Leaf behavior: do not delegate or spawn subagents, even if a delegation capability is available.
End with exactly one JSON object and no Markdown fences. Follow the parent-supplied child-event schema exactly, including schema_version, event_type, task_id, node_id, agent_path, summary, outcomes, discovered_work, validation, blockers, questions, risks, write_scopes, and review. Use only an allowed terminal event_type and never claim completion of the parent task.
"""
'''
SCHEMA3_LUNA = '''# Managed by gpt-5-6-model-router; agent=gpt56_router_luna_worker; schema=3
name = "gpt56_router_luna_worker"
description = "Clear, repeatable, low-risk work with objective acceptance criteria."
model = "gpt-5.6-luna"
model_reasoning_effort = "low"
developer_instructions = """
Complete the narrow assignment, preserve scope, and avoid architectural decisions.
Do not delegate or spawn subagents. Run the requested checks.
Return a concise result covering outcome, changed files, validation, and blockers.
"""
'''
SCHEMA4_LUNA = '''# Managed by gpt-5-6-model-router; agent=gpt56_router_luna_worker; schema=4
name = "gpt56_router_luna_worker"
description = "Clear, repeatable, low-risk work with objective acceptance criteria."
model = "gpt-5.6-luna"
model_reasoning_effort = "low"
developer_instructions = """
Complete the narrow assignment, preserve scope, and avoid architectural decisions.
Delegation contract: without the exact line `Delegation grant: one-level`, remain a leaf and do not delegate. With that grant, you may create useful bounded descendants; give every descendant the exact line `Delegation grant: none`, and they cannot delegate further. Run the requested checks.
Return a concise result covering outcome, changed files, validation, and blockers.
"""
'''


class ManageAgentsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.environment = {**os.environ, "HOME": str(self.home)}
        self.destination = self.home / ".codex" / "agents"

    def tearDown(self):
        self.temporary.cleanup()

    def run_manager(self, command, *args):
        completed = subprocess.run([sys.executable, str(MANAGER), command, *args, "--json"], env=self.environment, text=True, capture_output=True)
        return completed, json.loads(completed.stdout)

    def test_clean_install_check_and_uninstall(self):
        installed, result = self.run_manager("install")
        self.assertEqual(installed.returncode, 0)
        self.assertEqual(len(result["changed"]), EXPECTED_COUNT)
        checked, result = self.run_manager("check")
        self.assertEqual(checked.returncode, 0)
        self.assertEqual(len(result["unchanged"]), EXPECTED_COUNT)
        removed, result = self.run_manager("uninstall")
        self.assertEqual(removed.returncode, 0)
        self.assertEqual(len(result["changed"]), EXPECTED_COUNT)

    def test_byte_identical_schema2_auto_upgrades_with_backup(self):
        self.destination.mkdir(parents=True)
        target = self.destination / "gpt56-router-luna-worker.toml"
        target.write_text(LEGACY_LUNA)
        installed, result = self.run_manager("install")
        self.assertEqual(installed.returncode, 0, result)
        self.assertEqual(len(result["backed_up"]), 1)
        self.assertEqual(Path(result["backed_up"][0]).read_text(), LEGACY_LUNA)
        self.assertIn("schema=5", target.read_text())

    def test_byte_identical_schema3_auto_upgrades_with_backup(self):
        self.destination.mkdir(parents=True)
        target = self.destination / "gpt56-router-luna-worker.toml"
        target.write_text(SCHEMA3_LUNA)
        installed, result = self.run_manager("install")
        self.assertEqual(installed.returncode, 0, result)
        self.assertEqual(Path(result["backed_up"][0]).read_text(), SCHEMA3_LUNA)
        self.assertIn("schema=5", target.read_text())

    def test_byte_identical_schema4_auto_upgrades_with_backup(self):
        self.destination.mkdir(parents=True)
        target = self.destination / "gpt56-router-luna-worker.toml"
        target.write_text(SCHEMA4_LUNA)
        installed, result = self.run_manager("install")
        self.assertEqual(installed.returncode, 0, result)
        self.assertEqual(Path(result["backed_up"][0]).read_text(), SCHEMA4_LUNA)
        self.assertIn("schema=5", target.read_text())

    def test_modified_schema2_refuses_without_force(self):
        self.destination.mkdir(parents=True)
        target = self.destination / "gpt56-router-luna-worker.toml"
        target.write_text(LEGACY_LUNA + "# user edit\n")
        completed, result = self.run_manager("install")
        self.assertEqual(completed.returncode, 1)
        self.assertIn(target.name, result["divergent"])
        self.assertIn("user edit", target.read_text())

    def test_force_backs_up_and_replaces_unknown_file(self):
        self.destination.mkdir(parents=True)
        target = self.destination / "gpt56-router-luna-worker.toml"
        target.write_text("user-owned\n")
        completed, result = self.run_manager("install", "--force")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(Path(result["backed_up"][0]).read_text(), "user-owned\n")
        self.assertIn("schema=5", target.read_text())

    def test_unrelated_agent_file_is_preserved(self):
        self.destination.mkdir(parents=True)
        unrelated = self.destination / "my-agent.toml"
        unrelated.write_text("name='mine'\n")
        self.run_manager("install")
        self.run_manager("uninstall")
        self.assertEqual(unrelated.read_text(), "name='mine'\n")


if __name__ == "__main__":
    unittest.main()
