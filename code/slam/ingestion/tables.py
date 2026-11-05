"""Loaders for the tabular dataset files, keeping row-level provenance.

These return validated rows plus source line ranges. Mapping rows onto contract
types (``AuditRequest``, identities, activities, rules) happens later in the
normalizer. Values are kept exactly as supplied: no lower-casing, trimming or
merging here, so original text stays available as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .csvio import read_csv
from .issues import Issue, RowErrors
from .paths import UnsafePathError, resolve_under_root
from .timeutil import parse_utc


@dataclass(frozen=True, slots=True)
class TableSpec:
    name: str
    filename: str
    columns: tuple[str, ...]
    id_column: str
    timestamp_columns: tuple[str, ...] = ()


TABLE_SPECS: dict[str, TableSpec] = {
    spec.name: spec
    for spec in (
        TableSpec(
            "deletion_requests",
            "deletion_requests.csv",
            (
                "case_id",
                "email",
                "requested_at",
                "reported_status",
                "reported_at",
                "audit_at",
                "request_text",
            ),
            "case_id",
            ("requested_at", "reported_at", "audit_at"),
        ),
        TableSpec(
            "sample_deletion_requests",
            "sample_deletion_requests.csv",
            (
                "case_id",
                "email",
                "requested_at",
                "reported_status",
                "reported_at",
                "audit_at",
                "request_text",
            ),
            "case_id",
            ("requested_at", "reported_at", "audit_at"),
        ),
        TableSpec(
            "user_identities",
            "user_identities.csv",
            ("user_id", "name", "email", "phone", "email_hash", "updated_at"),
            "user_id",
            ("updated_at",),
        ),
        TableSpec(
            "user_audit_log",
            "user_audit_log.csv",
            ("audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"),
            "audit_id",
            ("event_time",),
        ),
        TableSpec(
            "system_activity",
            "system_activity.csv",
            (
                "activity_id",
                "event_time",
                "event_type",
                "source_system",
                "target_system",
                "resource_id",
                "reported_result",
                "details",
            ),
            "activity_id",
            ("event_time",),
        ),
        TableSpec(
            "deletion_rules",
            "deletion_rules.csv",
            ("rule_id", "data_category", "condition", "required_action"),
            "rule_id",
        ),
    )
}


@dataclass(frozen=True, slots=True)
class TableRow:
    line_start: int
    line_end: int
    row_id: str
    values: dict[str, str]
    times: dict[str, datetime]  # parsed UTC form of each timestamp column


@dataclass(frozen=True, slots=True)
class RejectedRow:
    line_start: int
    line_end: int
    row_id: str | None
    issues: tuple[Issue, ...]


@dataclass(frozen=True, slots=True)
class TableResult:
    name: str
    rows: tuple[TableRow, ...]
    rejected: tuple[RejectedRow, ...]
    issues: tuple[Issue, ...]
    row_count: int
    fatal: bool

    @property
    def accounted(self) -> bool:
        return len(self.rows) + len(self.rejected) == self.row_count


def load_table(dataset_dir: Path, name: str) -> TableResult:
    """Load one named table. Unknown names raise ``KeyError`` (a programming error)."""
    spec = TABLE_SPECS[name]
    try:
        path = resolve_under_root(Path(dataset_dir), spec.filename)
    except UnsafePathError as exc:
        issue = Issue(exc.code, "error", str(exc), source_id=spec.filename)
        return TableResult(name, (), (), (issue,), 0, True)

    csv_read = read_csv(path, spec.columns, source_id=spec.filename)
    if csv_read.fatal:
        return TableResult(name, (), (), csv_read.issues, 0, True)

    id_counts: dict[str, int] = {}
    for raw in csv_read.rows:
        key = raw.values[spec.id_column]
        id_counts[key] = id_counts.get(key, 0) + 1

    rows: list[TableRow] = []
    rejected: list[RejectedRow] = []
    all_issues: list[Issue] = []
    for raw in csv_read.rows:
        row_id = raw.values[spec.id_column]
        locator = f"{spec.filename}:{raw.line_start}"
        errors = RowErrors(row_id or None, locator)
        error = errors.add

        if raw.shape_error:
            error("TABLE_ROW_MALFORMED", raw.shape_error)
        if not row_id:
            error("TABLE_ID_EMPTY", f"{spec.id_column} is empty")
        elif id_counts[row_id] > 1:
            error("TABLE_DUPLICATE_ID", f"{spec.id_column} is used by more than one row")
        times: dict[str, datetime] = {}
        for column in spec.timestamp_columns:
            try:
                times[column] = parse_utc(raw.values[column])
            except ValueError as exc:
                error("TABLE_BAD_TIMESTAMP", f"{column}: {exc}")

        all_issues.extend(errors.issues)
        if errors.has_error:
            rejected.append(
                RejectedRow(raw.line_start, raw.line_end, row_id or None, tuple(errors.issues))
            )
        else:
            rows.append(TableRow(raw.line_start, raw.line_end, row_id, raw.values, times))

    return TableResult(
        name, tuple(rows), tuple(rejected), tuple(all_issues), len(csv_read.rows), False
    )
