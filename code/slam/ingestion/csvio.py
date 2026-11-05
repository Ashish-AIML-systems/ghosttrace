"""Strict CSV reading that keeps source line numbers for provenance."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .issues import Issue

_ENCODING = "utf-8-sig"  # a leading BOM is tolerated and dropped; recorded nowhere else


@dataclass(frozen=True, slots=True)
class RawRow:
    """One CSV record. ``shape_error`` is set when the field count is wrong."""

    line_start: int
    line_end: int
    values: dict[str, str]
    shape_error: str | None


@dataclass(frozen=True, slots=True)
class CsvRead:
    columns: tuple[str, ...]
    rows: tuple[RawRow, ...]
    issues: tuple[Issue, ...]
    fatal: bool


def _fatal(code: str, message: str, source_id: str) -> CsvRead:
    return CsvRead((), (), (Issue(code, "error", message, source_id=source_id),), True)


def read_csv(path: Path, required: Sequence[str], *, source_id: str) -> CsvRead:
    """Read ``path`` into rows. Never raises for bad content.

    File-level problems (unreadable, not UTF-8, missing/duplicate required
    columns) return ``fatal=True`` with an error issue. Row-level shape problems
    are reported on the row so the caller can reject it explicitly.
    """
    try:
        with path.open(encoding=_ENCODING, newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header:
                return _fatal("CSV_EMPTY", "file has no header row", source_id)
            if len(set(header)) != len(header):
                return _fatal("CSV_DUPLICATE_COLUMN", "duplicate column names", source_id)
            missing = [c for c in required if c not in header]
            if missing:
                return _fatal(
                    "CSV_MISSING_COLUMNS",
                    f"missing required columns: {', '.join(missing)}",
                    source_id,
                )
            rows: list[RawRow] = []
            previous_end = reader.line_num
            for fields in reader:
                start, end = previous_end + 1, reader.line_num
                previous_end = end
                if not fields:  # blank line: carries no record
                    continue
                error = None
                if len(fields) != len(header):
                    error = f"expected {len(header)} fields, found {len(fields)}"
                padded = (fields + [""] * len(header))[: len(header)]
                rows.append(RawRow(start, end, dict(zip(header, padded, strict=True)), error))
    except FileNotFoundError:
        return _fatal("CSV_NOT_FOUND", "file does not exist", source_id)
    except UnicodeDecodeError:
        return _fatal("CSV_NOT_UTF8", "file is not valid UTF-8", source_id)
    except (OSError, csv.Error) as exc:
        return _fatal("CSV_UNREADABLE", f"cannot read file: {type(exc).__name__}", source_id)
    return CsvRead(tuple(header), tuple(rows), (), False)
