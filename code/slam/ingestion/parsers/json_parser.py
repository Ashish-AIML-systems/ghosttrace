"""JSON evidence parser.

Recognises containers by structure (not by filename) and keeps the exact JSON
path of every record, so a span can point back to one object. Duplicate keys
are reported rather than silently overwritten. Unrecognised structure becomes
an explicit issue, never an assumption that the file holds nothing.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..issues import Issue, Severity
from ..timeutil import parse_utc
from .base import ParseOutput, ParseState, RawFact, SourceContext, json_span

PARSER_NAME = "json"
PARSER_VERSION = "1.0.0"

_LOOKUP_KEYS = frozenset({"resource_id", "record_type", "result"})
_SERVICE_TIME_FIELDS = ("observed_at", "recorded_at", "captured_at", "updated_at", "created_at")


def _pairs_hook(duplicates: list[str]) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                duplicates.append(key)
            seen[key] = value
        return seen

    return hook


class _Walker:
    def __init__(self, ctx: SourceContext, root: Any) -> None:
        self.ctx = ctx
        self.root = root
        self.facts: list[RawFact] = []
        self.issues: list[Issue] = []
        self.skipped = 0

    def issue(self, code: str, severity: Severity, message: str, path: str) -> None:
        self.issues.append(Issue(code, severity, message, self.ctx.source_id, path))

    def time_of(self, value: Any, fallback: datetime, path: str, label: str) -> datetime:
        if isinstance(value, str):
            try:
                return parse_utc(value)
            except ValueError:
                pass
        self.issue(
            "JSON_TIME_FALLBACK",
            "warning",
            f"{label} is missing or not a valid UTC timestamp; used a broader capture time",
            path,
        )
        return fallback

    def emit(
        self,
        path: str,
        record: dict[str, Any],
        when: datetime,
        *,
        layout: str,
        system_id: str | None = None,
        collection: str | None = None,
        container: str | None = None,
        state: str | None = None,
    ) -> None:
        resource = record.get("resource_id")
        self.facts.append(
            RawFact(
                layout=layout,
                effective_time=when,
                span=json_span(self.ctx.source_id, path),
                data=dict(record),
                system_id=system_id,
                resource_id=resource if isinstance(resource, str) and resource else None,
                collection=collection,
                container=container,
                state=state,
            )
        )

    # -- recognisers ---------------------------------------------------------

    def run(self) -> None:
        root = self.root
        if isinstance(root, dict):
            if isinstance(root.get("snapshots"), list):
                self.snapshot_bundle(root)
            elif isinstance(root.get("service_exports"), dict):
                self.service_exports(root)
            elif isinstance(root.get("records"), list):
                self.records_container(root)
        if not self.facts and not self.issues_of("JSON_UNMAPPED_STRUCTURE"):
            self.generic(root, "$")

    def issues_of(self, code: str) -> list[Issue]:
        return [i for i in self.issues if i.code == code]

    def container_time(self, root: dict[str, Any]) -> datetime:
        for key in ("exported_at", "captured_at"):
            value = root.get(key)
            if isinstance(value, str):
                try:
                    return parse_utc(value)
                except ValueError:
                    continue
        return self.ctx.captured_at

    def snapshot_bundle(self, root: dict[str, Any]) -> None:
        base = self.container_time(root)
        for i, snapshot in enumerate(root["snapshots"]):
            path = f"$.snapshots[{i}]"
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get("records"), list):
                self.issue(
                    "JSON_UNMAPPED_STRUCTURE", "warning", "snapshot has no records list", path
                )
                self.skipped += 1
                continue
            when = self.time_of(snapshot.get("captured_at"), base, path, "snapshot captured_at")
            store = snapshot.get("data_store")
            collection = snapshot.get("collection")
            for j, record in enumerate(snapshot["records"]):
                rpath = f"{path}.records[{j}]"
                if not isinstance(record, dict):
                    self.issue(
                        "JSON_UNMAPPED_STRUCTURE", "warning", "record is not an object", rpath
                    )
                    self.skipped += 1
                    continue
                if record.keys() >= _LOOKUP_KEYS:
                    self.lookup(rpath, record, when)
                else:
                    self.emit(
                        rpath,
                        record,
                        when,
                        layout="json.snapshot",
                        system_id=store if isinstance(store, str) else None,
                        collection=collection if isinstance(collection, str) else None,
                        container=f"snapshots[{i}]",
                    )

    def lookup(self, path: str, record: dict[str, Any], base: datetime) -> None:
        when = self.time_of(record.get("recorded_at"), base, path, "recorded_at")
        system = record.get("system")
        result = record.get("result")
        collection = record.get("record_type")
        self.emit(
            path,
            record,
            when,
            layout="json.lookup",
            system_id=system if isinstance(system, str) else None,
            collection=collection if isinstance(collection, str) else None,
            state=result if isinstance(result, str) else None,
        )

    def records_container(self, root: dict[str, Any]) -> None:
        base = self.container_time(root)
        collection = root.get("collection")
        for j, record in enumerate(root["records"]):
            path = f"$.records[{j}]"
            if not isinstance(record, dict):
                self.issue("JSON_UNMAPPED_STRUCTURE", "warning", "record is not an object", path)
                self.skipped += 1
            elif record.keys() >= _LOOKUP_KEYS:
                self.lookup(path, record, base)
            else:
                origin = root.get("origin")
                # Observed at the container's capture time. A record's own
                # created_at/updated_at stay in the fields: they say when it
                # changed, not when this evidence saw it.
                self.emit(
                    path,
                    record,
                    base,
                    layout="json.records",
                    system_id=origin if isinstance(origin, str) else None,
                    collection=collection if isinstance(collection, str) else None,
                )

    def service_exports(self, root: dict[str, Any]) -> None:
        base = self.container_time(root)
        for service, body in root["service_exports"].items():
            spath = f"$.service_exports.{service}"
            if not isinstance(body, dict):
                self.issue(
                    "JSON_UNMAPPED_STRUCTURE", "warning", "service export is not an object", spath
                )
                self.skipped += 1
                continue
            for list_name, items in body.items():
                lpath = f"{spath}.{list_name}"
                if not isinstance(items, list):
                    self.issue(
                        "JSON_UNMAPPED_STRUCTURE", "warning", "export section is not a list", lpath
                    )
                    self.skipped += 1
                    continue
                for k, item in enumerate(items):
                    path = f"{lpath}[{k}]"
                    if not isinstance(item, dict):
                        self.issue(
                            "JSON_UNMAPPED_STRUCTURE", "warning", "item is not an object", path
                        )
                        self.skipped += 1
                        continue
                    stamp = next((item[f] for f in _SERVICE_TIME_FIELDS if f in item), None)
                    self.emit(
                        path,
                        item,
                        self.time_of(stamp, base, path, "observed_at"),
                        layout="json.service_export",
                        system_id=service,
                        collection=list_name,
                        container=f"{service}.{list_name}",
                    )

    def generic(self, node: Any, path: str) -> None:
        """Fallback: report every object that names a resource, with a loud warning."""
        if isinstance(node, dict):
            if isinstance(node.get("resource_id"), str):
                self.emit(path, node, self.ctx.captured_at, layout="json.generic")
                self.issue(
                    "JSON_UNMAPPED_STRUCTURE",
                    "warning",
                    "unrecognised container; record kept with the source capture time",
                    path,
                )
                return
            for key, value in node.items():
                self.generic(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                self.generic(value, f"{path}[{index}]")


def parse_json(ctx: SourceContext, data: bytes) -> ParseOutput:
    def result(
        facts: list[RawFact], issues: list[Issue], status: ParseState, stats: dict[str, int]
    ) -> ParseOutput:
        return ParseOutput(PARSER_NAME, PARSER_VERSION, tuple(facts), tuple(issues), status, stats)

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        issue = Issue("JSON_NOT_UTF8", "error", "file is not valid UTF-8", ctx.source_id)
        return result([], [issue], "failed", {})
    duplicates: list[str] = []
    try:
        root = json.loads(text.lstrip("﻿"), object_pairs_hook=_pairs_hook(duplicates))
    except ValueError as exc:
        position = getattr(exc, "lineno", None)
        where = f"line {position}" if position else None
        issue = Issue("JSON_INVALID", "error", "file is not valid JSON", ctx.source_id, where)
        return result([], [issue], "failed", {})

    walker = _Walker(ctx, root)
    walker.run()
    issues = list(walker.issues)
    if duplicates:
        issues.append(
            Issue(
                "JSON_DUPLICATE_KEY",
                "warning",
                f"{len(duplicates)} duplicate object key(s); the last value was kept",
                ctx.source_id,
            )
        )
    if not walker.facts:
        issues.append(
            Issue(
                "JSON_NO_FACTS",
                "warning",
                "no records were recognised; this is not evidence that nothing is present",
                ctx.source_id,
            )
        )
    has_warning = any(i.severity in ("warning", "error") for i in issues)
    status: ParseState = "parsed" if walker.facts and not has_warning else "partial"
    stats = {"facts": len(walker.facts), "skipped": walker.skipped}
    return result(walker.facts, issues, status, stats)
