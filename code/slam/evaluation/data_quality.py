"""Evidence quality checks and transparent coverage proxies.

These diagnostics describe input coverage and contradictions. They are not
probabilities that an audit answer is correct and never change case decisions.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from slam.contracts import CaseContext, EvidenceBundle


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    code: str
    severity: str
    message: str
    source_ids: tuple[str, ...] = ()
    observation_ids: tuple[str, ...] = ()
    subject_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceQualityReport:
    expected_sources: int
    accounted_sources: int
    source_accounting_fraction: float
    parsed_sources: int
    partial_sources: int
    failed_sources: int
    parse_success_fraction: float
    observations: int
    observations_with_source_links: int
    observation_provenance_fraction: float
    duplicate_content_groups: int
    conflicting_observation_groups: int
    identity_collision_groups: int
    ingestion_issue_counts: dict[str, int]
    issues: tuple[DataQualityIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["issues"] = [asdict(issue) for issue in self.issues]
        return result


@dataclass(frozen=True, slots=True)
class CaseCoverageEstimate:
    case_id: str
    dimensions_checked: int
    dimensions_supported: int
    coverage_fraction: float
    supported_dimensions: tuple[str, ...]
    missing_or_uncertain_dimensions: tuple[str, ...]
    interpretation: str = "evidence coverage proxy; not probability of answer correctness"


def analyze_evidence_quality(
    bundle: EvidenceBundle,
    *,
    expected_source_ids: tuple[str, ...] | None = None,
) -> EvidenceQualityReport:
    """Summarize parse coverage and flag duplicate/conflicting evidence patterns."""

    sources_by_id: dict[str, list[Any]] = defaultdict(list)
    for source in bundle.sources:
        sources_by_id[source.source_id].append(source)

    expected_ids = (
        set(expected_source_ids)
        if expected_source_ids is not None
        else set(sources_by_id)
    )
    accounted_ids = set(sources_by_id) & expected_ids
    parsed = sum(
        1 for source_id in accounted_ids for source in sources_by_id[source_id]
        if source.parse_status.value == "parsed"
    )
    partial = sum(
        1 for source_id in accounted_ids for source in sources_by_id[source_id]
        if source.parse_status.value == "partial"
    )
    failed = sum(
        1 for source_id in accounted_ids for source in sources_by_id[source_id]
        if source.parse_status.value == "failed"
    )
    expected_count = len(expected_ids)
    source_accounting = len(accounted_ids) / expected_count if expected_count else 1.0
    parse_fraction = parsed / expected_count if expected_count else 1.0

    issues: list[DataQualityIssue] = []
    missing_ids = tuple(sorted(expected_ids - set(sources_by_id)))
    if missing_ids:
        issues.append(
            DataQualityIssue(
                code="MANIFEST_SOURCE_MISSING",
                severity="error",
                message=f"{len(missing_ids)} expected manifest source(s) have no SourceRecord",
                source_ids=missing_ids,
            )
        )
    repeated_source_ids = tuple(
        sorted(source_id for source_id, entries in sources_by_id.items() if len(entries) > 1)
    )
    if repeated_source_ids:
        issues.append(
            DataQualityIssue(
                code="DUPLICATE_SOURCE_ID",
                severity="error",
                message="A source_id is represented by multiple SourceRecord entries",
                source_ids=repeated_source_ids,
            )
        )

    content_groups: dict[str, list[str]] = defaultdict(list)
    for source in bundle.sources:
        content_groups[source.sha256].append(source.source_id)
    duplicate_groups = [
        tuple(sorted(ids)) for ids in content_groups.values() if len(set(ids)) > 1
    ]
    for ids in duplicate_groups:
        issues.append(
            DataQualityIssue(
                code="DUPLICATE_SOURCE_CONTENT",
                severity="warning",
                message="Different source IDs have identical source content hashes",
                source_ids=ids,
            )
        )

    resource_groups: dict[tuple[str, str, str, str], list[Any]] = defaultdict(list)
    for observation in bundle.observations:
        key = (
            observation.system_id,
            observation.resource_id,
            observation.category,
            observation.effective_time.isoformat(),
        )
        resource_groups[key].append(observation)
    conflict_groups = 0
    for _key, observations in resource_groups.items():
        states = {observation.observed_state for observation in observations}
        if len(states) > 1:
            conflict_groups += 1
            issues.append(
                DataQualityIssue(
                    code="CONFLICTING_RESOURCE_OBSERVATIONS",
                    severity="error",
                    message=(
                        "Same system/resource/category/time has multiple observed states: "
                        + ", ".join(sorted(states))
                    ),
                    source_ids=tuple(
                        sorted(
                            {
                                span.source_id
                                for observation in observations
                                for span in observation.spans
                            }
                        )
                    ),
                    observation_ids=tuple(
                        sorted(observation.observation_id for observation in observations)
                    ),
                )
            )

    identifier_owners: dict[tuple[str, str], set[str]] = defaultdict(set)
    for identity in bundle.current_identities:
        values = {
            "email": identity.email_normalized.strip().lower(),
            "phone": _normalize_phone(identity.phone),
            "email_hash": identity.email_hash.strip().lower(),
        }
        for kind, value in values.items():
            if value:
                identifier_owners[(kind, value)].add(identity.user_id)
    for change in bundle.identity_changes:
        if change.field_name.lower() not in {"email", "phone", "email_hash"}:
            continue
        for historical_value in (change.old_value, change.new_value):
            normalized = _normalize_identifier(change.field_name, historical_value)
            if normalized:
                identifier_owners[(change.field_name.lower(), normalized)].add(change.user_id)
    collisions = [
        (identifier, owners)
        for identifier, owners in identifier_owners.items()
        if len(owners) > 1
    ]
    for (kind, _value), owners in sorted(collisions):
        issues.append(
            DataQualityIssue(
                code="IDENTIFIER_LINKED_TO_MULTIPLE_USERS",
                severity="error",
                message=f"Normalized {kind} identifier is associated with multiple user IDs",
                subject_ids=tuple(sorted(owners)),
            )
        )

    observation_count = len(bundle.observations)
    linked_count = sum(
        1
        for observation in bundle.observations
        if observation.spans
        and all(span.source_id in sources_by_id for span in observation.spans)
    )
    provenance_fraction = linked_count / observation_count if observation_count else 1.0
    if linked_count < observation_count:
        issues.append(
            DataQualityIssue(
                code="OBSERVATION_SOURCE_UNRESOLVED",
                severity="error",
                message=(
                    f"{observation_count - linked_count} observation(s) have a span whose "
                    "source_id is absent from the source inventory"
                ),
                observation_ids=tuple(
                    sorted(
                        observation.observation_id
                        for observation in bundle.observations
                        if any(span.source_id not in sources_by_id for span in observation.spans)
                    )
                ),
            )
        )

    severity_counts = Counter(issue.severity.value for issue in bundle.issues)
    return EvidenceQualityReport(
        expected_sources=expected_count,
        accounted_sources=len(accounted_ids),
        source_accounting_fraction=source_accounting,
        parsed_sources=parsed,
        partial_sources=partial,
        failed_sources=failed,
        parse_success_fraction=parse_fraction,
        observations=observation_count,
        observations_with_source_links=linked_count,
        observation_provenance_fraction=provenance_fraction,
        duplicate_content_groups=len(duplicate_groups),
        conflicting_observation_groups=conflict_groups,
        identity_collision_groups=len(collisions),
        ingestion_issue_counts=dict(sorted(severity_counts.items())),
        issues=tuple(issues),
    )


def estimate_case_coverage(context: CaseContext) -> CaseCoverageEstimate:
    """Report explicit evidence/reconstruction coverage dimensions for a case.

    This is a transparent fraction of satisfied checks, not a calibrated
    probability, model confidence, or substitute for the planner's decision.
    """

    dimensions = {
        "request_intent_resolved": context.request_intent.value != "UNCLEAR",
        "subject_resolved": bool(context.subject_id),
        "eligible_observations_present": bool(context.eligible_observation_ids),
        "resource_states_present": bool(context.resource_states),
        "no_unresolved_conflicts": not context.unresolved_conflicts,
        "no_declared_coverage_gaps": not context.coverage_issues,
    }
    supported = tuple(name for name, value in dimensions.items() if value)
    missing = tuple(name for name, value in dimensions.items() if not value)
    total = len(dimensions)
    return CaseCoverageEstimate(
        case_id=context.request.case_id,
        dimensions_checked=total,
        dimensions_supported=len(supported),
        coverage_fraction=len(supported) / total if total else 1.0,
        supported_dimensions=supported,
        missing_or_uncertain_dimensions=missing,
    )


def _normalize_identifier(kind: str, value: str | None) -> str:
    if not value:
        return ""
    if kind.lower() == "phone":
        return _normalize_phone(value)
    return value.strip().lower()


def _normalize_phone(value: str) -> str:
    return "".join(character for character in value if character.isdigit())
