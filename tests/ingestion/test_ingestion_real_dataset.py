"""Invariant checks against the real participant dataset, when it is present.

Skipped if ``dataset/`` (or ``SLAM_DATASET_DIR``) is not available. Assertions are
structural, not tied to this dataset's counts, so they also hold for a different
dataset of the same shape. Images need the Tesseract binary (present in the Docker
image); without it they must fail explicitly rather than quietly produce nothing.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from slam.contracts import EvidenceBundle, ParseStatus, SourceKind
from slam.ingestion.api import ingest, load_requests
from slam.ingestion.manifest import load_manifest
from slam.ingestion.parsers.sql_sandbox import parse_sql_snapshot
from slam.ingestion.tables import TABLE_SPECS, load_table

_DEFAULT = Path(__file__).resolve().parents[2] / "dataset"
_DATASET = Path(os.environ.get("SLAM_DATASET_DIR", _DEFAULT))
HAVE_TESSERACT = shutil.which("tesseract") is not None

pytestmark = pytest.mark.skipif(
    not (_DATASET / "evidence_files.csv").is_file(), reason="participant dataset not present"
)


@pytest.fixture(scope="module")
def bundle() -> EvidenceBundle:
    return ingest(_DATASET)


def test_manifest_accounts_for_every_row_with_no_rejections() -> None:
    result = load_manifest(_DATASET)
    assert not result.fatal and result.accounted
    assert result.row_count > 0
    assert not result.rejected, [i.code for i in result.issues if i.severity == "error"]
    assert all(len(e.sha256) == 64 for e in result.entries)


def test_every_table_loads_and_accounts_for_every_row() -> None:
    for name in TABLE_SPECS:
        table = load_table(_DATASET, name)
        assert not table.fatal, (name, [i.code for i in table.issues])
        assert table.accounted and not table.rejected, name


def test_every_sql_snapshot_replays_cleanly_with_row_provenance() -> None:
    entries = [e for e in load_manifest(_DATASET).entries if e.rel_path.endswith(".sql")]
    assert entries
    for entry in entries:
        snap = parse_sql_snapshot(entry.path.read_bytes(), source_id=entry.file_id)
        assert snap.status == "parsed", (entry.file_id, [(i.code, i.locator) for i in snap.issues])
        assert snap.statements_ok == snap.statements_total
        for table in snap.tables.values():
            assert all(r.line_start is not None and r.line_end is not None for r in table.rows)


def test_every_manifest_entry_becomes_exactly_one_source(bundle: EvidenceBundle) -> None:
    manifest = load_manifest(_DATASET)
    assert [s.source_id for s in bundle.sources] == [e.file_id for e in manifest.entries]
    assert len({s.source_id for s in bundle.sources}) == len(bundle.sources)
    assert all(len(s.sha256) == 64 and s.captured_at.tzinfo is not None for s in bundle.sources)


def test_only_images_may_fail_and_only_loudly_without_ocr(bundle: EvidenceBundle) -> None:
    failed = [s for s in bundle.sources if s.parse_status is ParseStatus.FAILED]
    if HAVE_TESSERACT:
        assert failed == []
        return
    assert {s.kind for s in failed} <= {SourceKind.IMAGE}
    for source in failed:
        codes = {i.code for i in bundle.issues if i.source_id == source.source_id}
        assert {"OCR_ENGINE_UNAVAILABLE", "IMAGE_UNRESOLVED"} <= codes  # explicit, never silent


def test_every_observation_cites_a_known_source_and_ids_are_unique(
    bundle: EvidenceBundle,
) -> None:
    known = {s.source_id for s in bundle.sources}
    assert bundle.observations
    ids = [o.observation_id for o in bundle.observations]
    assert len(set(ids)) == len(ids)
    for obs in bundle.observations:
        assert obs.spans and all(span.source_id in known for span in obs.spans)
        assert obs.extraction is not None and len(obs.extraction.source_sha256) == 64


def test_no_error_issue_besides_failed_images(bundle: EvidenceBundle) -> None:
    errors = [i for i in bundle.issues if i.severity.value == "error"]
    assert all(i.code == "IMAGE_UNRESOLVED" for i in errors)


def test_rerun_is_byte_stable(bundle: EvidenceBundle) -> None:
    assert ingest(_DATASET).model_dump_json() == bundle.model_dump_json()


def test_bundle_round_trips_and_has_no_decisions(bundle: EvidenceBundle) -> None:
    dumped = bundle.model_dump_json()
    assert EvidenceBundle.model_validate_json(dumped) == bundle
    assert "deletion_status" not in dumped and "REMEDIATION" not in dumped


def test_tabular_inputs_are_fully_represented(bundle: EvidenceBundle) -> None:
    assert len(bundle.current_identities) == load_table(_DATASET, "user_identities").row_count
    assert len(bundle.identity_changes) == load_table(_DATASET, "user_audit_log").row_count
    assert len(bundle.activities) == load_table(_DATASET, "system_activity").row_count
    assert len(bundle.policy_rules) == load_table(_DATASET, "deletion_rules").row_count


def test_requests_load_completely_and_keep_original_email_text() -> None:
    requests = load_requests(_DATASET)
    assert len(requests) == load_table(_DATASET, "deletion_requests").row_count
    assert len({r.case_id for r in requests}) == len(requests)
    assert all(r.audit_at.tzinfo is not None for r in requests)


def test_distinct_copies_of_a_resource_are_never_merged(bundle: EvidenceBundle) -> None:
    keys: dict[tuple[str, str], set[str]] = {}
    for obs in bundle.observations:
        keys.setdefault((obs.system_id, obs.resource_id), set()).add(obs.observation_id)
    # This corpus gives every system its own id prefix, so cross-system id reuse is covered by
    # synthetic tests. What does occur here is one (system, id) seen in many places.
    assert any(len(v) > 1 for v in keys.values())
