from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins/gpt-5-6-model-router"
try:
    import tomllib
except ModuleNotFoundError:
    sys.path.insert(0, str(PLUGIN / "vendor"))
    import tomli as tomllib


class RepositoryContractTests(unittest.TestCase):
    def test_repository_validator(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_repo.py")], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_manifest_is_v041_and_hook_bearing(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
        self.assertRegex(manifest["version"], r"^0\.4\.1\+codex\.[A-Za-z0-9.-]+$")
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())
        self.assertEqual(
            set(hooks["hooks"]),
            {"UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop", "Stop"},
        )

    def test_removed_orchestration_surfaces_are_absent(self):
        route = PLUGIN / "skills/route-gpt56-task"
        self.assertFalse((route / "scripts/orchestrate.py").exists())
        self.assertEqual(
            {path.name for path in (route / "schemas").glob("*.json")},
            {"task-profile.schema.json", "route-recommendation.schema.json", "route-intent.schema.json"},
        )
        self.assertTrue((route / "scripts/route_guard.py").is_file())
        self.assertFalse((route / "scripts/build_spawn_prompt.py").exists())
        for name in ("protocol-schemas.md", "orchestration-workflows.md", "open-design-decisions.md", "migration-v0.2.md"):
            self.assertFalse((route / "references" / name).exists())

    def test_eight_schema5_bounded_roles(self):
        paths = sorted((PLUGIN / "skills/setup-gpt56-model-router/assets/agents").glob("*.toml"))
        self.assertEqual(len(paths), 8)
        for path in paths:
            text = path.read_text()
            role = tomllib.loads(text)
            self.assertIn("schema=5", text.splitlines()[0])
            self.assertIn("remain a leaf", role["developer_instructions"])
            self.assertIn("Do not delegate or spawn subagents", role["developer_instructions"])
            self.assertNotIn("one-level", role["developer_instructions"])
            self.assertNotIn("event_type", role["developer_instructions"])

    def test_migration_and_canary_are_documented(self):
        route = PLUGIN / "skills/route-gpt56-task"
        self.assertTrue((route / "references/migration-v0.4.md").is_file())
        evidence = (route / "references/runtime-evidence.md").read_text()
        self.assertIn("--expected-fork-turns none", evidence)
        self.assertIn("open `/hooks`", evidence.lower())

    def test_governed_contract(self):
        skill = (PLUGIN / "skills/route-gpt56-task/SKILL.md").read_text()
        for expected in (
            "every root `Agent` spawn on every turn",
            "critical execution uses at least Sol/medium",
            "manifest SHA-256",
            "trusted hooks are enforceable guardrails",
            "Root rationale alone cannot change",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected.lower(), skill.lower())
        self.assertNotIn("ordinary noncritical route choices remain advisory", skill.lower())

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
        self.assertEqual(len(roles), 8)
        self.assertTrue(all('model_reasoning_effort = "ultra"' not in path.read_text() for path in roles))


if __name__ == "__main__":
    unittest.main()
