from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INSPECTOR = (
    ROOT
    / "plugins/gpt-5-6-model-router/skills/setup-gpt56-model-router/scripts/inspect_plugin_discovery.py"
)


def load_inspector():
    spec = importlib.util.spec_from_file_location("inspect_plugin_discovery", INSPECTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load plugin discovery inspector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plugin_detail(*, enabled: bool = True, skills: tuple[str, ...] = ("route-gpt56-task", "setup-gpt56-model-router")) -> dict:
    return {
        "marketplaceName": "gpt-5-6-model-router-skills",
        "summary": {
            "id": "gpt-5-6-model-router@gpt-5-6-model-router-skills",
            "installed": True,
            "enabled": enabled,
            "localVersion": "0.3.0+codex.20260721075542",
        },
        "skills": [
            {"name": f"gpt-5-6-model-router:{name}", "enabled": True}
            for name in skills
        ],
    }


class InspectPluginDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inspector = load_inspector()

    def test_accepts_enabled_explicit_skills_from_plugin_read(self) -> None:
        result = self.inspector.evaluate_plugin(
            plugin_detail(),
            expected_plugin_id="gpt-5-6-model-router@gpt-5-6-model-router-skills",
            expected_version="0.3.0+codex.20260721075542",
            expected_skills=("route-gpt56-task", "setup-gpt56-model-router"),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["failure_reasons"], [])
        self.assertEqual(result["skills"], ["route-gpt56-task", "setup-gpt56-model-router"])

    def test_rejects_missing_explicit_skill(self) -> None:
        result = self.inspector.evaluate_plugin(
            plugin_detail(skills=("route-gpt56-task",)),
            expected_plugin_id="gpt-5-6-model-router@gpt-5-6-model-router-skills",
            expected_version="0.3.0+codex.20260721075542",
            expected_skills=("route-gpt56-task", "setup-gpt56-model-router"),
        )

        self.assertFalse(result["ok"])
        self.assertIn("expected explicit skill is unavailable: setup-gpt56-model-router", result["failure_reasons"])

    def test_rejects_disabled_plugin(self) -> None:
        result = self.inspector.evaluate_plugin(
            plugin_detail(enabled=False),
            expected_plugin_id="gpt-5-6-model-router@gpt-5-6-model-router-skills",
            expected_version="0.3.0+codex.20260721075542",
            expected_skills=("route-gpt56-task", "setup-gpt56-model-router"),
        )

        self.assertFalse(result["ok"])
        self.assertIn("plugin is not enabled", result["failure_reasons"])


if __name__ == "__main__":
    unittest.main()
