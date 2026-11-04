"""Frozen reconstruction interface; implementation is owned by Manya."""

from slam.contracts import AuditRequest, CaseContext, EvidenceBundle
from slam.runtime.provider import ModelProvider


def reconstruct(
    request: AuditRequest,
    bundle: EvidenceBundle,
    *,
    provider: ModelProvider | None = None,
) -> CaseContext:
    del request, bundle, provider
    raise NotImplementedError("identity reconstruction is owned by Manya")
