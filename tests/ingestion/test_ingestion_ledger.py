from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ingestion_helpers import observation, source_record
from slam.contracts import IngestionIssue, IssueSeverity
from slam.ingestion.ledger import Ledger, LedgerError

FP = "f" * 64


def issue(code: str = "X") -> IngestionIssue:
    return IngestionIssue(
        severity=IssueSeverity.WARNING, code=code, message="m", source_id="evidence_01"
    )


def test_migration_is_idempotent_and_versioned(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    with Ledger(path) as first:
        version = first.schema_version
        first.migrate()
        first.migrate()
        assert first.schema_version == version >= 1
    with Ledger(path) as reopened:
        assert reopened.schema_version == version


def test_a_newer_schema_is_refused_not_downgraded(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    Ledger(path).close()
    db = sqlite3.connect(path)
    db.execute("PRAGMA user_version=99")
    db.close()
    with pytest.raises(LedgerError):
        Ledger(path)


def test_writing_the_same_source_version_twice_changes_nothing() -> None:
    with Ledger() as ledger:
        obs = [observation("account_1"), observation("account_2")]
        assert ledger.write_source(source_record(), FP, 0, obs, [issue()]) is True
        before = ledger.counts()
        assert ledger.write_source(source_record(), FP, 0, obs, [issue()]) is False
        assert (
            ledger.counts()
            == before
            == {
                "sources": 1,
                "observations": 2,
                "identifiers": 4,  # email + email_normalized for each of the two observations
                "issues": 1,
            }
        )


def test_round_trip_preserves_everything_in_order() -> None:
    with Ledger() as ledger:
        obs = [observation("account_2"), observation("account_1")]
        ledger.write_source(source_record(), FP, 0, obs, [issue("A"), issue("B")])
        record, found, issues = ledger.read_source("evidence_01", "a" * 64, FP) or (None, [], [])
        assert record == source_record()
        assert [o.resource_id for o in found] == ["account_2", "account_1"]
        assert found == obs
        assert [i.code for i in issues] == ["A", "B"]
        assert ledger.read_source("evidence_01", "b" * 64, FP) is None


def test_a_changed_source_replaces_its_old_version_atomically() -> None:
    with Ledger() as ledger:
        ledger.write_source(source_record(), FP, 0, [observation("account_1")], [issue()])
        new = source_record(sha256="b" * 64)
        ledger.write_source(new, FP, 0, [observation("account_9")], [])
        assert ledger.counts()["observations"] == 1 and ledger.counts()["issues"] == 0
        assert ledger.read_source("evidence_01", "a" * 64, FP) is None
        assert ledger.search("account_1") == []
        assert [o.resource_id for o in ledger.search("account_9")] == ["account_9"]


def test_a_changed_pipeline_fingerprint_replaces_too() -> None:
    with Ledger() as ledger:
        ledger.write_source(source_record(), "1" * 64, 0, [observation("account_1")], [])
        assert ledger.has_source("evidence_01", "a" * 64, "1" * 64)
        ledger.write_source(source_record(), "2" * 64, 0, [observation("account_1")], [])
        assert not ledger.has_source("evidence_01", "a" * 64, "1" * 64)
        assert ledger.counts()["sources"] == 1


def test_a_failed_write_rolls_everything_back() -> None:
    with Ledger() as ledger:
        shared = observation("account_1")
        ledger.write_source(source_record("evidence_01"), FP, 0, [shared], [])
        before = ledger.counts()
        with pytest.raises(sqlite3.IntegrityError):  # same observation id from another source
            ledger.write_source(source_record("evidence_02"), FP, 1, [shared], [issue()])
        assert ledger.counts() == before
        assert ledger.read_source("evidence_01", "a" * 64, FP) is not None


def test_lookup_by_identifier_ignores_case() -> None:
    with Ledger() as ledger:
        ledger.write_source(source_record(), FP, 0, [observation("account_1")], [])
        assert len(ledger.find_by_identifier("ANA@example.COM")) == 1
        assert ledger.find_by_identifier("nobody@example.com") == []


def test_same_resource_id_in_two_systems_is_never_merged() -> None:
    with Ledger() as ledger:
        a = observation("account_1", system_id="account_service")
        b = observation("account_1", system_id="search_service")
        ledger.write_source(source_record(), FP, 0, [a, b], [])
        assert [o.system_id for o in ledger.find_by_resource("account_service", "account_1")] == [
            "account_service"
        ]
        assert [o.system_id for o in ledger.find_by_resource("search_service", "account_1")] == [
            "search_service"
        ]


def test_results_come_back_in_effective_time_order() -> None:
    with Ledger() as ledger:
        late = observation("account_1", effective_time=datetime(2026, 9, 5, tzinfo=UTC))
        early = observation("account_1", effective_time=datetime(2026, 9, 1, tzinfo=UTC))
        ledger.write_source(source_record(), FP, 0, [late, early], [])
        found = ledger.find_by_resource("account_service", "account_1")
        assert [o.effective_time.day for o in found] == [1, 5]


def test_full_text_search_covers_ids_identifiers_and_record_text() -> None:
    with Ledger() as ledger:
        ledger.write_source(source_record(), FP, 0, [observation("account_7")], [])
        for query in ("account_7", "ana@example.com", "hello ledger", "ledger hello"):
            assert [o.resource_id for o in ledger.search(query)] == ["account_7"], query
        assert ledger.search("absent-term") == []
        assert ledger.search("") == [] and ledger.search("   ") == []


@pytest.mark.parametrize(
    "hostile",
    [
        '"',
        'a" OR "b',
        "NEAR(a b)",
        "*",
        "a AND NOT b",
        "col:hello",
        "(((",
        "a -b",
        "'; DROP TABLE x; --",
    ],
)
def test_search_text_can_never_be_parsed_as_fts_syntax(hostile: str) -> None:
    with Ledger() as ledger:
        ledger.write_source(source_record(), FP, 0, [observation("account_1")], [])
        ledger.search(hostile)  # must not raise
        assert ledger.counts()["observations"] == 1


def test_search_limit_is_applied() -> None:
    with Ledger() as ledger:
        many = [observation(f"account_{n}", data={"note": "shared words"}) for n in range(5)]
        ledger.write_source(source_record(), FP, 0, many, [])
        assert len(ledger.search("shared", limit=3)) == 3


def test_a_file_ledger_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "ledger.sqlite"
    with Ledger(path) as ledger:
        ledger.write_source(source_record(), FP, 0, [observation("account_1")], [issue()])
    with Ledger(path) as reopened:
        assert reopened.has_source("evidence_01", "a" * 64, FP)
        assert reopened.counts()["observations"] == 1
