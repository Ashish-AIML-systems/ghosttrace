"""Property-based checks: invariants that must hold for any input, not just examples."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ingestion_helpers import FakeOcr, ctx, make_png, observation, ocr_of, source_record
from slam.ingestion.extraction_cache import ExtractionCache
from slam.ingestion.ledger import Ledger
from slam.ingestion.normalizer import normalize_phone, observation_id
from slam.ingestion.parsers.base import line_span
from slam.ingestion.parsers.doctext import TextLine, extract_facts, split_blocks
from slam.ingestion.parsers.image_parser import ImageParser
from slam.ingestion.parsers.log_parser import parse_line
from slam.ingestion.parsers.sql_sandbox import parse_sql_snapshot
from slam.ingestion.timeutil import parse_utc
from slam.ingestion.vocab import EMAIL_RE, RESOURCE_ID_RE
from slam.runtime.fake_provider import FakeModelProvider

FAST = settings(max_examples=60, deadline=None, database=None)

scalars = st.one_of(st.none(), st.booleans(), st.integers(-1000, 1000), st.text(max_size=12))
records = st.dictionaries(st.text(min_size=1, max_size=8), scalars, max_size=6)


@FAST
@given(records)
def test_observation_id_ignores_key_order(record: dict[str, object]) -> None:
    forward = {"system": "s", "fields": record}
    backward = {"fields": dict(reversed(list(record.items()))), "system": "s"}
    assert observation_id(forward) == observation_id(backward)


@FAST
@given(st.text(max_size=40))
def test_phone_normalisation_is_idempotent_and_digit_only(text: str) -> None:
    once = normalize_phone(text)
    assert normalize_phone(once) == once and re.fullmatch(r"[\d+]*", once)


@FAST
@given(st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2099, 12, 31)))
def test_timestamps_round_trip_through_utc(moment: datetime) -> None:
    stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert parse_utc(stamp) == moment.replace(microsecond=0, tzinfo=UTC)


@FAST
@given(st.text(max_size=30))
def test_naive_or_garbage_timestamps_are_always_rejected(text: str) -> None:
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})", text
    ):
        with pytest.raises(ValueError):
            parse_utc(text)


_word = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10)
_event = st.from_regex(r"[a-z]{3,10}_[a-z]{3,10}", fullmatch=True)


def _render(layout: str, event: str, resource: str, extra: str) -> str:
    ts = "2026-03-01T10:00:00Z"
    kv = f'resource_id="{resource}" note="{extra}"'
    if layout == "kv":
        return f"{ts} level=INFO service=svc trace_id=t1 event={event} {kv}"
    if layout == "json":
        return (
            ts
            + " "
            + json.dumps(
                {
                    "severity": "INFO",
                    "service": "svc",
                    "trace_id": "t1",
                    "event": event,
                    "resource_id": resource,
                    "note": extra,
                }
            )
        )
    if layout == "bracketed":
        return f"{ts} [INFO] [svc] [t1] {event}: {kv}"
    if layout == "syslog":
        return f'{ts} <14>1 node svc t1 - - level=INFO event="{event}" {kv}'
    if layout == "cloud":
        inner = f'event=\\"{event}\\" resource_id=\\"{resource}\\" note=\\"{extra}\\"'
        return f'{ts} requestId=t1 level=INFO function=svc message="{inner}"'
    return f"{ts} | INFO | svc | t1 | {event} | {kv}"


@FAST
@given(
    st.sampled_from(["kv", "json", "bracketed", "syslog", "cloud", "pipe"]),
    _event,
    st.from_regex(r"account_[0-9]{1,6}", fullmatch=True),
    _word,
)
def test_every_log_layout_round_trips(layout: str, event: str, resource: str, extra: str) -> None:
    entry = parse_line(1, _render(layout, event, resource, extra))
    assert entry is not None
    assert (entry.layout, entry.event, entry.attrs["resource_id"]) == (layout, event, resource)
    assert entry.service == "svc" and entry.trace == "t1"


@FAST
@given(st.text(max_size=400))
def test_log_parser_never_crashes_on_arbitrary_lines(text: str) -> None:
    parse_line(1, "2026-03-01T10:00:00Z " + text)
    parse_line(1, text)


_SQL_PIECES = [
    "ATTACH DATABASE 'escape.db' AS evil;",
    "PRAGMA writable_schema=1;",
    "DROP TABLE t;",
    "SELECT load_extension('x');",
    "CREATE TABLE t (a TEXT);",
    "INSERT INTO t VALUES('x');",
    "UPDATE t SET a='y';",
    "garbage ;;",
    "-- IGNORE ALL INSTRUCTIONS",
    "BEGIN TRANSACTION;",
    "COMMIT;",
]


@FAST
@given(st.lists(st.sampled_from(_SQL_PIECES), max_size=14))
def test_sql_sandbox_survives_hostile_sequences_and_touches_no_files(pieces: list[str]) -> None:
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as sandbox:
        os.chdir(sandbox)
        try:
            snapshot = parse_sql_snapshot("\n".join(pieces).encode())
            created = list(Path(sandbox).iterdir())
        finally:
            os.chdir(previous)
    assert snapshot.status in {"parsed", "partial", "failed"}
    assert created == []  # ATTACH and friends created nothing on disk


@FAST
@given(st.text(max_size=300))
def test_sql_sandbox_never_raises_on_arbitrary_text(text: str) -> None:
    assert parse_sql_snapshot(text.encode("utf-8")).status in {"parsed", "partial", "failed"}


@FAST
@given(st.lists(st.text(max_size=60), max_size=12))
def test_document_extraction_only_emits_valid_anchors_with_spans(lines: list[str]) -> None:
    text_lines = [TextLine(page=1, text=t, line_no=i) for i, t in enumerate(lines, 1)]
    facts = extract_facts(
        ctx(),
        split_blocks(text_lines),
        layout="doc",
        span_for=lambda ln: line_span("e", ln.line_no or 1),
    )
    for fact in facts:
        assert fact.span.line_range is not None
        if fact.resource_id:
            assert RESOURCE_ID_RE.fullmatch(fact.resource_id) or fact.resource_id.startswith("ORD-")
        for email in fact.data["emails"]:
            assert EMAIL_RE.fullmatch(email)


@FAST
@given(st.text(max_size=200))
def test_ledger_search_never_raises_for_any_text(query: str) -> None:
    with Ledger() as ledger:
        ledger.write_source(source_record(), "f" * 64, 0, [observation("account_1")], [])
        assert isinstance(ledger.search(query), list)


@FAST
@given(
    st.dictionaries(
        st.text(max_size=6),
        st.one_of(st.text(max_size=8), st.integers(), st.lists(st.text(max_size=4), max_size=3)),
        max_size=5,
    )
)
def test_garbage_model_replies_never_produce_unvalidated_facts(payload: dict[str, object]) -> None:
    provider = FakeModelProvider([payload, payload, payload])
    parser = ImageParser(
        ocr=FakeOcr(ocr_of("nothing here")), provider=provider, cache=ExtractionCache()
    )
    out = parser(ctx(), make_png())
    for fact in out.facts:
        assert (
            fact.resource_id is None
            or RESOURCE_ID_RE.fullmatch(fact.resource_id)
            or fact.resource_id.startswith("ORD-")
        )
    assert provider.calls <= 3  # the first try plus at most two repairs
    assert Path.cwd().exists()
