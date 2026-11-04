from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from slam.ingestion.extraction_cache import ExtractionCache

KEY = hashlib.sha256(b"k").hexdigest()
PAYLOAD = {"extraction": {"records": []}, "metadata": {"model": "m"}}


def test_in_memory_round_trip_and_counters() -> None:
    cache = ExtractionCache()
    assert cache.get(KEY) is None
    cache.put(KEY, PAYLOAD)
    assert cache.get(KEY) == PAYLOAD
    assert (cache.hits, cache.misses) == (1, 1)


def test_file_cache_survives_a_new_instance(tmp_path: Path) -> None:
    ExtractionCache(tmp_path).put(KEY, PAYLOAD)
    assert ExtractionCache(tmp_path).get(KEY) == PAYLOAD
    stored = list((tmp_path / "extractions").rglob("*.json"))
    assert len(stored) == 1 and stored[0].parent.name == KEY[:2]


@pytest.mark.parametrize("key", ["", "abc", "Z" * 64, KEY.upper(), KEY + "0"])
def test_malformed_keys_are_refused(key: str) -> None:
    cache = ExtractionCache()
    with pytest.raises(ValueError):
        cache.get(key)
    with pytest.raises(ValueError):
        cache.put(key, PAYLOAD)


def _entry(tmp_path: Path) -> Path:
    ExtractionCache(tmp_path).put(KEY, PAYLOAD)
    return next((tmp_path / "extractions").rglob("*.json"))


@pytest.mark.parametrize(
    "damage",
    ["not json at all", "[]", '{"key": "x"}', ""],
)
def test_unreadable_entries_are_a_miss_never_a_result(tmp_path: Path, damage: str) -> None:
    _entry(tmp_path).write_text(damage, encoding="utf-8")
    cache = ExtractionCache(tmp_path)
    assert cache.get(KEY) is None and cache.corrupt == 1 and cache.misses == 1


def test_tampered_payload_fails_its_integrity_check(tmp_path: Path) -> None:
    path = _entry(tmp_path)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["metadata"]["model"] = "tampered"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    cache = ExtractionCache(tmp_path)
    assert cache.get(KEY) is None and cache.corrupt == 1


def test_an_entry_filed_under_the_wrong_key_is_rejected(tmp_path: Path) -> None:
    path = _entry(tmp_path)
    other = hashlib.sha256(b"other").hexdigest()
    target = tmp_path / "extractions" / other[:2] / f"{other}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(path.read_bytes())
    assert ExtractionCache(tmp_path).get(other) is None


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path: Path) -> None:
    ExtractionCache(tmp_path).put(KEY, PAYLOAD)
    assert not list((tmp_path / "extractions").rglob("*.tmp"))


def test_failed_write_cleans_up_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_: object, **__: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        ExtractionCache(tmp_path).put(KEY, PAYLOAD)
    monkeypatch.undo()
    assert not list(tmp_path.rglob("*.tmp")) and ExtractionCache(tmp_path).get(KEY) is None


def test_stored_entries_contain_only_the_payload(tmp_path: Path) -> None:
    text = _entry(tmp_path).read_text(encoding="utf-8")
    assert set(json.loads(text)) == {"key", "payload_sha256", "payload"}
