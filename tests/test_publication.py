from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class PublicationTests(unittest.TestCase):
    def test_publication_contracts(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_publication.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_archive_is_deterministic_and_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.zip"
            second = Path(temp) / "second.zip"
            outputs = []
            for output in (first, second):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "build_publication.py"), "--output", str(output)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(json.loads(result.stdout))
            self.assertEqual(outputs[0]["sha256"], outputs[1]["sha256"])
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertTrue(names)
                self.assertTrue(all(name.startswith("gpt-5-6-model-router/") for name in names))
                self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
                self.assertIn("gpt-5-6-model-router/.codex-plugin/plugin.json", names)
                self.assertIn("gpt-5-6-model-router/assets/logo.png", names)


if __name__ == "__main__":
    unittest.main()
