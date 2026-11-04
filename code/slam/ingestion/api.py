"""Frozen ingestion interface; implementation is owned by Ashish."""

from pathlib import Path

from slam.contracts import EvidenceBundle
from slam.runtime.provider import ModelProvider


def ingest(
    dataset_dir: Path,
    *,
    cache_dir: Path | None = None,
    provider: ModelProvider | None = None,
) -> EvidenceBundle:
    del dataset_dir, cache_dir, provider
    raise NotImplementedError("evidence ingestion is owned by Ashish")
