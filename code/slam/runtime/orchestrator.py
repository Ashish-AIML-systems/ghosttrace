"""Thin integration flow that never fabricates results for missing modules."""

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
    """Compose teammate APIs; unresolved modules fail explicitly."""

    bundle = ingest(dataset_dir, cache_dir=cache_dir, provider=provider)
    return tuple(plan(reconstruct(request, bundle, provider=provider)) for request in requests)
