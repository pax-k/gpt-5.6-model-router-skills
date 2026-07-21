from __future__ import annotations
import hashlib, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SETUP = ROOT / "plugins/gpt-5-6-model-router/skills/setup-gpt56-model-router/scripts/setup_router.py"
sys.path.insert(0, str(SETUP.parent))
import manage_agents  # noqa: E402
import setup_router  # noqa: E402


class SetupRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.home = Path(self.temp.name)
        self.env = {**os.environ, "HOME": str(self.home)}
        self.codex = self.home / ".codex"; self.config = self.codex / "config.toml"

    def tearDown(self): self.temp.cleanup()

    def run_setup(self, command, *args):
        done = subprocess.run([sys.executable, str(SETUP), command, *args, "--json"], env=self.env, text=True, capture_output=True)
        return done, json.loads(done.stdout)

    def write_config(self, text): self.codex.mkdir(parents=True, exist_ok=True); self.config.write_text(text)

    def test_clean_install_check_uninstall(self):
        installed, result = self.run_setup("install")
        self.assertEqual(installed.returncode, 0, result); self.assertEqual(result["depth"]["effective_depth"], 2)
        self.assertIn("schema=4", next((self.codex / "agents").glob("*.toml")).read_text().splitlines()[0])
        checked, result = self.run_setup("check"); self.assertEqual(checked.returncode, 0, result)
        removed, result = self.run_setup("uninstall"); self.assertEqual(removed.returncode, 0, result)
        self.assertFalse(self.config.exists()); self.assertFalse(list((self.codex / "agents").glob("gpt56-router-*.toml")))

    def test_depth_absent_one_two_and_greater_than_two(self):
        for initial, expected_after_remove in ((None, None), (1, 1), (2, 2), (4, 4)):
            with self.subTest(initial=initial):
                if initial is not None: self.write_config(f"[agents]\nmax_depth = {initial}\n")
                installed, result = self.run_setup("install"); self.assertEqual(installed.returncode, 0, result)
                self.assertGreaterEqual(result["depth"]["effective_depth"], 2)
                removed, result = self.run_setup("uninstall"); self.assertEqual(removed.returncode, 0, result)
                if expected_after_remove is None: self.assertFalse(self.config.exists())
                else: self.assertIn(f"max_depth = {expected_after_remove}", self.config.read_text())
                subprocess.run([sys.executable, str(SETUP), "uninstall", "--force", "--json"], env=self.env, capture_output=True)
                if self.codex.exists():
                    for path in (self.codex / "agents").glob("gpt56-router-*.toml"): path.unlink()

    def test_legacy_depth_is_adopted_with_original_restoration(self):
        original = b"[agents]\nmax_depth = 1\n[ui]\ntheme = 'dark'\n"
        managed = b"[agents]\n# Managed by gpt-5-6-model-router; recursion; schema=2\nmax_depth = 2\n[ui]\ntheme = 'dark'\n"
        self.codex.mkdir(parents=True); backup = self.codex / "legacy-backup.toml"; backup.write_bytes(original); self.config.write_bytes(managed)
        (self.codex / ".gpt56-router-recursion-state.json").write_text(json.dumps({
            "schema": 2, "backup_path": str(backup), "original_exists": True,
            "original_sha256": hashlib.sha256(original).hexdigest(), "managed_sha256": hashlib.sha256(managed).hexdigest(),
        }))
        installed, result = self.run_setup("install"); self.assertEqual(installed.returncode, 0, result)
        self.assertIn("depth; schema=3", self.config.read_text())
        self.config.write_text(self.config.read_text() + "# later unrelated edit\n")
        removed, result = self.run_setup("uninstall"); self.assertEqual(removed.returncode, 0, result)
        self.assertIn("max_depth = 1", self.config.read_text()); self.assertIn("later unrelated edit", self.config.read_text())

    def test_legacy_depth_adoption_preserves_preexisting_unrelated_edits(self):
        original = b"[agents]\nmax_depth = 1\n"
        managed_snapshot = b"[agents]\n# Managed by gpt-5-6-model-router; recursion; schema=2\nmax_depth = 2\n"
        current = managed_snapshot + b"[ui]\ntheme = 'later'\n"
        self.codex.mkdir(parents=True); backup = self.codex / "legacy-backup.toml"; backup.write_bytes(original); self.config.write_bytes(current)
        (self.codex / ".gpt56-router-recursion-state.json").write_text(json.dumps({
            "schema": 2, "backup_path": str(backup), "original_exists": True,
            "original_sha256": hashlib.sha256(original).hexdigest(), "managed_sha256": hashlib.sha256(managed_snapshot).hexdigest(),
        }))
        installed, result = self.run_setup("install"); self.assertEqual(installed.returncode, 0, result)
        removed, result = self.run_setup("uninstall"); self.assertEqual(removed.returncode, 0, result)
        self.assertIn("max_depth = 1", self.config.read_text()); self.assertIn("theme = 'later'", self.config.read_text())

    def test_modified_template_refuses_without_force(self):
        agents = self.codex / "agents"; agents.mkdir(parents=True); target = agents / "gpt56-router-luna-worker.toml"; target.write_text("user edit\n")
        refused, result = self.run_setup("install"); self.assertEqual(refused.returncode, 1); self.assertEqual(target.read_text(), "user edit\n")
        forced, result = self.run_setup("install", "--force"); self.assertEqual(forced.returncode, 0, result)

    def test_user_edited_managed_depth_blocks_all_mutation(self):
        self.run_setup("install"); agent = next((self.codex / "agents").glob("*.toml")); before = agent.read_bytes()
        self.config.write_text(self.config.read_text().replace("max_depth = 2", "max_depth = 3"))
        refused, result = self.run_setup("uninstall"); self.assertEqual(refused.returncode, 1)
        self.assertEqual(agent.read_bytes(), before); self.assertIn("max_depth = 3", self.config.read_text())

    def test_post_install_failure_rolls_back_templates_and_depth(self):
        failed = manage_agents.Result(ok=False, command="check", target_dir=str(self.codex / "agents"), errors=["injected post-check failure"])
        with mock.patch.object(setup_router.manage_agents, "check_agents", return_value=failed):
            result = setup_router.run("install", codex=self.codex)
        self.assertFalse(result.ok); self.assertTrue(result.rolled_back)
        self.assertFalse(self.config.exists())
        self.assertFalse(list((self.codex / "agents").glob("gpt56-router-*.toml")))


if __name__ == "__main__": unittest.main()
