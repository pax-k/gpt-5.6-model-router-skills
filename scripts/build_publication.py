#!/usr/bin/env python3
"""Build a deterministic, sanitized hook-bearing plugin archive."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import zipfile
from pathlib import Path
from typing import Optional


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


def source_date_epoch() -> int:
    configured = os.environ.get("SOURCE_DATE_EPOCH")
    if configured is not None:
        try:
            epoch = int(configured)
        except ValueError as error:
            raise ValueError("SOURCE_DATE_EPOCH must be an integer") from error
        if epoch < 0:
            raise ValueError("SOURCE_DATE_EPOCH must be non-negative")
        return epoch
    for ref in ("HEAD",):
        completed = subprocess.run(
            ["git", "log", "-1", "--format=%ct", ref],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip().isdigit():
            return int(completed.stdout.strip())
    raise ValueError("set SOURCE_DATE_EPOCH or build from a Git repository")


def annotated_tag_epoch(tag: str) -> int:
    object_type = subprocess.run(
        ["git", "cat-file", "-t", tag],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if object_type.returncode != 0 or object_type.stdout.strip() != "tag":
        raise ValueError(f"release ref must be an annotated tag: {tag}")
    ref = f"refs/tags/{tag}"
    completed = subprocess.run(
        ["git", "for-each-ref", "--format=%(taggerdate:unix)", ref],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value.isdigit():
        raise ValueError(f"could not derive SOURCE_DATE_EPOCH from annotated tag: {tag}")
    return int(value)


def zip_timestamp(epoch: int) -> tuple[int, int, int, int, int, int]:
    value = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
    if value.year < 1980:
        value = value.replace(year=1980, month=1, day=1, hour=0, minute=0, second=0)
    return value.year, value.month, value.day, value.hour, value.minute, value.second - value.second % 2


def build(output: Path, epoch: Optional[int] = None) -> dict[str, object]:
    paths = included_files()
    if not paths:
        raise ValueError("plugin contains no publishable files")
    resolved_epoch = source_date_epoch() if epoch is None else epoch
    timestamp = zip_timestamp(resolved_epoch)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            data = path.read_bytes()
            validate_text(path, data)
            relative = path.relative_to(PLUGIN).as_posix()
            info = zipfile.ZipInfo(f"{ARCHIVE_ROOT}/{relative}", timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return {
        "ok": True,
        "archive": str(output),
        "sha256": digest,
        "checksum": str(checksum),
        "source_date_epoch": resolved_epoch,
        "file_count": len(paths),
        "archive_root": ARCHIVE_ROOT,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_output())
    parser.add_argument("--source-date-epoch", type=int)
    parser.add_argument("--release-tag", help="Require an annotated release tag and use its tagger epoch")
    args = parser.parse_args()
    if args.source_date_epoch is not None and args.release_tag:
        parser.error("--source-date-epoch and --release-tag are mutually exclusive")
    epoch = annotated_tag_epoch(args.release_tag) if args.release_tag else args.source_date_epoch
    print(json.dumps(build(args.output.resolve(), epoch), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
