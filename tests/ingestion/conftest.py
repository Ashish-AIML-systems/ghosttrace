"""Shared fixtures for ingestion tests (stdlib + pytest only, no network, no API key)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

# The shared pyproject does not exist yet, so make ``slam`` importable directly.
_CODE_DIR = Path(__file__).resolve().parents[2] / "code"
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

MANIFEST_HEADER = "file_id,file_path,origin,captured_at"


@pytest.fixture
def dir_link() -> Callable[[Path, Path], None]:
    """Create ``link`` -> ``target`` (symlink, or a junction on Windows without privilege)."""

    def create(link: Path, target: Path) -> None:
        try:
            os.symlink(target, link, target_is_directory=True)
            return
        except (OSError, NotImplementedError):
            pass
        if sys.platform == "win32":
            done = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True,
                check=False,
            )
            if done.returncode == 0:
                return
        pytest.skip("cannot create a directory link on this platform/user")

    return create


@pytest.fixture
def make_dataset(tmp_path: Path) -> Callable[..., Path]:
    """Build a throwaway dataset directory.

    ``manifest_lines`` are written verbatim under the header; ``files`` maps a
    dataset-relative path to bytes. Returns the dataset root.
    """

    def build(
        manifest_lines: list[str],
        files: Mapping[str, bytes] | None = None,
        *,
        header: str = MANIFEST_HEADER,
    ) -> Path:
        root = tmp_path / "dataset"
        root.mkdir(exist_ok=True)
        (root / "evidence_files.csv").write_text(
            "\n".join([header, *manifest_lines]) + "\n", encoding="utf-8"
        )
        for relative, content in (files or {}).items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return root

    return build
