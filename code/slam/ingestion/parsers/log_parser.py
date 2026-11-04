"""Log parser.

Six timestamp-prefixed layouts are recognised from line content, not from the
file name: JSON-after-timestamp, bracketed, RFC5424-style syslog, cloud-runtime
(``requestId=... message="..."``), pipe-delimited, and plain ``key=value``. All
reduce to one entry shape (time, level, service, trace, event, attributes).

An entry becomes a fact only when it names a resource and is not a ``*_started``
event. ``*_started`` entries are not facts, but their subject keys are joined to
the later entries of the same trace so a result can be tied to the person it
was looked up for. Entries that name no resource are counted as uninterpreted
operational events and are never treated as evidence of anything.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..issues import Issue
from ..timeutil import parse_utc
from ..vocab import SUBJECT_KEY_FIELDS
from .base import ParseOutput, ParseState, RawFact, SourceContext, line_span, quote_of

PARSER_NAME = "log"
PARSER_VERSION = "1.0.0"

_KV = re.compile(r'([A-Za-z_][A-Za-z0-9_.\-]*)=("(?:[^"\\]|\\.)*"|\S+)')
_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z)\s+(.*)$")
_BRACKETED = re.compile(
    r"^\[(\w+)\]\s+\[([\w.\-]+)\]\s+\[([\w.\-]+)\]\s+([A-Za-z_][\w]*):?\s*(.*)$"
)
_SYSLOG = re.compile(r"^<\d+>\d\s+\S+\s+(\S+)\s+(\S+)\s+-\s+-\s+(.*)$")
_LEVEL_WORD = re.compile(r"^(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s+(.*)$")
_EVENT_WORD = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_LEVELS = {"TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL"}


@dataclass(frozen=True, slots=True)
class LogEntry:
    line_no: int
    when: datetime
    layout: str
    level: str | None
    service: str | None
    trace: str | None
    event: str | None
    attrs: dict[str, str]
    raw: str


def _kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in _KV.findall(text):
        if value.startswith('"'):
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        out[key] = value
    return out


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _entry_from_json(rest: str) -> tuple[str, dict[str, str]] | None:
    try:
        loaded = json.loads(rest)
    except ValueError:
        return None
    if not isinstance(loaded, dict):
        return None
    return "json", {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in loaded.items()}


def _pipe_entry(rest: str) -> tuple[str, dict[str, str]] | None:
    """``LEVEL | service | [trace |] event | key=value ...`` with a variable column count."""
    parts = [p.strip() for p in rest.lstrip("| ").split(" | ")]
    if len(parts) < 3 or parts[0] not in _LEVELS:
        return None
    attrs = _kv(parts[-1]) if "=" in parts[-1] else {}
    middle = parts[1:-1] if attrs else parts[1:]
    event = next((p for p in reversed(middle) if _EVENT_WORD.match(p) and "-" not in p), None)
    if event is None or not middle:
        return None
    attrs["level"] = parts[0]
    attrs["service"] = middle[0]
    attrs["event"] = event
    extras = [p for p in middle[1:] if p != event]
    if extras:
        attrs.setdefault("trace_id", extras[0])
    return "pipe", attrs


def parse_line(line_no: int, line: str) -> LogEntry | None:
    match = _TS.match(line)
    if match is None:
        return None
    try:
        when = parse_utc(match.group(1))
    except ValueError:
        return None
    rest = match.group(2).strip()
    layout = "kv"
    attrs: dict[str, str]
    if rest.startswith("{"):
        parsed = _entry_from_json(rest)
        if parsed is None:
            return None
        layout, attrs = parsed
        attrs.setdefault("level", attrs.get("severity", ""))
        attrs.setdefault("service", attrs.get("logger", ""))
    elif (bracket := _BRACKETED.match(rest)) is not None:
        layout = "bracketed"
        attrs = _kv(bracket.group(5))
        attrs.update(
            level=bracket.group(1),
            service=bracket.group(2),
            trace_id=bracket.group(3),
            event=bracket.group(4),
        )
    elif (sys_match := _SYSLOG.match(rest)) is not None:
        layout = "syslog"
        attrs = _kv(sys_match.group(3))
        attrs["service"] = sys_match.group(1)
        attrs["trace_id"] = sys_match.group(2)
    elif rest.startswith("requestId="):
        layout = "cloud"
        outer = _kv(rest)
        attrs = _kv(outer.get("message", ""))
        attrs["level"] = outer.get("level", "")
        attrs["service"] = outer.get("function", "")
        attrs["trace_id"] = outer.get("requestId", "")
    elif rest.startswith("|") and (pipe := _pipe_entry(rest)) is not None:
        layout, attrs = pipe
    else:
        word = _LEVEL_WORD.match(rest)
        body = word.group(2) if word else rest
        attrs = _kv(body)
        if word:
            attrs.setdefault("level", word.group(1))
        if "=" not in body:
            return None
    attrs = {k: v for k, v in attrs.items() if v != ""}
    return LogEntry(
        line_no=line_no,
        when=when,
        layout=layout,
        level=_str(attrs.get("level")),
        service=_str(attrs.get("service")),
        trace=_str(attrs.get("trace_id")),
        event=_str(attrs.get("event")),
        attrs=attrs,
        raw=line,
    )


def _subject_values(attrs: dict[str, str]) -> tuple[str, ...]:
    return tuple(attrs[k] for k in sorted(SUBJECT_KEY_FIELDS) if k in attrs)


def parse_log(ctx: SourceContext, data: bytes) -> ParseOutput:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        issue = Issue("LOG_NOT_UTF8", "error", "file is not valid UTF-8", ctx.source_id)
        return ParseOutput(PARSER_NAME, PARSER_VERSION, (), (issue,), "failed")

    entries: list[LogEntry] = []
    unparsed: list[int] = []
    for number, line in enumerate(text.lstrip("﻿").split("\n"), start=1):
        if not line.strip():
            continue
        entry = parse_line(number, line.rstrip("\r"))
        if entry is None:
            unparsed.append(number)
        else:
            entries.append(entry)

    subjects: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        if entry.trace:
            for value in _subject_values(entry.attrs):
                if value not in subjects[entry.trace]:
                    subjects[entry.trace].append(value)

    facts: list[RawFact] = []
    uninterpreted: Counter[str] = Counter()
    for entry in entries:
        resource = entry.attrs.get("resource_id")
        is_start = bool(entry.event and entry.event.endswith("_started"))
        if not resource or is_start:
            uninterpreted[entry.event or "(none)"] += 1
            continue
        own = _subject_values(entry.attrs)
        joined = tuple(dict.fromkeys((*own, *subjects.get(entry.trace or "", ()))))
        system = entry.attrs.get("system") or entry.service
        facts.append(
            RawFact(
                layout=f"log.{entry.layout}",
                effective_time=entry.when,
                span=line_span(ctx.source_id, entry.line_no, quote=quote_of(entry.raw)),
                data={k: v for k, v in entry.attrs.items()},
                system_id=system,
                resource_id=resource,
                collection=entry.attrs.get("record_type"),
                state=entry.attrs.get("result") if entry.event == "record_lookup" else None,
                subject_keys=joined,
            )
        )

    issues: list[Issue] = []
    if unparsed:
        shown = ", ".join(str(n) for n in unparsed[:5])
        more = "" if len(unparsed) <= 5 else f" (+{len(unparsed) - 5} more)"
        issues.append(
            Issue(
                "LOG_LINES_UNPARSED",
                "warning",
                f"{len(unparsed)} line(s) did not match any known log layout: {shown}{more}",
                ctx.source_id,
                f"line {unparsed[0]}",
            )
        )
    skipped = sum(uninterpreted.values())
    if skipped:
        issues.append(
            Issue(
                "LOG_EVENTS_NOT_INTERPRETED",
                "info",
                f"{skipped} entr(ies) named no resource or were lookup starts; not turned into "
                "observations (operational noise carries no record state)",
                ctx.source_id,
            )
        )
    if not entries:
        issues.append(
            Issue(
                "LOG_NO_ENTRIES",
                "warning",
                "no log entries recognised; this is not evidence that nothing is present",
                ctx.source_id,
            )
        )
    status: ParseState = "parsed" if entries and not unparsed else "partial"
    if not entries and not unparsed:
        status = "partial"
    stats = {
        "lines": len(entries) + len(unparsed),
        "entries": len(entries),
        "facts": len(facts),
        "unparsed_lines": len(unparsed),
        "uninterpreted_events": sum(uninterpreted.values()),
    }
    return ParseOutput(PARSER_NAME, PARSER_VERSION, tuple(facts), tuple(issues), status, stats)
