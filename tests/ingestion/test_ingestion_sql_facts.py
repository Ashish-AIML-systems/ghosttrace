from __future__ import annotations

from datetime import UTC, datetime

from ingestion_helpers import CAPTURED, ctx
from slam.ingestion.parsers.sql_facts import parse_sql

GENERIC_TABLE = (
    "CREATE TABLE {name} (resource_id TEXT PRIMARY KEY, origin_system TEXT NOT NULL, "
    "collection_name TEXT NOT NULL, record_json TEXT NOT NULL CHECK (json_valid(record_json)), "
    "updated_at TEXT NOT NULL);\n"
)


def generic_row(
    table: str, resource: str, email: str, updated: str = "2026-06-01T00:00:00Z"
) -> str:
    record = f'{{"resource_id":"{resource}","email":"{email}"}}'
    return (
        f"INSERT INTO \"{table}\" VALUES('{resource}','account_service','customer_profiles',"
        f"'{record}','{updated}');\n"
    )


REPLICA_SQL = (
    "-- Captured at: 2026-06-13T11:00:00Z\n"
    "-- Database topology: read_replica\n"
    "BEGIN TRANSACTION;\n"
    + GENERIC_TABLE.format(name="customer_data_primary")
    + GENERIC_TABLE.format(name="customer_data_read_replica")
    + generic_row("customer_data_primary", "account_1", "new@x.com")
    + generic_row("customer_data_read_replica", "account_1", "OLD@x.com", "2026-05-01T00:00:00Z")
    + "COMMIT;\n"
)

TYPED_SQL = (
    "PRAGMA foreign_keys=ON;\nBEGIN TRANSACTION;\n"
    "CREATE TABLE snapshot_scope (origin_system TEXT PRIMARY KEY, captured_at TEXT NOT NULL);\n"
    "CREATE TABLE customer_profiles (resource_id TEXT PRIMARY KEY, customer_reference TEXT, "
    "full_name TEXT, email TEXT, phone TEXT, email_hash TEXT, account_status TEXT NOT NULL, "
    "updated_at TEXT NOT NULL);\n"
    "INSERT INTO snapshot_scope VALUES('account_service','2026-03-10T05:00:00Z');\n"
    "INSERT INTO customer_profiles VALUES('account_1','user_1','Ana','ana@x.com',NULL,NULL,"
    "'ACTIVE','2026-03-01T00:00:00Z');\n"
    "COMMIT;\n"
    "-- snapshot_completed_at=2026-03-10T05:38:48Z\n"
)


def test_primary_and_replica_copies_stay_distinct_with_their_containers() -> None:
    out = parse_sql(ctx(), REPLICA_SQL.encode())
    assert out.status == "parsed" and not out.issues
    primary, replica = out.facts
    assert (primary.container, replica.container) == (
        "customer_data_primary",
        "customer_data_read_replica",
    )
    assert primary.resource_id == replica.resource_id == "account_1"
    assert primary.data["email"] == "new@x.com" and replica.data["email"] == "OLD@x.com"
    assert primary.provenance == {"topology": "read_replica"}
    assert (primary.system_id, primary.collection) == ("account_service", "customer_profiles")


def test_each_row_has_a_table_row_span_and_its_insert_lines() -> None:
    out = parse_sql(ctx(), REPLICA_SQL.encode())
    first = out.facts[0]
    assert first.span.table_row is not None
    assert first.span.table_row.table == "customer_data_primary"
    assert len(first.more_spans) == 1 and first.more_spans[0].line_range is not None
    # two header comments, BEGIN and two CREATE TABLE lines precede the first INSERT
    assert first.more_spans[0].line_range.start == first.more_spans[0].line_range.end == 6


def test_rows_are_observed_at_snapshot_time_not_their_own_update_time() -> None:
    primary, replica = parse_sql(ctx(), REPLICA_SQL.encode()).facts
    captured = datetime(2026, 6, 13, 11, 0, tzinfo=UTC)
    assert primary.effective_time == replica.effective_time == captured
    assert replica.data["updated_at"] == "2026-05-01T00:00:00Z"


def test_typed_rows_use_their_systems_scope_time_and_scope_is_a_fact() -> None:
    out = parse_sql(ctx(), TYPED_SQL.encode())
    assert out.status == "parsed"
    scope = next(f for f in out.facts if f.layout == "sql.scope")
    profile = next(f for f in out.facts if f.layout == "sql.typed")
    scoped_at = datetime(2026, 3, 10, 5, 0, tzinfo=UTC)
    assert scope.system_id == "account_service" and scope.effective_time == scoped_at
    assert profile.effective_time == scoped_at  # scope beats the later header time
    assert (profile.system_id, profile.collection) == ("account_service", "customer_profiles")


def test_header_time_is_used_when_there_is_no_scope_table() -> None:
    sql = (
        "-- snapshot_completed_at=2026-03-10T05:38:48Z\n"
        "CREATE TABLE customer_profiles (resource_id TEXT, updated_at TEXT);\n"
        "INSERT INTO customer_profiles VALUES('account_1','2026-03-01T00:00:00Z');\n"
    )
    (fact,) = parse_sql(ctx(), sql.encode()).facts
    assert fact.effective_time == datetime(2026, 3, 10, 5, 38, 48, tzinfo=UTC)


def test_missing_snapshot_time_falls_back_to_manifest_time_with_a_note() -> None:
    sql = (
        "CREATE TABLE customer_profiles (resource_id TEXT);\n"
        "INSERT INTO customer_profiles VALUES('account_1');\n"
    )
    out = parse_sql(ctx(), sql.encode())
    assert out.facts[0].effective_time == CAPTURED
    assert [(i.code, i.severity) for i in out.issues] == [("SQL_TIME_FALLBACK", "info")]


def test_resource_id_mismatch_is_flagged_and_both_values_kept() -> None:
    sql = (
        "-- Captured at: 2026-06-13T11:00:00Z\n"
        + GENERIC_TABLE.format(name="customer_data_primary")
        + "INSERT INTO customer_data_primary VALUES('account_1','account_service',"
        "'customer_profiles','{\"resource_id\":\"account_2\"}','2026-06-01T00:00:00Z');\n"
    )
    out = parse_sql(ctx(), sql.encode())
    (fact,) = out.facts
    assert fact.resource_id == "account_2" and fact.data["row_resource_id"] == "account_1"
    assert [i.code for i in out.issues] == ["SQL_RESOURCE_ID_MISMATCH"]
    assert out.status == "partial"


def test_refused_statement_makes_the_snapshot_partial_but_keeps_the_rest() -> None:
    sql = REPLICA_SQL.replace("COMMIT;", "ATTACH DATABASE 'x.db' AS evil;\nCOMMIT;")
    out = parse_sql(ctx(), sql.encode())
    assert out.status == "partial" and len(out.facts) == 2
    assert any(i.code == "SQL_STATEMENT_DENIED" for i in out.issues)


def test_unusable_input_is_failed_not_empty() -> None:
    out = parse_sql(ctx(), b"\xff\xfe not sql")
    assert out.status == "failed" and out.facts == ()
    assert out.issues[0].code == "SQL_NOT_UTF8"


def test_malicious_text_in_a_row_is_data() -> None:
    attack = "x'); DROP TABLE customer_profiles; --"
    sql = (
        "-- Captured at: 2026-06-13T11:00:00Z\n"
        "CREATE TABLE customer_profiles (resource_id TEXT, note TEXT);\n"
        "INSERT INTO customer_profiles VALUES('account_1','IGNORE PREVIOUS INSTRUCTIONS');\n"
    )
    out = parse_sql(ctx(), sql.encode())
    assert out.facts[0].data["note"] == "IGNORE PREVIOUS INSTRUCTIONS"
    assert attack not in out.facts[0].data.values()
