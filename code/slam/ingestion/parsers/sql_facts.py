"""SQL snapshot evidence parser: sandboxed replay, then rows become facts.

Two table shapes occur. Generic tables hold ``record_json`` with the owning
``origin_system`` and ``collection_name``; typed tables have one column set per
data category. A ``snapshot_scope`` table lists which systems the snapshot
covered and when, which is positive evidence of coverage and also the capture
time used for the rows of that system.

A row's effective time is the capture time of its system in this snapshot. Its
own ``updated_at`` says when the data last changed, not when it was seen, so
it stays in the fields.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..issues import Issue
from ..timeutil import parse_utc
from ..vocab import COLLECTIONS
from .base import ParseOutput, RawFact, SourceContext, line_span, row_span
from .sql_sandbox import SqlSnapshot, SqlTable, parse_sql_snapshot

PARSER_NAME = "sql"
PARSER_VERSION = "1.0.0"

SCOPE_TABLE = "snapshot_scope"
_HEADER_TIME_KEYS = ("Captured at", "snapshot_completed_at")


def _snapshot_time(snap: SqlSnapshot) -> datetime | None:
    for key in _HEADER_TIME_KEYS:
        if key in snap.header:
            try:
                return parse_utc(snap.header[key][0])
            except ValueError:
                continue
    return None


def _scope_times(snap: SqlSnapshot, issues: list[Issue], source_id: str) -> dict[str, datetime]:
    table = snap.tables.get(SCOPE_TABLE)
    out: dict[str, datetime] = {}
    if table is None:
        return out
    for row in table.rows:
        system, stamp = row.values.get("origin_system"), row.values.get("captured_at")
        try:
            if isinstance(system, str) and isinstance(stamp, str):
                out[system] = parse_utc(stamp)
                continue
        except ValueError:
            pass
        issues.append(
            Issue(
                "SQL_SCOPE_ROW_INVALID",
                "warning",
                "snapshot_scope row has no usable origin_system/captured_at",
                source_id,
                f"{SCOPE_TABLE} row {row.rowid}",
            )
        )
    return out


def _spans(ctx: SourceContext, table: SqlTable, index: int) -> tuple[Any, tuple[Any, ...]]:
    row = table.rows[index]
    number = row.rowid if row.rowid is not None else index + 1
    first = row_span(ctx.source_id, table.name, number)
    if row.line_start is None or row.line_end is None:
        return first, ()
    return first, (line_span(ctx.source_id, row.line_start, row.line_end),)


def parse_sql(ctx: SourceContext, data: bytes) -> ParseOutput:
    snap = parse_sql_snapshot(data, source_id=ctx.source_id)
    issues: list[Issue] = list(snap.issues)
    if snap.status == "failed":
        return ParseOutput(PARSER_NAME, PARSER_VERSION, (), tuple(issues), "failed")

    header_time = _snapshot_time(snap)
    scope = _scope_times(snap, issues, ctx.source_id)
    default_time = header_time or ctx.captured_at
    if header_time is None and not scope:
        issues.append(
            Issue(
                "SQL_TIME_FALLBACK",
                "info",
                "no capture time inside the snapshot; the manifest capture time was used",
                ctx.source_id,
            )
        )
    topology = snap.header.get("Database topology", (None, 0))[0]

    facts: list[RawFact] = []
    for table in snap.tables.values():
        for index, row in enumerate(table.rows):
            span, more = _spans(ctx, table, index)
            provenance = {"topology": topology} if topology else {}
            if table.name == SCOPE_TABLE:
                system = row.values.get("origin_system")
                when = scope.get(system) if isinstance(system, str) else None
                if when is None:
                    continue  # already reported by _scope_times
                facts.append(
                    RawFact(
                        layout="sql.scope",
                        effective_time=when,
                        span=span,
                        more_spans=more,
                        data=dict(row.values),
                        system_id=system if isinstance(system, str) else None,
                        collection=SCOPE_TABLE,
                        container=table.name,
                        provenance=provenance,
                    )
                )
                continue

            if "record_json" in row.values:
                record = _load_record(row.values.get("record_json"))
                if record is None:
                    issues.append(
                        Issue(
                            "SQL_RECORD_JSON_INVALID",
                            "warning",
                            "record_json is not a JSON object; row skipped",
                            ctx.source_id,
                            f"{table.name} row {row.rowid}",
                        )
                    )
                    continue
                fields = dict(record)
                fields.setdefault("updated_at", row.values.get("updated_at"))
                system = row.values.get("origin_system")
                collection = row.values.get("collection_name")
                resource = record.get("resource_id") or row.values.get("resource_id")
                if (
                    record.get("resource_id")
                    and row.values.get("resource_id")
                    and record["resource_id"] != row.values["resource_id"]
                ):
                    issues.append(
                        Issue(
                            "SQL_RESOURCE_ID_MISMATCH",
                            "warning",
                            "row resource_id differs from the id inside record_json; both kept",
                            ctx.source_id,
                            f"{table.name} row {row.rowid}",
                        )
                    )
                    fields["row_resource_id"] = row.values["resource_id"]
                owner = system if isinstance(system, str) else None
                facts.append(
                    RawFact(
                        layout="sql.generic",
                        effective_time=scope.get(owner or "", default_time),
                        span=span,
                        more_spans=more,
                        data=fields,
                        system_id=owner,
                        resource_id=resource if isinstance(resource, str) else None,
                        collection=collection if isinstance(collection, str) else None,
                        container=table.name,
                        provenance=provenance,
                    )
                )
                continue

            resource = row.values.get("resource_id")
            vocab = COLLECTIONS.get(table.name)
            owner = vocab[1] if vocab else None
            facts.append(
                RawFact(
                    layout="sql.typed",
                    effective_time=scope.get(owner or "", default_time),
                    span=span,
                    more_spans=more,
                    data=dict(row.values),
                    system_id=owner,
                    resource_id=resource if isinstance(resource, str) else None,
                    collection=table.name,
                    container=table.name,
                    provenance=provenance,
                )
            )

    has_error = any(i.severity == "error" for i in issues)
    status = snap.status if snap.status != "parsed" or not has_error else "partial"
    if status == "parsed" and any(i.severity == "warning" for i in issues):
        status = "partial"
    stats = {
        "statements": snap.statements_total,
        "statements_ok": snap.statements_ok,
        "tables": len(snap.tables),
        "facts": len(facts),
    }
    return ParseOutput(PARSER_NAME, PARSER_VERSION, tuple(facts), tuple(issues), status, stats)


def _load_record(value: object) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        loaded = json.loads(value)
    except ValueError:
        return None
    return loaded if isinstance(loaded, dict) else None
