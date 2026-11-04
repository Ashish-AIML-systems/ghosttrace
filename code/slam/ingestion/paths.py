"""Safe resolution of manifest-supplied paths under the dataset root."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath


class UnsafePathError(ValueError):
    """A manifest path that must not be opened. ``code`` is a stable issue code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def resolve_under_root(root: Path, relative: str) -> Path:
    """Resolve ``relative`` beneath ``root`` or raise :class:`UnsafePathError`.

    Manifest paths must be POSIX-style relative paths. Absolute paths, drive
    letters, backslashes, NUL bytes, ``..`` components and symlinks or
    junctions that leave the root are all rejected. The result is only a
    location: it is not guaranteed to exist.
    """
    if not isinstance(relative, str) or not relative:
        raise UnsafePathError("PATH_EMPTY", "path is empty")
    if relative != relative.strip():
        raise UnsafePathError("PATH_WHITESPACE", "path has leading/trailing space")
    if "\x00" in relative:
        raise UnsafePathError("PATH_NUL", "path contains a NUL byte")
    if "\\" in relative:
        raise UnsafePathError("PATH_BACKSLASH", "path contains a backslash")

    windows = PureWindowsPath(relative)
    if relative.startswith("/") or windows.drive or windows.root:
        raise UnsafePathError("PATH_ABSOLUTE", "path is absolute")
    if ".." in relative.split("/"):
        raise UnsafePathError("PATH_TRAVERSAL", "path contains a '..' component")

    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise UnsafePathError("PATH_ESCAPES_ROOT", "path resolves outside the dataset")
    return resolved
