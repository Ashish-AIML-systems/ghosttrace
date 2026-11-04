import pytest
from slam.contracts import CONTRACT_MODELS, ContractModel

TS = "2026-01-01T00:00:00Z"
SHA = "a" * 64

SAMPLES: dict[str, dict[str, object]] = {
    "AuditRequest": {
        "case_id": "case-1",
        "email": "Person@Example.test",
        "requested_at": TS,
        "reported_status": "COMPLETE",
        "reported_at": TS,
        "audit_at": TS,
        "request_text": "delete",
    },
    "SourceRecord": {
        "source_id": "file-1",
        "kind": "json",
        "origin": "support",
        "path": "evidence/records/a.json",
        "captured_at": TS,
        "sha256": SHA,
        "parse_status": "parsed",
    },
    "SourceSpan": {"source_id": "file-1", "json_path": "$.record", "quote": "short"},
    "TableRowLocator": {"table": "users", "row": 1},
    "LineRangeLocator": {"start": 1, "end": 2},
    "PdfPositionLocator": {"page": 1, "x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0},
    "ImageRegionLocator": {"x": 0, "y": 0, "width": 10, "height": 10},
    "ExtractionProvenance": {
        "parser_name": "json",
        "parser_version": "1",
        "source_sha256": SHA,
    },
    "Observation": {
        "observation_id": SHA,
        "subject_hints": ["Person@Example.test"],
        "system_id": "support",
        "resource_id": "ticket-1",
        "category": "SUPPORT_RECORD",
        "observed_state": "PRESENT",
        "effective_time": TS,
        "source_kind": "json",
        "spans": [{"source_id": "file-1", "json_path": "$.record"}],
    },
    "CurrentIdentity": {
        "user_id": "user-1",
        "name": "Person",
        "email": "Person@Example.test",
        "email_normalized": "person@example.test",
        "phone": "+10000000000",
        "email_hash": SHA,
        "updated_at": TS,
        "source_id": "identity-row-1",
    },
    "IdentityChangeEvent": {
        "audit_id": "audit-1",
        "user_id": "user-1",
        "field_name": "email",
        "old_value": "old@example.test",
        "new_value": "Person@Example.test",
        "changed_at": TS,
        "source_id": "identity-audit",
    },
    "Activity": {
        "activity_id": "activity-1",
        "activity_type": "DELETE",
        "occurred_at": TS,
    },
    "PolicyRule": {
        "rule_id": "rule-1",
        "category": "SUPPORT_RECORD",
        "required_action": "REDACT",
    },
    "IngestionIssue": {
        "severity": "warning",
        "code": "OCR_LOW_CONFIDENCE",
        "message": "manual review required",
        "source_id": "file-1",
        "locator": "page=1",
    },
    "EvidenceBundle": {"contract_version": "1.0.0"},
    "IdentityLink": {
        "left_identifier": "old@example.test",
        "right_identifier": "person@example.test",
        "relationship": "email_change",
        "evidence_ids": ["audit-1"],
        "confidence": "EXACT",
    },
    "ResourceState": {
        "system_id": "support",
        "resource_id": "ticket-1",
        "category": "SUPPORT_RECORD",
        "state": "PRESENT",
        "at": TS,
    },
    "GraphEdge": {
        "source": "primary",
        "target": "replica",
        "relationship": "replicates_to",
        "evidence_ids": ["activity-1"],
        "active": True,
    },
    "CaseContext": {
        "request": {
            "case_id": "case-1",
            "email": "person@example.test",
            "requested_at": TS,
            "reported_status": "COMPLETE",
            "reported_at": TS,
            "audit_at": TS,
            "request_text": "delete",
        },
        "request_intent": "DELETION",
    },
    "Step": {
        "step_no": 1,
        "phase": "VERIFICATION",
        "system_id": "support",
        "resource_id": "ticket-1",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
        "evidence_id": "file-1",
    },
    "CaseAnswer": {
        "case_id": "case-1",
        "deletion_status": "NOT_APPLICABLE",
        "ready_for_export": True,
    },
}


@pytest.mark.parametrize("model", CONTRACT_MODELS, ids=lambda model: model.__name__)
def test_every_exported_contract_round_trips(model: type[ContractModel]) -> None:
    assert model.__name__ in SAMPLES, f"missing canonical sample for {model.__name__}"
    value = model.model_validate(SAMPLES[model.__name__])
    assert model.model_validate_json(value.model_dump_json()) == value


def test_sample_map_matches_exported_contracts() -> None:
    assert set(SAMPLES) == {model.__name__ for model in CONTRACT_MODELS}
