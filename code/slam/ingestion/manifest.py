"""Evidence manifest loader (``evidence_files.csv``).

Every manifest row ends up in exactly one place: ``entries`` (usable) or
``rejected`` (with explicit issues). Nothing is dropped silently, and a bad
row never aborts the rest. Hashes are computed here; the official manifest has
no hash column, so a ``sha256`` column is validated only if a dataset has one.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .csvio import read_csv
from .issues import Issue, RowErrors
from .paths import UnsafePathError, resolve_under_root
from .timeutil import parse_utc

MANIFEST_FILENAME = "evidence_files.csv"
EVIDENCE_DIRNAME = "evidence"
REQUIRED_COLUMNS = ("file_id", "file_path", "origin", "captured_at")
OPTIONAL_HASH_COLUMN = "sha256"
DEFAULT_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_HASH_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    file_id: str
    rel_path: str
    origin: str
    captured_at: datetime  # manifest capture time, UTC
    path: Path  # resolved, verified to exist under the dataset root
    sha256: str
    size_bytes: int
    line_no: int


@dataclass(frozen=True, slots=True)
class RejectedEntry:
    line_no: int
    file_id: str | None
    rel_path: str | None
    issues: tuple[Issue, ...]


@dataclass(frozen=True, slots=True)
class ManifestResult:
    entries: tuple[ManifestEntry, ...]
    rejected: tuple[RejectedEntry, ...]
    issues: tuple[Issue, ...]  # every issue (file, row and corpus level), in order
    row_count: int
    fatal: bool

    @property
    def accounted(self) -> bool:
        """True when every manifest row is either an entry or a rejection."""
        return len(self.entries) + len(self.rejected) == self.row_count


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(
    dataset_dir: Path,
    *,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
    report_unmanifested: bool = True,
) -> ManifestResult:
    root = Path(dataset_dir).resolve()
    all_issues: list[Issue] = []
    if not root.is_dir():
        all_issues.append(Issue("DATASET_NOT_FOUND", "error", "dataset directory does not exist"))
        return ManifestResult((), (), tuple(all_issues), 0, True)

    csv_read = read_csv(root / MANIFEST_FILENAME, REQUIRED_COLUMNS, source_id=MANIFEST_FILENAME)
    if csv_read.fatal:
        return ManifestResult((), (), csv_read.issues, 0, True)

    for column in csv_read.columns:
        if column not in REQUIRED_COLUMNS and column != OPTIONAL_HASH_COLUMN:
            all_issues.append(
                Issue(
                    "MANIFEST_EXTRA_COLUMN",
                    "warning",
                    f"unrecognised column '{column}' ignored",
                    source_id=MANIFEST_FILENAME,
                )
            )

    id_counts = Counter(r.values["file_id"] for r in csv_read.rows)
    path_counts = Counter(r.values["file_path"] for r in csv_read.rows)
    entries: list[ManifestEntry] = []
    rejected: list[RejectedEntry] = []

    for raw in csv_read.rows:
        values = raw.values
        file_id, rel_path = values["file_id"], values["file_path"]
        locator = f"{MANIFEST_FILENAME}:{raw.line_start}"
        errors = RowErrors(file_id or None, locator)
        error = errors.add

        if raw.shape_error:
            error("MANIFEST_ROW_MALFORMED", raw.shape_error)
        if not file_id:
            error("MANIFEST_ID_EMPTY", "file_id is empty")
        elif file_id != file_id.strip():
            error("MANIFEST_ID_WHITESPACE", "file_id has leading/trailing space")
        elif id_counts[file_id] > 1:
            error("MANIFEST_DUPLICATE_ID", "file_id is used by more than one row")
        if not values["origin"].strip():
            error("MANIFEST_ORIGIN_EMPTY", "origin is empty")

        captured_at: datetime | None = None
        try:
            captured_at = parse_utc(values["captured_at"])
        except ValueError as exc:
            error("MANIFEST_BAD_TIMESTAMP", f"captured_at: {exc}")

        resolved: Path | None = None
        try:
            resolved = resolve_under_root(root, rel_path)
        except UnsafePathError as exc:
            error(exc.code, str(exc))

        sha = ""
        size = 0
        if resolved is not None:
            if not resolved.is_file():
                error("SOURCE_NOT_FOUND", "referenced file does not exist")
            else:
                size = resolved.stat().st_size
                if size > max_source_bytes:
                    error("SOURCE_TOO_LARGE", f"file is {size} bytes, over the limit")
                else:
                    try:
                        sha = _sha256(resolved)
                    except OSError as exc:
                        error("SOURCE_UNREADABLE", f"cannot read file: {type(exc).__name__}")

        declared = values.get(OPTIONAL_HASH_COLUMN)
        if declared and sha and declared.lower() != sha:
            error("SOURCE_HASH_MISMATCH", "file content does not match manifest sha256")

        if path_counts[rel_path] > 1:
            errors.warn("MANIFEST_DUPLICATE_PATH", "path is referenced by more than one row")

        all_issues.extend(errors.issues)
        if errors.has_error:
            rejected.append(
                RejectedEntry(
                    raw.line_start, file_id or None, rel_path or None, tuple(errors.issues)
                )
            )
        else:
            assert captured_at is not None and resolved is not None
            entries.append(
                ManifestEntry(
                    file_id,
                    rel_path,
                    values["origin"],
                    captured_at,
                    resolved,
                    sha,
                    size,
                    raw.line_start,
                )
            )

    if report_unmanifested:
        all_issues.extend(_unmanifested_files(root, {r.values["file_path"] for r in csv_read.rows}))

    return ManifestResult(
        tuple(entries), tuple(rejected), tuple(all_issues), len(csv_read.rows), False
    )


def _unmanifested_files(root: Path, listed: set[str]) -> list[Issue]:
    """Warn about evidence files the manifest does not mention.

    Not sources (the manifest is authoritative), but worth surfacing in the
    corpus inventory. Symlinks are listed, never followed.
    """
    base = root / EVIDENCE_DIRNAME
    if not base.is_dir():
        return []
    found: list[str] = []
    for path in base.rglob("*"):
        if path.is_file() or path.is_symlink():
            found.append(path.relative_to(root).as_posix())
    return [
        Issue(
            "SOURCE_NOT_IN_MANIFEST",
            "warning",
            "evidence file is not listed in the manifest and is not ingested",
            None,
            rel,
        )
        for rel in sorted(found)
        if rel not in listed
    ]
