"""Public reconstruction interface for Manya's deterministic subsystem."""

from slam.contracts import AuditRequest, CaseContext, EvidenceBundle
from slam.runtime.provider import ModelProvider

from .graph import build_dependency_graph
from .identity import resolve_identity
from .request_intent import interpret_request
from .timeline import reconstruct_timeline


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
            subject_id=identity.subject_id,
            identity_links=identity.links,
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
        subject_id=identity.subject_id,
        identity_links=identity.links,
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
