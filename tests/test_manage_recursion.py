from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib import util
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
MANAGER = ROOT / "plugins/gpt-5-6-model-router/skills/setup-gpt56-model-router/scripts/manage_recursion.py"


SPEC = util.spec_from_file_location("manage_recursion_under_test", MANAGER)
assert SPEC is not None and SPEC.loader is not None
MANAGE_RECURSION = util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MANAGE_RECURSION
SPEC.loader.exec_module(MANAGE_RECURSION)


class ManageRecursionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.environment = os.environ.copy()
        self.environment["HOME"] = str(self.home)
        self.environment.pop("CODEX_HOME", None)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def config(self) -> Path:
        return self.home / ".codex" / "config.toml"

    @property
    def state(self) -> Path:
        return self.home / ".codex" / ".gpt56-router-recursion-state.json"

    def run_manager(self, command: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        completed = subprocess.run(
            [sys.executable, str(MANAGER), command, "--json"],
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )
        return completed, json.loads(completed.stdout)

    def test_enable_check_disable_restores_full_config(self) -> None:
        original = "# user comment\n[agents]\nmax_threads = 8\nmax_depth = 1 # keep\n[features]\nfoo = true\n"
        self.config.parent.mkdir(parents=True)
        self.config.write_text(original)

        enabled, enabled_result = self.run_manager("enable")
        self.assertEqual(enabled.returncode, 0)
        self.assertEqual(enabled_result["changed"], ["agents.max_depth=2"])
        managed = self.config.read_text()
        self.assertIn("max_threads = 8", managed)
        self.assertIn("max_depth = 2 # keep", managed)
        self.assertIn("# Managed by gpt-5-6-model-router; recursion; schema=2", managed)
        self.assertEqual(Path(enabled_result["backed_up"][0]).read_text(), original)

        checked, _ = self.run_manager("check")
        self.assertEqual(checked.returncode, 0)
        repeated, repeated_result = self.run_manager("enable")
        self.assertEqual(repeated.returncode, 0)
        self.assertEqual(repeated_result["changed"], [])

        disabled, _ = self.run_manager("disable")
        self.assertEqual(disabled.returncode, 0)
        self.assertEqual(self.config.read_text(), original)

    def test_enable_missing_config_and_disable_removes_only_managed_config(self) -> None:
        enabled, _ = self.run_manager("enable")
        self.assertEqual(enabled.returncode, 0)
        self.assertIn("[agents]", self.config.read_text())
        disabled, _ = self.run_manager("disable")
        self.assertEqual(disabled.returncode, 0)
        self.assertFalse(self.config.exists())

    def test_disable_refuses_after_config_edit(self) -> None:
        self.config.parent.mkdir(parents=True)
        self.config.write_text("[agents]\nmax_threads = 8\n")
        self.run_manager("enable")
        self.config.write_text(self.config.read_text() + "# user edit\n")

        checked, check_result = self.run_manager("check")
        self.assertEqual(checked.returncode, 0)
        self.assertTrue(any("rollback remains guarded" in item for item in check_result["unchanged"]))
        repeated, repeated_result = self.run_manager("enable")
        self.assertEqual(repeated.returncode, 0)
        self.assertTrue(any("rollback remains guarded" in item for item in repeated_result["unchanged"]))

        disabled, result = self.run_manager("disable")
        self.assertEqual(disabled.returncode, 1)
        self.assertIn("refusing ambiguous rollback", result["errors"][0])
        self.assertIn("# user edit", self.config.read_text())

    def test_enable_refuses_unsupported_inline_agents_table(self) -> None:
        self.config.parent.mkdir(parents=True)
        self.config.write_text("agents = { max_threads = 8, max_depth = 1 }\n")
        enabled, result = self.run_manager("enable")
        self.assertEqual(enabled.returncode, 1)
        self.assertIn("unsupported inline", result["errors"][0])

    def test_enable_with_existing_agent_subtables_inserts_parent_and_preserves_roles(self) -> None:
        original = '[agents.reviewer]\nconfig_file = "./agents/reviewer.toml"\n\n[features]\nmulti_agent = true\n'
        self.config.parent.mkdir(parents=True)
        self.config.write_text(original)

        enabled, enabled_result = self.run_manager("enable")
        self.assertEqual(enabled.returncode, 0, enabled_result)
        managed = self.config.read_text()
        self.assertIn("[agents]\n", managed)
        self.assertIn("max_depth = 2", managed)
        self.assertIn('[agents.reviewer]\nconfig_file = "./agents/reviewer.toml"', managed)
        self.assertTrue(json.loads(self.state.read_text()))

        disabled, disabled_result = self.run_manager("disable")
        self.assertEqual(disabled.returncode, 0, disabled_result)
        self.assertEqual(self.config.read_text(), original)

    def test_disable_rolls_config_back_to_managed_state_when_state_removal_fails(self) -> None:
        original = "[agents]\nmax_depth = 1\n"
        self.config.parent.mkdir(parents=True)
        self.config.write_text(original)
        enabled, _ = self.run_manager("enable")
        self.assertEqual(enabled.returncode, 0)
        managed = self.config.read_bytes()
        real_unlink = Path.unlink

        def fail_state_unlink(path: Path, *args: object, **kwargs: object) -> None:
            if path == self.state:
                raise OSError("injected state unlink failure")
            real_unlink(path, *args, **kwargs)

        with (
            mock.patch.object(MANAGE_RECURSION, "config_path", return_value=self.config),
            mock.patch.object(MANAGE_RECURSION, "state_path", return_value=self.state),
            mock.patch.object(Path, "unlink", autospec=True, side_effect=fail_state_unlink),
        ):
            result = MANAGE_RECURSION.disable()

        self.assertFalse(result.ok)
        self.assertIn("rolled back", result.errors[0])
        self.assertEqual(self.config.read_bytes(), managed)
        self.assertTrue(self.state.is_file())

    def test_oserror_is_rendered_as_json_error(self) -> None:
        self.config.mkdir(parents=True)

        completed = subprocess.run(
            [sys.executable, str(MANAGER), "check", "--json"],
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertIn("check failed", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
