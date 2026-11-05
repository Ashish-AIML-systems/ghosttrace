from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from slam.ingestion.tables import TABLE_SPECS, load_table

IDENTITY_HEADER = "user_id,name,email,phone,email_hash,updated_at"


def _write(root: Path, name: str, text: str) -> Path:
    root.mkdir(exist_ok=True)
    (root / TABLE_SPECS[name].filename).write_text(text, encoding="utf-8", newline="")
    return root


def test_identities_keep_values_verbatim_with_line_numbers(tmp_path: Path) -> None:
    root = _write(
        tmp_path,
        "user_identities",
        f"{IDENTITY_HEADER}\n"
        "user_01,Ana Ríos,ANA.Rios@Example.COM,+34 612 847 593,abc,2026-05-28T04:03:00Z\n"
        "user_02,Bo,bo@example.com,,def,2026-05-29T04:03:00+01:00\n",
    )
    table = load_table(root, "user_identities")
    assert not table.fatal and table.accounted and not table.rejected
    first, second = table.rows
    assert first.values["email"] == "ANA.Rios@Example.COM"  # never case-folded or trimmed
    assert first.values["name"] == "Ana Ríos"
    assert (first.line_start, first.line_end) == (2, 2)
    assert second.values["phone"] == ""
    assert first.times["updated_at"] == datetime(2026, 5, 28, 4, 3, tzinfo=UTC)
    assert second.times["updated_at"] == datetime(2026, 5, 29, 3, 3, tzinfo=UTC)


def test_multiline_quoted_field_reports_full_line_range(tmp_path: Path) -> None:
    root = _write(
        tmp_path,
        "deletion_requests",
        "case_id,email,requested_at,reported_status,reported_at,audit_at,request_text\n"
        "case_01,a@x.com,2026-01-01T00:00:00Z,COMPLETE,2026-01-02T00:00:00Z,"
        '2026-01-03T00:00:00Z,"line one\nline two"\n'
        "case_02,b@x.com,2026-01-01T00:00:00Z,COMPLETE,2026-01-02T00:00:00Z,2026-01-03T00:00:00Z,ok\n",
    )
    first, second = load_table(root, "deletion_requests").rows
    assert (first.line_start, first.line_end) == (2, 3)
    assert first.values["request_text"] == "line one\nline two"
    assert (second.line_start, second.line_end) == (4, 4)


def test_bad_rows_are_rejected_explicitly_and_accounted(tmp_path: Path) -> None:
    root = _write(
        tmp_path,
        "user_identities",
        f"{IDENTITY_HEADER}\n"
        "user_01,A,a@x.com,1,h,2026-05-28T04:03:00Z\n"
        "user_01,A2,a2@x.com,1,h,2026-05-28T04:03:00Z\n"  # duplicate id (both rejected)
        "user_03,C,c@x.com,1,h,yesterday\n"  # bad time
        "user_04,D,d@x.com\n"  # short row
        ",E,e@x.com,1,h,2026-05-28T04:03:00Z\n"  # empty id
        "user_06,F,f@x.com,1,h,2026-05-28T04:03:00Z\n",
    )
    table = load_table(root, "user_identities")
    assert [r.row_id for r in table.rows] == ["user_06"]
    codes = {i.code for i in table.issues}
    assert codes == {
        "TABLE_DUPLICATE_ID",
        "TABLE_BAD_TIMESTAMP",
        "TABLE_ROW_MALFORMED",
        "TABLE_ID_EMPTY",
    }
    assert table.accounted and table.row_count == 6
    assert all("a@x.com" not in i.message for i in table.issues)


def test_missing_column_or_file_is_fatal(tmp_path: Path) -> None:
    root = _write(tmp_path, "user_identities", "user_id,name\nuser_01,A\n")
    bad = load_table(root, "user_identities")
    assert bad.fatal and not bad.rows and bad.issues[0].code == "CSV_MISSING_COLUMNS"
    missing = load_table(tmp_path / "other", "user_audit_log")
    assert missing.fatal and missing.issues[0].code == "CSV_NOT_FOUND"


def test_empty_table_is_not_the_same_as_a_failed_table(tmp_path: Path) -> None:
    root = _write(tmp_path, "deletion_rules", "rule_id,data_category,condition,required_action\n")
    ok = load_table(root, "deletion_rules")
    assert not ok.fatal and ok.row_count == 0 and ok.accounted


def test_unknown_table_name_is_a_programming_error(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        load_table(tmp_path, "no_such_table")


def test_every_spec_is_internally_consistent() -> None:
    for spec in TABLE_SPECS.values():
        assert spec.id_column in spec.columns
        assert set(spec.timestamp_columns) <= set(spec.columns)
        assert len(set(spec.columns)) == len(spec.columns)
