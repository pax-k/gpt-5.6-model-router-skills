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
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "build_publication.py"),
                        "--output",
                        str(output),
                        "--source-date-epoch",
                        "1784764801",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(json.loads(result.stdout))
                checksum = Path(outputs[-1]["checksum"])
                self.assertEqual(
                    checksum.read_text(),
                    f"{outputs[-1]['sha256']}  {output.name}\n",
                )
            self.assertEqual(outputs[0]["sha256"], outputs[1]["sha256"])
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertTrue(names)
                self.assertTrue(all(name.startswith("gpt-5-6-model-router/") for name in names))
                self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
                self.assertIn("gpt-5-6-model-router/.codex-plugin/plugin.json", names)
                self.assertIn("gpt-5-6-model-router/assets/logo.png", names)
                self.assertIn("gpt-5-6-model-router/hooks/hooks.json", names)
                self.assertIn("gpt-5-6-model-router/LICENSE", names)
                self.assertIn("gpt-5-6-model-router/vendor/tomli/LICENSE", names)
                self.assertTrue(all(item.date_time == (2026, 7, 23, 0, 0, 0) for item in archive.infolist()))
                manifest = json.loads(archive.read("gpt-5-6-model-router/.codex-plugin/plugin.json"))
                interface = manifest["interface"]
                self.assertEqual(interface["composerIcon"], "./assets/logo.png")
                self.assertNotIn("brandColor", interface)
                self.assertLessEqual(len(interface["shortDescription"]), 30)

    def test_release_build_requires_an_annotated_tag(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_publication.py"),
                "--release-tag",
                "definitely-not-a-release-tag",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release ref must be an annotated tag", result.stderr)


if __name__ == "__main__":
    unittest.main()
