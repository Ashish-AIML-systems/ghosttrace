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
