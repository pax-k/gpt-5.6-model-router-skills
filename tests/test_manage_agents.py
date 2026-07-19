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


class ManageAgentsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.environment = os.environ.copy()
        self.environment["HOME"] = str(self.home)
        self.environment.pop("CODEX_HOME", None)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def destination(self) -> Path:
        return self.home / ".codex" / "agents"

    def run_manager(self, command: str, *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        completed = subprocess.run(
            [sys.executable, str(MANAGER), command, *arguments, "--json"],
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )
        return completed, json.loads(completed.stdout)

    def test_clean_install_check_and_idempotent_reinstall(self) -> None:
        missing, missing_result = self.run_manager("check")
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(len(missing_result["missing"]), EXPECTED_COUNT)

        installed, installed_result = self.run_manager("install")
        self.assertEqual(installed.returncode, 0)
        self.assertEqual(len(installed_result["changed"]), EXPECTED_COUNT)
        self.assertEqual(installed_result["unchanged"], [])

        checked, checked_result = self.run_manager("check")
        self.assertEqual(checked.returncode, 0)
        self.assertEqual(len(checked_result["unchanged"]), EXPECTED_COUNT)

        repeated, repeated_result = self.run_manager("install")
        self.assertEqual(repeated.returncode, 0)
        self.assertEqual(repeated_result["changed"], [])
        self.assertEqual(len(repeated_result["unchanged"]), EXPECTED_COUNT)

    def test_divergent_file_refuses_all_mutation(self) -> None:
        self.destination.mkdir(parents=True)
        conflict = self.destination / "gpt56-router-luna-worker.toml"
        conflict.write_text("user-owned\n")

        completed, result = self.run_manager("install")
        self.assertEqual(completed.returncode, 1)
        self.assertIn(conflict.name, result["divergent"])
        self.assertEqual(conflict.read_text(), "user-owned\n")
        self.assertEqual(list(self.destination.glob("gpt56-router-*.toml")), [conflict])

    def test_force_backs_up_before_replacement(self) -> None:
        self.destination.mkdir(parents=True)
        conflict = self.destination / "gpt56-router-luna-worker.toml"
        conflict.write_text("user-owned\n")

        completed, result = self.run_manager("install", "--force")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(len(result["backed_up"]), 1)
        backup = Path(result["backed_up"][0])
        self.assertEqual(backup.read_text(), "user-owned\n")
        self.assertTrue(conflict.read_text().startswith("# Managed by gpt-5-6-model-router;"))

    def test_force_backs_up_divergent_schema_one_template(self) -> None:
        self.destination.mkdir(parents=True)
        conflict = self.destination / "gpt56-router-luna-worker.toml"
        original = (
            "# Managed by gpt-5-6-model-router; agent=gpt56_router_luna_worker; schema=1\n"
            'name = "gpt56_router_luna_worker"\n'
        )
        conflict.write_text(original)

        completed, result = self.run_manager("install", "--force")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(Path(result["backed_up"][0]).read_text(), original)
        self.assertTrue(conflict.read_text().startswith("# Managed by gpt-5-6-model-router; agent=gpt56_router_luna_worker; schema=2"))

    def test_safe_uninstall_migrates_legacy_backup_out_of_agent_discovery(self) -> None:
        self.run_manager("install")
        backup_dir = self.destination / ".gpt56-router-backups" / "fixture"
        backup_dir.mkdir(parents=True)
        (backup_dir / "keep.txt").write_text("keep")

        completed, result = self.run_manager("uninstall")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(len(result["changed"]), EXPECTED_COUNT)
        self.assertFalse(backup_dir.exists())
        self.assertEqual(len(result["migrated_backups"]), 1)
        self.assertTrue((Path(result["migrated_backups"][0]) / "fixture" / "keep.txt").is_file())
        self.assertEqual(list(self.destination.glob("gpt56-router-*.toml")), [])

    def test_check_detects_and_install_migrates_legacy_backup(self) -> None:
        self.run_manager("install")
        legacy = self.destination / ".gpt56-router-backups" / "fixture"
        legacy.mkdir(parents=True)
        (legacy / "keep.txt").write_text("keep")

        checked, checked_result = self.run_manager("check")
        self.assertEqual(checked.returncode, 1)
        self.assertIn("custom-agent discovery tree", checked_result["errors"][0])

        installed, installed_result = self.run_manager("install")
        self.assertEqual(installed.returncode, 0)
        self.assertFalse((self.destination / ".gpt56-router-backups").exists())
        migrated = Path(installed_result["migrated_backups"][0])
        self.assertTrue((migrated / "fixture" / "keep.txt").is_file())

    def test_uninstall_refuses_unmanaged_destination_without_partial_deletion(self) -> None:
        self.run_manager("install")
        conflict = self.destination / "gpt56-router-terra-worker.toml"
        conflict.write_text("user-owned\n")

        completed, result = self.run_manager("uninstall")
        self.assertEqual(completed.returncode, 1)
        self.assertTrue(result["errors"])
        self.assertEqual(len(list(self.destination.glob("gpt56-router-*.toml"))), EXPECTED_COUNT)

    def test_uninstall_refuses_incorrect_capability_marker_without_partial_deletion(self) -> None:
        self.run_manager("install")
        conflict = self.destination / "gpt56-router-sol-engineer.toml"
        conflict.write_text(
            conflict.read_text().replace(
                "# Router capability: may_delegate=true",
                "# Router capability: may_delegate=false",
            )
        )

        completed, result = self.run_manager("uninstall")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("router capability marker", result["errors"][0])
        self.assertEqual(len(list(self.destination.glob("gpt56-router-*.toml"))), EXPECTED_COUNT)

    def test_uninstall_refuses_customized_managed_file_without_partial_deletion(self) -> None:
        self.run_manager("install")
        customized = self.destination / "gpt56-router-terra-worker.toml"
        customized.write_text(customized.read_text() + "\n# local customization\n")

        completed, result = self.run_manager("uninstall")

        self.assertEqual(completed.returncode, 1)
        self.assertIn(customized.name, result["divergent"])
        self.assertIn("refusing to remove divergent files", result["errors"][0])
        self.assertEqual(len(list(self.destination.glob("gpt56-router-*.toml"))), EXPECTED_COUNT)

    def test_force_uninstall_backs_up_customized_file_before_removal(self) -> None:
        self.run_manager("install")
        customized = self.destination / "gpt56-router-terra-worker.toml"
        customized_content = customized.read_text() + "\n# local customization\n"
        customized.write_text(customized_content)

        completed, result = self.run_manager("uninstall", "--force")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(len(result["backed_up"]), 1)
        self.assertEqual(Path(result["backed_up"][0]).read_text(), customized_content)
        self.assertEqual(len(result["changed"]), EXPECTED_COUNT)
        self.assertEqual(list(self.destination.glob("gpt56-router-*.toml")), [])


if __name__ == "__main__":
    unittest.main()
