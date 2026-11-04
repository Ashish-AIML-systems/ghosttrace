"""Content-addressed cache for validated model extraction payloads.

Key construction belongs to the runtime (``build_model_cache_key``); this module
only decides when ingestion reads and writes. Entries hold the validated
structured payload and call metadata, never API keys, prompts containing
credentials, or image bytes. Each entry carries a digest of its payload; a
corrupt or tampered entry is treated as a miss, never as a result.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_KEY = re.compile(r"^[0-9a-f]{64}$")


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExtractionCache:
    """File-backed when given a directory, otherwise in-memory for the run."""

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = None if directory is None else Path(directory) / "extractions"
        self._memory: dict[str, dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0
        self.corrupt = 0

    def _path(self, key: str) -> Path | None:
        if self._dir is None:
            return None
        return self._dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        if not _KEY.match(key):
            raise ValueError("cache key must be a 64-character lowercase hex digest")
        path = self._path(key)
        found = self._memory.get(key) if path is None else self._read(path, key)
        if found is None:
            self.misses += 1
        else:
            self.hits += 1
        return found

    def _read(self, path: Path, key: str) -> dict[str, Any] | None:
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            payload = envelope["payload"]
            if envelope["key"] != key or envelope["payload_sha256"] != _digest(payload):
                raise ValueError("integrity check failed")
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError):
            self.corrupt += 1
            return None
        return payload if isinstance(payload, dict) else None

    def put(self, key: str, payload: dict[str, Any]) -> None:
        if not _KEY.match(key):
            raise ValueError("cache key must be a 64-character lowercase hex digest")
        path = self._path(key)
        if path is None:
            self._memory[key] = payload
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {"key": key, "payload_sha256": _digest(payload), "payload": payload}
        handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(
                    envelope, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                )
            os.replace(temp_name, path)  # atomic: readers never see a partial file
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
