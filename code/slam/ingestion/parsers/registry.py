"""Choose a parser from verified content, never from the filename alone."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from slam.contracts import SourceKind

from ..issues import Issue
from .base import ParseOutput, SourceContext

Parser = Callable[[SourceContext, bytes], ParseOutput]

_TS_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s")
_SQL_STATEMENT = re.compile(
    r"^\s*(?:CREATE\s+(?:TABLE|INDEX)|INSERT\s+INTO|BEGIN\s+TRANSACTION|PRAGMA)\b",
    re.IGNORECASE | re.MULTILINE,
)
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)
_EXTENSION_KIND: dict[str, SourceKind] = {
    ".json": SourceKind.JSON,
    ".log": SourceKind.LOG,
    ".txt": SourceKind.TEXT,
    ".sql": SourceKind.SQL,
    ".pdf": SourceKind.PDF,
    ".png": SourceKind.IMAGE,
    ".jpg": SourceKind.IMAGE,
    ".jpeg": SourceKind.IMAGE,
    ".csv": SourceKind.CSV,
}


@dataclass(frozen=True, slots=True)
class Detection:
    kind: SourceKind | None
    mime: str | None = None
    issues: tuple[Issue, ...] = ()


def hinted_kind(rel_path: str) -> SourceKind:
    """Kind suggested by the extension alone; used only to label a source that failed detection."""
    suffix = "." + rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
    return _EXTENSION_KIND.get(suffix, SourceKind.TEXT)


def image_mime(data: bytes) -> str | None:
    for magic, mime in _IMAGE_MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def sniff_kind(data: bytes) -> SourceKind | None:
    """Classify bytes by content. ``None`` means unrecognised binary or empty."""
    if image_mime(data) is not None:
        return SourceKind.IMAGE
    if data.startswith(b"%PDF-"):
        return SourceKind.PDF
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    body = text.lstrip("﻿ \t\r\n")
    if not body:
        return None
    if body[0] in "{[":
        try:
            json.loads(body)
        except ValueError:
            pass
        else:
            return SourceKind.JSON
    if _SQL_STATEMENT.search(text):
        return SourceKind.SQL
    lines = [line for line in text.splitlines() if line.strip()]
    stamped = [line for line in lines if _TS_PREFIX.match(line)]
    if lines and len(stamped) / len(lines) >= 0.6:
        structured = sum(1 for line in stamped if "=" in line or " {" in line)
        if structured / len(stamped) >= 0.5:
            return SourceKind.LOG
    return SourceKind.TEXT


def detect(data: bytes, rel_path: str, source_id: str) -> Detection:
    """Sniff the content and compare with the extension, which is only a hint."""
    kind = sniff_kind(data)
    suffix = "." + rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
    hinted = _EXTENSION_KIND.get(suffix)
    issues: list[Issue] = []
    if kind is None:
        issues.append(
            Issue(
                "FORMAT_UNRECOGNISED",
                "error",
                "content is empty or not a supported format",
                source_id,
                rel_path,
            )
        )
        return Detection(None, None, tuple(issues))
    if hinted is not None and hinted is not kind:
        # A .log that is really plain text (or .txt that is a log) is a mild disagreement.
        mild = {hinted, kind} <= {SourceKind.LOG, SourceKind.TEXT}
        issues.append(
            Issue(
                "FORMAT_EXTENSION_MISMATCH",
                "info" if mild else "warning",
                f"extension suggests {hinted.value} but content is {kind.value}; using content",
                source_id,
                rel_path,
            )
        )
    return Detection(kind, image_mime(data), tuple(issues))
