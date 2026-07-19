#!/usr/bin/env python3
"""Build a deterministic, sanitized skills-only plugin archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "gpt-5-6-model-router"
ARCHIVE_ROOT = PLUGIN.name
EXCLUDED_NAMES = {".DS_Store", ".git", ".omo", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
TEXT_SUFFIXES = {".json", ".md", ".py", ".toml", ".yaml", ".yml", ".txt"}
PRIVATE_PATTERNS = {
    "absolute macOS user path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "persisted rollout identifier": re.compile(
        r"\b019[0-9a-f]{5}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
    "GitHub token": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
    "OpenAI secret key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
}
ZIP_TIMESTAMP = (2026, 7, 19, 0, 0, 0)


def included_files() -> list[Path]:
    files: list[Path] = []
    for path in PLUGIN.rglob("*"):
        relative = path.relative_to(PLUGIN)
        if any(part in EXCLUDED_NAMES for part in relative.parts):
            continue
        if path.is_file() and path.suffix not in EXCLUDED_SUFFIXES:
            files.append(path)
    return sorted(files, key=lambda value: value.as_posix())


def validate_text(path: Path, data: bytes) -> None:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return
    text = data.decode("utf-8")
    for label, pattern in PRIVATE_PATTERNS.items():
        if pattern.search(text):
            raise ValueError(f"{label} found in {path.relative_to(PLUGIN)}")


def default_output() -> Path:
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    base_version = str(manifest["version"]).split("+", 1)[0]
    return ROOT / "dist" / f"{PLUGIN.name}-{base_version}.zip"


def build(output: Path) -> dict[str, object]:
    paths = included_files()
    if not paths:
        raise ValueError("plugin contains no publishable files")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            data = path.read_bytes()
            validate_text(path, data)
            relative = path.relative_to(PLUGIN).as_posix()
            info = zipfile.ZipInfo(f"{ARCHIVE_ROOT}/{relative}", ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "ok": True,
        "archive": str(output),
        "sha256": digest,
        "file_count": len(paths),
        "archive_root": ARCHIVE_ROOT,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_output())
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
