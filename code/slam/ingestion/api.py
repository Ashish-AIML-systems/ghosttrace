"""Frozen ingestion interface; implementation is owned by Ashish."""

from pathlib import Path

from slam.contracts import AuditRequest, EvidenceBundle
from slam.runtime.provider import ModelProvider


def ingest(
    dataset_dir: Path,
    *,
    cache_dir: Path | None = None,
    provider: ModelProvider | None = None,
) -> EvidenceBundle:
    del dataset_dir, cache_dir, provider
    raise NotImplementedError("evidence ingestion is owned by Ashish")


def load_requests(dataset_dir: Path) -> tuple[AuditRequest, ...]:
    """Load requests separately; EvidenceBundle intentionally excludes requests."""

    del dataset_dir
    raise NotImplementedError("request loading is owned by Ashish")
