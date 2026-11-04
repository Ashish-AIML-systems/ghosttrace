"""Per-run composition with per-case failure isolation."""

from pathlib import Path

from slam.contracts import AuditRequest, CaseAnswer
from slam.ingestion import ingest
from slam.planning import plan
from slam.reconstruction import reconstruct
from slam.runtime.provider import ModelProvider


def run_cases(
    requests: tuple[AuditRequest, ...],
    dataset_dir: Path,
    *,
    cache_dir: Path | None = None,
    provider: ModelProvider | None = None,
) -> tuple[CaseAnswer, ...]:
    """Ingest once, then process every request independently in stable case order.

    A broken shared ingest is fatal because no case can be grounded without it. A
    reconstruction/planning error is isolated to that case and represented as a
    blocked answer, never as a guessed status that could be exported as complete.
    """
    case_ids = [request.case_id for request in requests]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("requests contain duplicate case_id values")

    bundle = ingest(dataset_dir, cache_dir=cache_dir, provider=provider)
    answers: list[CaseAnswer] = []
    for request in sorted(requests, key=lambda item: item.case_id):
        try:
            context = reconstruct(request, bundle, provider=provider)
            answer = plan(context)
            if answer.case_id != request.case_id:
                raise ValueError("planner returned an answer for a different case_id")
            answers.append(answer)
        except Exception as exc:  # isolate one malformed or unsupported case
            answers.append(
                CaseAnswer(
                    case_id=request.case_id,
                    ready_for_export=False,
                    blocking_issues=(f"case processing failed ({type(exc).__name__})",),
                )
            )
    return tuple(answers)
