from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from slam.ingestion.paths import UnsafePathError, resolve_under_root


def test_resolves_normal_relative_path(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "a.log").write_text("x")
    resolved = resolve_under_root(tmp_path, "evidence/a.log")
    assert resolved == (tmp_path / "evidence" / "a.log").resolve()


def test_nonexistent_path_is_resolved_not_checked(tmp_path: Path) -> None:
    # Existence is the manifest loader's job; resolution only guards location.
    assert resolve_under_root(tmp_path, "evidence/missing.log").is_relative_to(tmp_path)


@pytest.mark.parametrize(
    ("bad", "code"),
    [
        ("", "PATH_EMPTY"),
        (" evidence/a.log", "PATH_WHITESPACE"),
        ("evidence/a.log ", "PATH_WHITESPACE"),
        ("evidence/a\x00.log", "PATH_NUL"),
        ("evidence\\a.log", "PATH_BACKSLASH"),
        ("/etc/passwd", "PATH_ABSOLUTE"),
        ("C:/Windows/win.ini", "PATH_ABSOLUTE"),
        ("C:win.ini", "PATH_ABSOLUTE"),
        ("../secret.txt", "PATH_TRAVERSAL"),
        ("evidence/../../secret.txt", "PATH_TRAVERSAL"),
        ("evidence/..", "PATH_TRAVERSAL"),
    ],
)
def test_rejects_unsafe_paths_with_stable_codes(tmp_path: Path, bad: str, code: str) -> None:
    with pytest.raises(UnsafePathError) as info:
        resolve_under_root(tmp_path, bad)
    assert info.value.code == code


def test_rejects_symlink_that_escapes_root(
    tmp_path: Path, dir_link: Callable[[Path, Path], None]
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    root = tmp_path / "root"
    root.mkdir()
    dir_link(root / "link", outside)
    with pytest.raises(UnsafePathError) as info:
        resolve_under_root(root, "link/secret.txt")
    assert info.value.code == "PATH_ESCAPES_ROOT"
