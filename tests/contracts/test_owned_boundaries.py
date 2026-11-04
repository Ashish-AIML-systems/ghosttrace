import inspect
from pathlib import Path

import pytest
from slam.contracts import AuditRequest, EvidenceBundle
from slam.ingestion import ingest
from slam.planning import plan
from slam.reconstruction import reconstruct


def test_frozen_signatures_are_available() -> None:
    assert tuple(inspect.signature(ingest).parameters) == ("dataset_dir", "cache_dir", "provider")
    assert tuple(inspect.signature(reconstruct).parameters) == ("request", "bundle", "provider")
    assert tuple(inspect.signature(plan).parameters) == ("context",)


def test_unimplemented_owner_module_fails_explicitly() -> None:
    with pytest.raises(NotImplementedError, match="Ashish"):
        ingest(Path("dataset"))


def test_reconstruction_stub_does_not_fabricate_context() -> None:
    request = AuditRequest.model_validate_json(
        '{"case_id":"c","email":"x@y.test","requested_at":"2026-01-01T00:00:00Z",'
        '"reported_status":"COMPLETE","reported_at":"2026-01-01T00:00:00Z",'
        '"audit_at":"2026-01-02T00:00:00Z","request_text":"delete"}'
    )
    with pytest.raises(NotImplementedError, match="Manya"):
        reconstruct(request, EvidenceBundle())
