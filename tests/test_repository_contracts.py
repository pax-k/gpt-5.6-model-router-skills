from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "gpt-5-6-model-router"
AGENT_TEMPLATE_DIR = PLUGIN / "skills" / "setup-gpt56-model-router" / "assets" / "agents"
REFERENCES = PLUGIN / "skills" / "route-gpt56-task" / "references"
MARKER = re.compile(r"^# Managed by gpt-5-6-model-router; agent=([a-z0-9_]+); schema=2$")


class RepositoryContractTests(unittest.TestCase):
    def test_repository_validator(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_repo.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_manifest_uses_v021_fresh_codex_cachebuster(self) -> None:
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        self.assertRegex(manifest["version"], r"^0\.2\.1\+codex\.20260719\d{6}$")
        self.assertEqual(manifest["skills"], "./skills/")

    def test_router_documents_the_envelope_reentry_and_runtime_proof_boundaries(self) -> None:
        skill = (PLUGIN / "skills" / "route-gpt56-task" / "SKILL.md").read_text()
        for text in (
            "autonomous execution within the requested scope",
            "re-enter",
            "delegation capability",
            "route_task.py\" decide",
            "orchestrate.py",
            "build_spawn_prompt.py",
            "inspect_spawn.py",
            "fork_turns: \"none\"",
            "live route proof is unavailable",
        ):
            with self.subTest(text=text):
                self.assertIn(text, skill)

    def test_every_reference_is_marked_implemented_or_resolved(self) -> None:
        expected = {
            "model-effort-research.md": "Status: Implemented",
            "routing-policy.md": "Status: Implemented",
            "protocol-schemas.md": "Status: Implemented",
            "orchestration-workflows.md": "Status: Implemented",
            "open-design-decisions.md": "Status: Resolved and implemented",
            "migration-v0.2.md": "Status: Implemented",
            "runtime-evidence.md": "Status: Implemented",
        }
        for filename, status in expected.items():
            with self.subTest(filename=filename):
                text = (REFERENCES / filename).read_text()
                self.assertIn(status, text)

    def test_setup_templates_are_ten_unique_schema2_role_contracts(self) -> None:
        templates = []
        for path in sorted(AGENT_TEMPLATE_DIR.glob("gpt56-router-*.toml")):
            raw = path.read_text()
            template = tomllib.loads(raw)
            templates.append(template)
            marker = MARKER.fullmatch(raw.splitlines()[0])
            self.assertIsNotNone(marker, path.name)
            self.assertEqual(marker.group(1), template["name"])
            self.assertTrue(template["name"].startswith("gpt56_router_"))
            self.assertIn(template["model"], {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"})
            self.assertIn(template["model_reasoning_effort"], {"low", "medium", "high", "xhigh", "max"})
            self.assertTrue(template["description"])
            self.assertTrue(template["developer_instructions"])
            self.assertIn("autonom", template["developer_instructions"].lower())
            self.assertIn("router-specific approval", template["developer_instructions"])
            self.assertNotIn('"event":"child_complete"', template["developer_instructions"])
            for field in ("event_type", "task_id", "node_id", "agent_path", "discovered_work", "write_scopes", "review"):
                self.assertIn(field, template["developer_instructions"])

        self.assertEqual(len(templates), 10)
        self.assertEqual(len({template["name"] for template in templates}), 10)


if __name__ == "__main__":
    unittest.main()
