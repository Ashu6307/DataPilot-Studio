"""Filesystem isolation and immutable-source checks."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

ALLOWED_SUFFIXES = {".csv", ".xlsx", ".xlsm"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_filename(name: str) -> str:
    basename = Path(name).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(basename).stem).strip("._") or "source"
    suffix = Path(basename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported source type: {suffix or 'none'}")
    return f"{stem[:100]}{suffix}"


@dataclass(frozen=True, slots=True)
class SourceFile:
    id: UUID
    path: Path
    original_filename: str
    sha256: str
    size_bytes: int

    def assert_unchanged(self) -> None:
        current = sha256_file(self.path)
        if current != self.sha256:
            raise RuntimeError("SOURCE_FINGERPRINT_CHANGED")


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.uploads = self.root / "uploads"
        self.runs = self.root / "runs"
        self.projects = self.root / "projects"
        for directory in (self.uploads, self.runs, self.projects):
            directory.mkdir(parents=True, exist_ok=True)

    def import_source(self, stream_path: Path, original_filename: str, source_id: UUID | None = None) -> SourceFile:
        """Copy into the managed source area without modifying the supplied file."""
        clean_name = safe_filename(original_filename)
        identifier = source_id or uuid4()
        source_dir = (self.uploads / str(identifier)).resolve()
        source_dir.mkdir(parents=True, exist_ok=False)
        destination = (source_dir / clean_name).resolve()
        if source_dir not in destination.parents:
            raise ValueError("unsafe source path")
        shutil.copyfile(stream_path, destination)
        return SourceFile(
            id=identifier,
            path=destination,
            original_filename=original_filename,
            sha256=sha256_file(destination),
            size_bytes=destination.stat().st_size,
        )

    def source_from_id(self, source_id: UUID, original_filename: str, fingerprint: str) -> SourceFile:
        source_dir = (self.uploads / str(source_id)).resolve()
        candidates = [item for item in source_dir.iterdir() if item.is_file()] if source_dir.exists() else []
        if len(candidates) != 1:
            raise FileNotFoundError(f"source not found: {source_id}")
        path = candidates[0].resolve()
        if source_dir not in path.parents:
            raise ValueError("unsafe source handle")
        return SourceFile(source_id, path, original_filename, fingerprint, path.stat().st_size)

    def create_run_directory(self, run_id: UUID) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        directory = (self.runs / f"{timestamp}_{run_id}").resolve()
        directory.mkdir(parents=True, exist_ok=False)
        for name in ("config-snapshot", "logs", "checkpoints", "outputs"):
            (directory / name).mkdir()
        return directory

