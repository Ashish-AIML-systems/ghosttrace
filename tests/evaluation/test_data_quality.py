from datetime import UTC, datetime

from slam.contracts import (
    AuditRequest,
    CaseContext,
    CurrentIdentity,
    EvidenceBundle,
    IdentityChangeEvent,
    Observation,
    RequestIntent,
    SourceRecord,
    SourceSpan,
)
from slam.evaluation.data_quality import analyze_evidence_quality, estimate_case_coverage

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
OBS_A = "c" * 64
OBS_B = "d" * 64


def source(source_id: str, sha256: str = SHA_A, parse_status: str = "parsed") -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        kind="json",
        origin="test",
        path=f"evidence/{source_id}.json",
        captured_at=NOW,
        sha256=sha256,
        parse_status=parse_status,
    )


def observation(observation_id: str, state: str, source_id: str) -> Observation:
    return Observation(
        observation_id=observation_id,
        system_id="accounts",
        resource_id="r-1",
        category="PROFILE",
        observed_state=state,
        effective_time=NOW,
        source_kind="json",
        spans=(SourceSpan(source_id=source_id, json_path="$.record"),),
    )


def test_quality_report_finds_missing_and_duplicate_sources_conflicts_and_identity_collisions():
    bundle = EvidenceBundle(
        sources=(source("s1"), source("s2", SHA_A, "partial"), source("s3", SHA_B, "failed")),
        current_identities=(
            CurrentIdentity(
                user_id="u1",
                name="A",
                email="same@example.test",
                email_normalized="same@example.test",
                phone="+1 (222)",
                email_hash=SHA_A,
                updated_at=NOW,
                source_id="s1",
            ),
            CurrentIdentity(
                user_id="u2",
                name="B",
                email="same@example.test",
                email_normalized="same@example.test",
                phone="1222",
                email_hash=SHA_A,
                updated_at=NOW,
                source_id="s1",
            ),
        ),
        identity_changes=(
            IdentityChangeEvent(
                audit_id="a1",
                user_id="u3",
                field_name="email",
                old_value="same@example.test",
                changed_at=NOW,
                source_id="s1",
            ),
        ),
        observations=(
            observation(OBS_A, "PRESENT", "s1"),
            observation(OBS_B, "ABSENT", "s1"),
        ),
    )

    report = analyze_evidence_quality(bundle, expected_source_ids=("s1", "s2", "missing"))

    assert report.expected_sources == 3
    assert report.accounted_sources == 2
    assert report.source_accounting_fraction == 2 / 3
    assert report.parsed_sources == 1
    assert report.partial_sources == 1
    assert report.failed_sources == 0
    assert report.duplicate_content_groups == 1
    assert report.conflicting_observation_groups == 1
    assert report.identity_collision_groups >= 1
    assert {issue.code for issue in report.issues} >= {
        "MANIFEST_SOURCE_MISSING",
        "DUPLICATE_SOURCE_CONTENT",
        "CONFLICTING_RESOURCE_OBSERVATIONS",
        "IDENTIFIER_LINKED_TO_MULTIPLE_USERS",
    }


def test_quality_report_detects_unresolved_observation_provenance():
    bundle = EvidenceBundle(
        sources=(source("s1"),),
        observations=(observation(OBS_A, "PRESENT", "not-in-source-inventory"),),
    )
    report = analyze_evidence_quality(bundle)
    assert report.observation_provenance_fraction == 0.0
    assert any(issue.code == "OBSERVATION_SOURCE_UNRESOLVED" for issue in report.issues)


def test_case_coverage_is_an_explicit_proxy_not_probability():
    request = AuditRequest(
        case_id="case_1",
        email="a@example.test",
        requested_at=NOW,
        reported_status="COMPLETE",
        reported_at=NOW,
        audit_at=NOW,
        request_text="delete my account",
    )
    context = CaseContext(
        request=request,
        request_intent=RequestIntent.DELETION,
        subject_id="u1",
        eligible_observation_ids=(OBS_A,),
        coverage_issues=("some parser failed",),
    )
    estimate = estimate_case_coverage(context)
    assert estimate.dimensions_checked == 6
    assert estimate.dimensions_supported == 4
    assert estimate.coverage_fraction == 4 / 6
    assert "no_declared_coverage_gaps" in estimate.missing_or_uncertain_dimensions
    assert estimate.interpretation.startswith("evidence coverage proxy")
