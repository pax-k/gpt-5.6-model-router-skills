from __future__ import annotations

import json
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins/gpt-5-6-model-router"


class RepositoryContractTests(unittest.TestCase):
    def test_repository_validator(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_repo.py")], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_manifest_is_v030(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
        self.assertRegex(manifest["version"], r"^0\.3\.0\+codex\.20260721\d{6}$")

    def test_removed_orchestration_surfaces_are_absent(self):
        route = PLUGIN / "skills/route-gpt56-task"
        self.assertFalse((route / "scripts/orchestrate.py").exists())
        self.assertEqual({path.name for path in (route / "schemas").glob("*.json")}, {"task-profile.schema.json", "route-recommendation.schema.json"})
        for name in ("protocol-schemas.md", "orchestration-workflows.md", "open-design-decisions.md", "migration-v0.2.md"):
            self.assertFalse((route / "references" / name).exists())

    def test_ten_schema4_bounded_roles(self):
        paths = sorted((PLUGIN / "skills/setup-gpt56-model-router/assets/agents").glob("*.toml"))
        self.assertEqual(len(paths), 10)
        for path in paths:
            text = path.read_text()
            role = tomllib.loads(text)
            self.assertIn("schema=4", text.splitlines()[0])
            self.assertIn("Delegation grant: one-level", role["developer_instructions"])
            self.assertIn("Delegation grant: none", role["developer_instructions"])
            self.assertNotIn("event_type", role["developer_instructions"])

    def test_migration_and_canary_are_documented(self):
        route = PLUGIN / "skills/route-gpt56-task"
        self.assertTrue((route / "references/migration-v0.3.md").is_file())
        evidence = (route / "references/runtime-evidence.md").read_text()
        self.assertIn('fork_turns: "none"', evidence)
        self.assertIn("install acceptance", evidence)

    def test_autonomy_first_contract(self):
        skill = (PLUGIN / "skills/route-gpt56-task/SKILL.md").read_text()
        for expected in (
            "best expected value",
            "may override every",
            "never blocks the task",
            "Delegation grant: one-level",
            "no fixed count",
            "optional helpers",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected.lower(), skill.lower())
        self.assertNotIn("must use", skill.lower())

    def test_unified_setup_replaces_recursion_manager(self):
        setup = PLUGIN / "skills/setup-gpt56-model-router/scripts"
        self.assertTrue((setup / "setup_router.py").is_file())
        self.assertTrue((setup / "manage_depth.py").is_file())
        self.assertFalse((setup / "manage_recursion.py").exists())

    def test_ultra_remains_out_of_scope(self):
        route = PLUGIN / "skills/route-gpt56-task"
        for path in (route / "schemas").glob("*.json"):
            self.assertNotIn("ultra", path.read_text())
        roles = list((PLUGIN / "skills/setup-gpt56-model-router/assets/agents").glob("*.toml"))
        self.assertEqual(len(roles), 10)
        self.assertTrue(all('model_reasoning_effort = "ultra"' not in path.read_text() for path in roles))


if __name__ == "__main__":
    unittest.main()
