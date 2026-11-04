"""Strict timestamp parsing. Every accepted time is timezone-aware UTC."""

from __future__ import annotations

import re
from datetime import UTC, datetime

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$")


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp with an explicit offset into UTC.

    Naive timestamps are rejected: an unknown zone would make cutoff filtering
    ambiguous. Raises ``ValueError`` on anything else.
    """
    if not isinstance(value, str) or not _ISO.match(value):
        raise ValueError("timestamp must be ISO-8601 with an explicit UTC offset")
    return datetime.fromisoformat(value).astimezone(UTC)
