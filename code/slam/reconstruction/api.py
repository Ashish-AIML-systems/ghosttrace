"""Public reconstruction interface for Manya's deterministic subsystem."""

from datetime import datetime

from slam.contracts import AuditRequest, CaseContext, EvidenceBundle, GraphEdge, ResourceState
from slam.runtime.provider import ModelProvider

from .graph import build_dependency_graph
from .identity import resolve_identity
from .request_intent import interpret_request
from .timeline import reconstruct_timeline


def _cited_evidence_times(
    bundle: EvidenceBundle,
    audit_at: datetime,
    states: tuple[ResourceState, ...],
    edges: tuple[GraphEdge, ...],
    identity_evidence: tuple[str, ...],
) -> dict[str, datetime]:
    """Capture time of every participant-visible id this context cites, never after the cutoff.

    Contract 1.1.0 lets a planner check citations from the context alone. Only ids that exist
    at ``audit_at`` are included, so an id that is absent here cannot be cited.
    """

    times: dict[str, datetime] = {}
    times.update({s.source_id: s.captured_at for s in bundle.sources})
    times.update({a.activity_id: a.occurred_at for a in bundle.activities})
    times.update({c.audit_id: c.changed_at for c in bundle.identity_changes})
    cited = {
        *identity_evidence,
        *(
            i
            for state in states
            for i in (*state.supporting_evidence_ids, *state.conflicting_evidence_ids)
        ),
        *(i for edge in edges for i in edge.evidence_ids),
    }
    return {i: times[i] for i in sorted(cited) if i in times and times[i] <= audit_at}


def reconstruct(
    request: AuditRequest,
    bundle: EvidenceBundle,
    *,
    provider: ModelProvider | None = None,
) -> CaseContext:
    """Convert one request and evidence bundle into a grounded cutoff context."""

    intent = interpret_request(request.request_text, provider)
    identity = resolve_identity(request, bundle)

    if intent.intent.value == "NON_DELETION":
        coverage = (intent.provider_issue,) if intent.provider_issue else ()
        return CaseContext(
            request=request,
            request_intent=intent.intent,
            policy_rules=bundle.policy_rules,
            subject_id=identity.subject_id,
            identity_links=identity.links,
            evidence_captured_at=_cited_evidence_times(
                bundle,
                request.audit_at,
                (),
                (),
                tuple(i for link in identity.links for i in link.evidence_ids),
            ),
            coverage_issues=tuple(sorted(set((*identity.coverage_issues, *coverage)))),
            unresolved_conflicts=identity.conflicts,
        )

    timeline = reconstruct_timeline(
        request,
        bundle,
        identity.match_values,
        identity.subject_id,
    )
    graph = build_dependency_graph(
        request,
        bundle,
        timeline.eligible,
        timeline.states,
        identity.match_values,
        identity.subject_id,
    )
    provider_issues = (intent.provider_issue,) if intent.provider_issue else ()
    coverage = tuple(
        sorted(
            set(
                (
                    *identity.coverage_issues,
                    *timeline.coverage_issues,
                    *graph.coverage_issues,
                    *provider_issues,
                )
            )
        )
    )
    conflicts = tuple(
        sorted(set((*identity.conflicts, *timeline.conflicts, *graph.conflicts)))
    )
    return CaseContext(
        request=request,
        request_intent=intent.intent,
        policy_rules=bundle.policy_rules,
        subject_id=identity.subject_id,
        identity_links=identity.links,
        evidence_captured_at=_cited_evidence_times(
            bundle,
            request.audit_at,
            timeline.states,
            (*graph.active_flows, *graph.restore_risks),
            tuple(i for link in identity.links for i in link.evidence_ids),
        ),
        eligible_observation_ids=tuple(
            observation.observation_id for observation in timeline.eligible
        ),
        excluded_future_observation_ids=tuple(
            observation.observation_id for observation in timeline.excluded_future
        ),
        resource_states=timeline.states,
        active_flows=graph.active_flows,
        restore_risks=graph.restore_risks,
        coverage_issues=coverage,
        unresolved_conflicts=conflicts,
    )
