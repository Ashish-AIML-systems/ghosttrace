from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from slam.ingestion.issues import Issue
from slam.ingestion.manifest import load_manifest

MakeDataset = Callable[..., Path]


def _codes(issues: Iterable[Issue]) -> set[str]:
    return {i.code for i in issues}


def test_happy_path_hashes_and_utc_times(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        [
            "evidence_01,evidence/a.log,svc_a,2026-03-01T10:00:00Z",
            "evidence_02,evidence/b.json,svc_b,2026-03-02T11:30:00+02:00",
        ],
        {"evidence/a.log": b"hello", "evidence/b.json": b"{}"},
    )
    result = load_manifest(root)
    assert not result.fatal and result.accounted and not result.rejected
    first, second = result.entries
    assert first.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert first.size_bytes == 5
    assert first.captured_at == datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    assert second.captured_at == datetime(2026, 3, 2, 9, 30, tzinfo=UTC)
    assert second.captured_at.utcoffset() == timedelta(0)
    assert first.path.is_file() and first.line_no == 2


def test_missing_file_is_rejected_others_still_load(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        [
            "evidence_01,evidence/a.log,svc,2026-03-01T10:00:00Z",
            "evidence_02,evidence/gone.log,svc,2026-03-01T10:00:00Z",
        ],
        {"evidence/a.log": b"x"},
    )
    result = load_manifest(root)
    assert [e.file_id for e in result.entries] == ["evidence_01"]
    assert [r.file_id for r in result.rejected] == ["evidence_02"]
    assert "SOURCE_NOT_FOUND" in _codes(result.issues)
    assert result.accounted


@pytest.mark.parametrize(
    ("bad_path", "code"),
    [
        ("../outside.txt", "PATH_TRAVERSAL"),
        ("/etc/passwd", "PATH_ABSOLUTE"),
        ("evidence\\a.log", "PATH_BACKSLASH"),
        ("C:/Windows/win.ini", "PATH_ABSOLUTE"),
    ],
)
def test_unsafe_paths_are_rejected_and_recorded(
    make_dataset: MakeDataset, tmp_path: Path, bad_path: str, code: str
) -> None:
    (tmp_path / "outside.txt").write_text("must never be read")
    root = make_dataset(
        [
            f"evidence_01,{bad_path},svc,2026-03-01T10:00:00Z",
            "evidence_02,evidence/a.log,svc,2026-03-01T10:00:00Z",
        ],
        {"evidence/a.log": b"ok"},
    )
    result = load_manifest(root)
    assert [e.file_id for e in result.entries] == ["evidence_02"]
    assert code in _codes(result.rejected[0].issues)
    assert result.rejected[0].issues[0].locator == "evidence_files.csv:2"


def test_symlink_escaping_the_dataset_is_rejected(
    make_dataset: MakeDataset, tmp_path: Path, dir_link: Callable[[Path, Path], None]
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    root = make_dataset(
        ["evidence_01,evidence/link/secret.txt,svc,2026-03-01T10:00:00Z"], {"evidence/.keep": b""}
    )
    dir_link(root / "evidence" / "link", outside)
    result = load_manifest(root)
    assert not result.entries
    assert "PATH_ESCAPES_ROOT" in _codes(result.issues)


def test_duplicate_ids_reject_every_occurrence(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        [
            "evidence_01,evidence/a.log,svc,2026-03-01T10:00:00Z",
            "evidence_01,evidence/b.log,svc,2026-03-01T10:00:00Z",
            "evidence_02,evidence/c.log,svc,2026-03-01T10:00:00Z",
        ],
        {"evidence/a.log": b"a", "evidence/b.log": b"b", "evidence/c.log": b"c"},
    )
    result = load_manifest(root)
    assert [e.file_id for e in result.entries] == ["evidence_02"]
    assert len(result.rejected) == 2
    assert all("MANIFEST_DUPLICATE_ID" in _codes(r.issues) for r in result.rejected)
    assert result.accounted


@pytest.mark.parametrize(
    "stamp", ["2026-03-01", "2026-03-01 10:00:00", "2026-03-01T10:00:00", "not-a-time", ""]
)
def test_bad_or_naive_timestamps_are_rejected(make_dataset: MakeDataset, stamp: str) -> None:
    root = make_dataset([f"evidence_01,evidence/a.log,svc,{stamp}"], {"evidence/a.log": b"x"})
    result = load_manifest(root)
    assert not result.entries
    assert "MANIFEST_BAD_TIMESTAMP" in _codes(result.issues)


def test_missing_required_column_is_fatal_not_empty(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        ["evidence_01,evidence/a.log,2026-03-01T10:00:00Z"],
        {"evidence/a.log": b"x"},
        header="file_id,file_path,captured_at",
    )
    result = load_manifest(root)
    assert result.fatal and not result.entries
    assert "CSV_MISSING_COLUMNS" in _codes(result.issues)


def test_missing_manifest_and_missing_dataset_are_fatal(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert "CSV_NOT_FOUND" in _codes(load_manifest(empty).issues)
    assert load_manifest(empty).fatal
    assert "DATASET_NOT_FOUND" in _codes(load_manifest(tmp_path / "nope").issues)


def test_malformed_row_is_rejected_not_guessed(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        [
            "evidence_01,evidence/a.log,svc,2026-03-01T10:00:00Z,EXTRA",
            "evidence_02,evidence/b.log,svc,2026-03-01T10:00:00Z",
        ],
        {"evidence/a.log": b"a", "evidence/b.log": b"b"},
    )
    result = load_manifest(root)
    assert "MANIFEST_ROW_MALFORMED" in _codes(result.rejected[0].issues)
    assert [e.file_id for e in result.entries] == ["evidence_02"]


def test_optional_hash_column_is_validated_when_present(make_dataset: MakeDataset) -> None:
    good = hashlib.sha256(b"x").hexdigest()
    root = make_dataset(
        [
            f"evidence_01,evidence/a.log,svc,2026-03-01T10:00:00Z,{good.upper()}",
            f"evidence_02,evidence/b.log,svc,2026-03-01T10:00:00Z,{'0' * 64}",
        ],
        {"evidence/a.log": b"x", "evidence/b.log": b"x"},
        header="file_id,file_path,origin,captured_at,sha256",
    )
    result = load_manifest(root)
    assert [e.file_id for e in result.entries] == ["evidence_01"]
    assert "SOURCE_HASH_MISMATCH" in _codes(result.rejected[0].issues)


def test_oversized_source_is_rejected(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        ["evidence_01,evidence/a.log,svc,2026-03-01T10:00:00Z"], {"evidence/a.log": b"0123456789"}
    )
    result = load_manifest(root, max_source_bytes=4)
    assert not result.entries and "SOURCE_TOO_LARGE" in _codes(result.issues)


def test_unmanifested_files_are_reported_but_not_ingested(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        ["evidence_01,evidence/a.log,svc,2026-03-01T10:00:00Z"],
        {"evidence/a.log": b"a", "evidence/stray.log": b"stray"},
    )
    result = load_manifest(root)
    assert [e.file_id for e in result.entries] == ["evidence_01"]
    stray = [i for i in result.issues if i.code == "SOURCE_NOT_IN_MANIFEST"]
    assert [i.locator for i in stray] == ["evidence/stray.log"]
    assert stray[0].severity == "warning"
    assert not load_manifest(root, report_unmanifested=False).issues


def test_identical_content_under_two_ids_stays_two_sources(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        [
            "evidence_01,evidence/a.log,svc,2026-03-01T10:00:00Z",
            "evidence_02,evidence/b.log,svc,2026-03-05T10:00:00Z",
        ],
        {"evidence/a.log": b"same", "evidence/b.log": b"same"},
    )
    first, second = load_manifest(root).entries
    assert first.sha256 == second.sha256
    assert first.file_id != second.file_id and first.captured_at != second.captured_at


def test_same_path_twice_is_a_warning_and_both_rows_are_kept(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        [
            "evidence_01,evidence/a.log,svc,2026-03-01T10:00:00Z",
            "evidence_02,evidence/a.log,svc,2026-03-01T10:00:00Z",
        ],
        {"evidence/a.log": b"a"},
    )
    result = load_manifest(root)
    assert len(result.entries) == 2
    assert [i.code for i in result.issues].count("MANIFEST_DUPLICATE_PATH") == 2


def test_issue_messages_never_echo_source_values(make_dataset: MakeDataset) -> None:
    secret = "jane.doe@example.com"
    root = make_dataset(
        [
            f"evidence_01,evidence/a.log,svc,{secret}",
            f"{secret},evidence/b.log,svc,2026-03-01T10:00:00Z,x",
        ],
        {"evidence/a.log": b"a", "evidence/b.log": b"b"},
    )
    for issue in load_manifest(root).issues:
        assert secret not in issue.message
        assert secret not in (issue.locator or "")


def test_loading_twice_is_identical(make_dataset: MakeDataset) -> None:
    root = make_dataset(
        [
            "evidence_01,evidence/a.log,svc,2026-03-01T10:00:00Z",
            "evidence_02,evidence/missing.log,svc,bad",
        ],
        {"evidence/a.log": b"a", "evidence/stray.log": b"s"},
    )
    assert load_manifest(root) == load_manifest(root)
