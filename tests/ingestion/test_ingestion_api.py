"""End-to-end ingestion over a small synthetic dataset (no network, no API key)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ingestion_helpers import FakeOcr, make_pdf, make_png, ocr_of
from slam.contracts import EvidenceBundle, ParseStatus, SourceKind
from slam.ingestion import api
from slam.ingestion.api import RequestLoadError, ingest, ingest_with_ocr, load_requests
from slam.ingestion.parsers import json_parser
from slam.ingestion.parsers.image_parser import OcrResult
from slam.runtime.fake_provider import FakeModelProvider

LOOKUP_JSON = {
    "exported_at": "2026-09-01T00:00:00Z",
    "records": [
        {
            "system": "account_service",
            "resource_id": "account_9",
            "record_type": "USER_PROFILE",
            "result": "NOT_FOUND",
            "recorded_at": "2026-08-30T08:00:00Z",
            "subject_reference": "Ana.Rios@Example.com",
        }
    ],
}
LOG = (
    "2026-03-01T10:00:00Z level=INFO service=account_service trace_id=t1 resource_id=account_1 "
    "event=profile_lookup_completed rows=1 http_status=200 correlation_key=ana.rios@example.com\n"
)
SQL = (
    "-- Captured at: 2026-06-13T11:00:00Z\n"
    "-- Database topology: read_replica\n"
    "CREATE TABLE customer_data_primary (resource_id TEXT PRIMARY KEY, origin_system TEXT, "
    "collection_name TEXT, record_json TEXT CHECK (json_valid(record_json)), updated_at TEXT);\n"
    "CREATE TABLE customer_data_read_replica (resource_id TEXT PRIMARY KEY, origin_system TEXT, "
    "collection_name TEXT, record_json TEXT CHECK (json_valid(record_json)), updated_at TEXT);\n"
    "INSERT INTO customer_data_primary VALUES('account_1','account_service','customer_profiles',"
    '\'{"resource_id":"account_1","email":"ana.rios@example.com","account_status":"DELETED"}\','
    "'2026-06-01T00:00:00Z');\n"
    "INSERT INTO customer_data_read_replica VALUES('account_1','account_service',"
    "'customer_profiles',"
    '\'{"resource_id":"account_1","email":"ana.rios@example.com","account_status":"ACTIVE"}\','
    "'2026-05-01T00:00:00Z');\n"
)
TXT = (
    "SHIFT HANDOVER\nSnapshot: 2026-10-01T12:00:00Z\n\n"
    "2026-10-01T12:00:00Z | search_service | search_5 | SEARCH_INDEX_ENTRY | IDENTIFIABLE | "
    "ana.rios@example.com\n"
)
PDF = make_pdf([[(72, 700, "Event reference audit_record_003"), (72, 685, "subject user_03")]])
PNG = make_png()

MANIFEST = [
    "evidence_01,evidence/records/lookups.json,records_service,2026-09-01T00:00:00Z",
    "evidence_02,evidence/logs/service.log,observability,2026-03-02T00:00:00Z",
    "evidence_03,evidence/databases/snapshot.sql,db_capture,2026-06-13T12:00:00Z",
    "evidence_04,evidence/records/handover.txt,account_service,2026-10-01T12:00:00Z",
    "evidence_05,evidence/documents/journal.pdf,security_audit_service,2026-09-05T06:30:00Z",
    "evidence_06,evidence/images/console.png,backup_service,2026-04-29T02:00:00Z",
]
FILES = {
    "evidence/records/lookups.json": json.dumps(LOOKUP_JSON).encode(),
    "evidence/logs/service.log": LOG.encode(),
    "evidence/databases/snapshot.sql": SQL.encode(),
    "evidence/records/handover.txt": TXT.encode(),
    "evidence/documents/journal.pdf": PDF,
    "evidence/images/console.png": PNG,
}
ID_HEADER = "user_id,name,email,phone,email_hash,updated_at\n"
IDENTITIES = (
    ID_HEADER + "user_01,Ana Ríos,Ana.Rios@Example.com,+34 612 847 593,abc,2026-05-28T04:03:00Z\n"
)
REQUESTS = (
    "case_id,email,requested_at,reported_status,reported_at,audit_at,request_text\n"
    "case_2,ANA.RIOS@example.com,2026-08-18T09:14:00Z,COMPLETE,2026-08-20T16:42:00Z,"
    "2026-09-03T11:30:00Z,Please delete my account\n"
    "case_1,b@example.com,2026-08-18T09:14:00Z,NOT_STARTED,2026-08-20T16:42:00Z,"
    "2026-09-03T11:30:00Z,Hello\n"
)


def build(
    root: Path, *, manifest: list[str] | None = None, files: dict[str, bytes] | None = None
) -> Path:
    dataset = root / "dataset"
    dataset.mkdir(parents=True)
    rows = MANIFEST if manifest is None else manifest
    (dataset / "evidence_files.csv").write_text(
        "\n".join(["file_id,file_path,origin,captured_at", *rows]) + "\n", encoding="utf-8"
    )
    for rel, data in (FILES if files is None else files).items():
        target = dataset / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (dataset / "user_identities.csv").write_text(IDENTITIES, encoding="utf-8")
    (dataset / "user_audit_log.csv").write_text(
        "audit_id,user_id,event_time,field_name,old_value,new_value\n"
        "audit_01,user_01,2025-01-01T00:00:00Z,email,old@example.com,Ana.Rios@Example.com\n",
        encoding="utf-8",
    )
    (dataset / "system_activity.csv").write_text(
        "activity_id,event_time,event_type,source_system,target_system,resource_id,"
        "reported_result,details\n"
        "activity_01,2026-08-01T00:00:00Z,DELETE_RECORD,deletion_worker,account_service,"
        "account_1,SUCCESS,Deleted account_1\n",
        encoding="utf-8",
    )
    (dataset / "deletion_rules.csv").write_text(
        "rule_id,data_category,condition,required_action\nrule_01,USER_PROFILE,Always,DELETE\n",
        encoding="utf-8",
    )
    (dataset / "deletion_requests.csv").write_text(REQUESTS, encoding="utf-8")
    return dataset


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    return build(tmp_path)


def run(dataset: Path, **kw: object) -> EvidenceBundle:
    kw.setdefault("ocr", FakeOcr(ocr_of("backup_9287 areed1433@gmail.com")))
    return ingest_with_ocr(dataset, **kw)  # type: ignore[arg-type]


# --- coverage and structure ---------------------------------------------------------


def test_every_manifest_entry_is_accounted_for_and_parsed(dataset: Path) -> None:
    bundle = run(dataset)
    assert [s.source_id for s in bundle.sources] == [f"evidence_0{n}" for n in range(1, 7)]
    assert {s.parse_status for s in bundle.sources} == {ParseStatus.PARSED}
    assert {s.kind for s in bundle.sources} == set(SourceKind) - {SourceKind.CSV}
    errors = [i for i in bundle.issues if i.severity.value == "error"]
    assert errors == []


def test_source_records_carry_the_real_hash_and_manifest_time(dataset: Path) -> None:
    bundle = run(dataset)
    first = bundle.sources[0]
    assert first.sha256 == hashlib.sha256(FILES[first.path]).hexdigest()
    assert (
        first.captured_at == datetime(2026, 9, 1, tzinfo=UTC) and first.origin == "records_service"
    )
    assert first.extraction is not None and first.extraction.parser_name == "json"
    assert first.extraction.source_sha256 == first.sha256


def test_every_observation_cites_a_known_source_with_a_valid_span(dataset: Path) -> None:
    bundle = run(dataset)
    known = {s.source_id for s in bundle.sources}
    assert bundle.observations
    for obs in bundle.observations:
        assert obs.spans and all(span.source_id in known for span in obs.spans)
        assert obs.effective_time.utcoffset() is not None


def test_tabular_inputs_become_contract_rows(dataset: Path) -> None:
    bundle = run(dataset)
    (identity,) = bundle.current_identities
    assert (
        identity.email == "Ana.Rios@Example.com"
        and identity.email_normalized == "ana.rios@example.com"
    )
    assert identity.source_id == "user_01"
    (change,) = bundle.identity_changes
    assert (change.audit_id, change.old_value, change.new_value) == (
        "audit_01",
        "old@example.com",
        "Ana.Rios@Example.com",
    )
    (activity,) = bundle.activities
    assert (
        activity.system_id == "account_service"
        and activity.attributes["evidence_nature"] == "claim"
    )
    assert activity.attributes["source_system"] == "deletion_worker"
    assert [(r.rule_id, r.category) for r in bundle.policy_rules] == [("rule_01", "USER_PROFILE")]


def test_ingestion_produces_no_decision_or_plan(dataset: Path) -> None:
    dumped = run(dataset).model_dump_json()
    for forbidden in (
        "deletion_status",
        "steps_json",
        "REMEDIATION",
        "VERIFY_RECORD",
        "ready_for_export",
    ):
        assert forbidden not in dumped
    assert set(EvidenceBundle.model_fields) == {
        "contract_version",
        "sources",
        "current_identities",
        "identity_changes",
        "activities",
        "observations",
        "policy_rules",
        "issues",
    }


def test_conflicting_replicas_and_same_id_across_systems_stay_distinct(dataset: Path) -> None:
    bundle = run(dataset)
    copies = [
        o
        for o in bundle.observations
        if o.resource_id == "account_1" and o.source_kind is SourceKind.SQL
    ]
    assert {o.fields["container"] for o in copies} == {
        "customer_data_primary",
        "customer_data_read_replica",
    }
    assert {o.fields["source"]["account_status"] for o in copies} == {"DELETED", "ACTIVE"}
    assert len({o.observation_id for o in bundle.observations}) == len(bundle.observations)
    # the same id also appears in a log (account_service) - still its own observation
    assert any(
        o.source_kind is SourceKind.LOG and o.resource_id == "account_1"
        for o in bundle.observations
    )


def test_late_evidence_is_kept_with_its_real_time_for_downstream_cutoffs(dataset: Path) -> None:
    bundle = run(dataset)
    cutoff = datetime(2026, 9, 3, 11, 30, tzinfo=UTC)
    late = [o for o in bundle.observations if o.effective_time > cutoff]
    early = [o for o in bundle.observations if o.effective_time <= cutoff]
    assert late and early  # nothing was filtered out, both sides are present
    assert any(o.source_kind is SourceKind.TEXT for o in late)  # the 2026-10-01 handover
    assert all(s.captured_at.tzinfo is not None for s in bundle.sources)


def test_identifiers_are_matched_case_insensitively_without_losing_the_original(
    dataset: Path,
) -> None:
    bundle = run(dataset)
    lookup = next(o for o in bundle.observations if o.resource_id == "account_9")
    assert lookup.identifiers["email"] == "Ana.Rios@Example.com"
    assert "ana.rios@example.com" in lookup.subject_hints and lookup.observed_state == "NOT_FOUND"


# --- determinism and idempotency -------------------------------------------------------


def test_identical_input_gives_byte_identical_output(dataset: Path) -> None:
    assert run(dataset).model_dump_json() == run(dataset).model_dump_json()


def test_bundle_round_trips_through_json(dataset: Path) -> None:
    bundle = run(dataset)
    assert EvidenceBundle.model_validate_json(bundle.model_dump_json()) == bundle


def test_rerun_reuses_the_ledger_and_does_not_reparse(
    dataset: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    first = run(dataset, cache_dir=cache)

    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("an unchanged source must not be processed again")

    monkeypatch.setattr(api, "_process", forbidden)
    second = run(dataset, cache_dir=cache)
    assert second.model_dump_json() == first.model_dump_json()
    assert (cache / "ledger.sqlite").is_file()


def test_a_changed_source_is_reprocessed_and_replaces_its_old_rows(
    dataset: Path, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    before = run(dataset, cache_dir=cache)
    log = dataset / "evidence/logs/service.log"
    log.write_text(LOG.replace("account_1", "account_77"), encoding="utf-8")
    after = run(dataset, cache_dir=cache)
    assert any(o.resource_id == "account_77" for o in after.observations)
    log_obs = [o for o in after.observations if o.source_kind is SourceKind.LOG]
    assert all(o.resource_id != "account_1" for o in log_obs)
    assert len(after.observations) == len(before.observations)
    assert after.sources[1].sha256 != before.sources[1].sha256


def test_pipeline_fingerprint_changes_with_provider_and_model() -> None:
    base = api._fingerprint(None)
    fake = api._fingerprint(FakeModelProvider([]))
    other = api._fingerprint(FakeModelProvider([], model="another-model"))
    assert len({base, fake, other}) == 3


# --- failure is explicit and contained --------------------------------------------------


def test_a_crashing_parser_fails_only_its_own_source(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(*_: object) -> None:
        raise RuntimeError("secret internal detail jane@example.com")

    monkeypatch.setattr(json_parser, "parse_json", crash)
    bundle = run(dataset)
    statuses = {s.source_id: s.parse_status for s in bundle.sources}
    assert statuses["evidence_01"] is ParseStatus.FAILED
    assert all(v is ParseStatus.PARSED for k, v in statuses.items() if k != "evidence_01")
    crashed = [i for i in bundle.issues if i.code == "PARSER_CRASHED"]
    assert len(crashed) == 1 and crashed[0].severity.value == "error"
    assert "jane@example.com" not in crashed[0].message  # exception text is never echoed
    assert not [o for o in bundle.observations if o.resource_id == "account_9"]


def test_unrecognised_and_empty_files_are_failed_sources_with_issues(tmp_path: Path) -> None:
    files = {
        **FILES,
        "evidence/logs/service.log": b"\x00\xff\xfe",
        "evidence/records/handover.txt": b"",
    }
    bundle = run(build(tmp_path, files=files))
    by_id = {s.source_id: s for s in bundle.sources}
    assert by_id["evidence_02"].parse_status is ParseStatus.FAILED
    assert by_id["evidence_04"].parse_status is ParseStatus.FAILED
    codes = {(i.source_id, i.code) for i in bundle.issues}
    assert ("evidence_02", "FORMAT_UNRECOGNISED") in codes and (
        "evidence_04",
        "SOURCE_EMPTY",
    ) in codes


def test_unreadable_image_without_ocr_or_model_is_a_failed_source(dataset: Path) -> None:
    bundle = run(dataset, ocr=FakeOcr(OcrResult(available=False, error="NoBinary")))
    image = bundle.sources[5]
    assert image.parse_status is ParseStatus.FAILED
    assert {"OCR_ENGINE_UNAVAILABLE", "IMAGE_UNRESOLVED"} <= {
        i.code for i in bundle.issues if i.source_id == "evidence_06"
    }


def test_model_read_image_carries_model_provenance_and_is_marked_uncertain(
    dataset: Path, tmp_path: Path
) -> None:
    provider = FakeModelProvider(
        [{"records": [{"resource_id": "backup_9287", "emails": ["areed1433@gmail.com"]}]}]
    )
    bundle = run(
        dataset,
        ocr=FakeOcr(OcrResult(available=False, error="NoBinary")),
        provider=provider,
        cache_dir=tmp_path / "cache",
    )
    image = bundle.sources[5]
    assert image.parse_status is ParseStatus.PARTIAL
    assert image.extraction is not None and image.extraction.model == "fake-structured-v1"
    (obs,) = [o for o in bundle.observations if o.source_kind is SourceKind.IMAGE]
    assert (
        obs.fields["uncertain"] is True
        and obs.extraction is not None
        and obs.extraction.model_provider == "fake"
    )
    again = run(
        dataset,
        ocr=FakeOcr(OcrResult(available=False, error="NoBinary")),
        provider=FakeModelProvider([]),
        cache_dir=tmp_path / "cache",
    )
    assert again.model_dump_json() == bundle.model_dump_json()


def test_manifest_problems_become_issues_and_the_rest_still_loads(tmp_path: Path) -> None:
    manifest = [
        *MANIFEST,
        "evidence_07,../outside.txt,x,2026-01-01T00:00:00Z",
        "evidence_08,evidence/missing.log,x,bad",
    ]
    bundle = run(build(tmp_path, manifest=manifest))
    assert len(bundle.sources) == 6
    codes = [i.code for i in bundle.issues]
    assert (
        "PATH_TRAVERSAL" in codes
        and "SOURCE_NOT_FOUND" in codes
        and "MANIFEST_BAD_TIMESTAMP" in codes
    )


def test_a_missing_manifest_is_a_loud_failure_not_an_empty_bundle(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    bundle = ingest(empty)
    assert bundle.sources == () and bundle.observations == ()
    errors = {i.code for i in bundle.issues if i.severity.value == "error"}
    assert "CSV_NOT_FOUND" in errors


def test_a_bad_identity_row_is_reported_and_others_survive(tmp_path: Path) -> None:
    dataset = build(tmp_path)
    (dataset / "user_identities.csv").write_text(
        IDENTITIES + "user_02,Bo,bo@example.com,1,h,not-a-time\n", encoding="utf-8"
    )
    bundle = run(dataset)
    assert len(bundle.current_identities) == 1
    assert "TABLE_BAD_TIMESTAMP" in {i.code for i in bundle.issues}


def test_unlisted_evidence_files_are_reported_but_not_ingested(tmp_path: Path) -> None:
    files = {**FILES, "evidence/logs/stray.log": LOG.encode()}
    bundle = run(build(tmp_path, files=files))
    assert len(bundle.sources) == 6
    assert any(
        i.code == "SOURCE_NOT_IN_MANIFEST" and i.locator == "evidence/logs/stray.log"
        for i in bundle.issues
    )


# --- requests ----------------------------------------------------------------------------


def test_requests_load_in_file_order_with_original_email_case(dataset: Path) -> None:
    requests = load_requests(dataset)
    assert [r.case_id for r in requests] == ["case_2", "case_1"]
    assert requests[0].email == "ANA.RIOS@example.com"
    assert requests[0].audit_at == datetime(2026, 9, 3, 11, 30, tzinfo=UTC)


def test_a_bad_request_row_raises_instead_of_being_dropped(dataset: Path) -> None:
    (dataset / "deletion_requests.csv").write_text(
        REQUESTS
        + "case_3,c@example.com,yesterday,COMPLETE,2026-08-20T16:42:00Z,2026-09-03T11:30:00Z,x\n",
        encoding="utf-8",
    )
    with pytest.raises(RequestLoadError) as info:
        load_requests(dataset)
    assert any(i.code == "TABLE_BAD_TIMESTAMP" for i in info.value.issues)


def test_a_missing_requests_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RequestLoadError):
        load_requests(tmp_path)
