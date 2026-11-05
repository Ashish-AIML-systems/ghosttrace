"""Content-addressed keys; storage policy is deliberately separate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def build_cache_key(*, namespace: str, parts: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 over an explicit namespace and JSON-safe parts."""

    payload = json.dumps(
        {"namespace": namespace, "parts": parts},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_model_cache_key(
    *,
    source_sha256: str,
    prompt_version: str,
    schema_version: str,
    provider: str,
    model: str,
    settings: Mapping[str, Any],
) -> str:
    """Canonical extraction-cache key owned by runtime and consumed by ingestion."""

    return build_cache_key(
        namespace="model-extraction-v1",
        parts={
            "source_sha256": source_sha256,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "provider": provider,
            "model": model,
            "settings": settings,
        },
    )
