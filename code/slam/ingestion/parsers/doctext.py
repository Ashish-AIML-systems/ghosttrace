"""Deterministic entity-anchor extraction for document-like text (PDF, OCR, prose).

Layout is unreliable in documents, so this relies on high-precision anchors:
resource ids (known prefixes), order references, e-mail addresses, phone
numbers and ``user_N`` references. Identifiers found on or just after an anchor
line, inside the same block, are attached to that anchor. Identifiers with no
anchor nearby are kept together as one document-level fact rather than being
dropped or wrongly attached.

The output states only what the text shows: that the id appears with those
identifiers. It does not decide whether a record is deleted, retained or
exposed. Deciding is later, deterministic work.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from slam.contracts import SourceSpan

from ..vocab import EMAIL_RE, PHONE_RE, RESOURCE_ID_RE, USER_ID_RE
from .base import RawFact, SourceContext, quote_of

ORDER_RE = re.compile(r"\bORD-[0-9]+\b(?!-\w)")
WINDOW = 8  # lines after an anchor that may still describe it
MAX_KEPT_LINES = 12

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
# "25 Aug 2027 04:03 UTC"; text extraction often drops the colon, leaving "04 03 UTC".
_DATE = re.compile(
    r"(?P<label>retain until|retained until|recorded|issued|received|captured|submitted|"
    r"generated|order date|created|expires)?\s*"
    r"(?P<d>\d{1,2})\s+(?P<m>[A-Z][a-z]{2})\s+(?P<y>\d{4})"
    r"(?:\s+(?P<h>\d{2})[:\s]\s?(?P<min>\d{2})\s*UTC)?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TextLine:
    """One line of extracted text with an optional position on its page."""

    page: int
    text: str
    box: tuple[float, float, float, float] | None = None
    line_no: int | None = None


@dataclass(slots=True)
class _Anchor:
    """An anchor accumulated across every place it appears in one document."""

    anchor: str
    kind: str  # "resource" | "order"
    spans: list[SourceSpan] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    users: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    scope: str = "line"  # "line" = on/after the anchor, "block" = same block only


def _add_unique(target: list[str], values: Sequence[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def find_dates(text: str) -> dict[str, str]:
    """Labelled dates in ``text`` as ISO-8601 UTC strings. First occurrence of a label wins."""
    found: dict[str, str] = {}
    for match in _DATE.finditer(" ".join(text.split())):
        month = _MONTHS.get(match.group("m").lower())
        if month is None:
            continue
        try:
            moment = datetime(
                int(match.group("y")),
                month,
                int(match.group("d")),
                int(match.group("h") or 0),
                int(match.group("min") or 0),
                tzinfo=UTC,
            )
        except ValueError:
            continue
        label = (match.group("label") or "date").lower().replace(" ", "_")
        found.setdefault(label, moment.isoformat().replace("+00:00", "Z"))
    return found


def _identifiers(text: str) -> tuple[list[str], list[str], list[str]]:
    return (
        EMAIL_RE.findall(text),
        [p.strip() for p in PHONE_RE.findall(text)],
        USER_ID_RE.findall(text),
    )


def split_blocks(lines: Sequence[TextLine]) -> list[list[TextLine]]:
    """Group lines into blocks at page changes and at ``Record`` card headings."""
    blocks: list[list[TextLine]] = []
    current: list[TextLine] = []
    for line in lines:
        starts_card = line.text.strip().lower() == "record"
        if current and (starts_card or line.page != current[-1].page):
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def extract_facts(
    ctx: SourceContext,
    blocks: Sequence[Sequence[TextLine]],
    *,
    layout: str,
    span_for: Callable[[TextLine], SourceSpan],
    when: datetime | None = None,
) -> list[RawFact]:
    """Turn text blocks into one fact per distinct anchor plus one document-level fact."""
    moment = when or ctx.captured_at
    anchors: dict[str, _Anchor] = {}
    orphan = _Anchor("", "document")
    orphan_first: TextLine | None = None
    all_text: list[str] = []

    for block in blocks:
        touched: list[_Anchor] = []
        block_orphan = _Anchor("", "document")
        current: list[_Anchor] = []
        current_index = -1
        for index, line in enumerate(block):
            text = line.text
            all_text.append(text)
            found = [(a, "resource") for a in RESOURCE_ID_RE.findall(text)] + [
                (a, "order") for a in ORDER_RE.findall(text)
            ]
            emails, phones, users = _identifiers(text)
            if found:
                current = []
                current_index = index
                for name, kind in dict.fromkeys(found):
                    item = anchors.setdefault(name, _Anchor(name, kind))
                    item.spans.append(span_for(line))
                    _add_unique(item.emails, emails)
                    _add_unique(item.phones, phones)
                    _add_unique(item.users, users)
                    _add_unique(item.lines, [text])
                    current.append(item)
                    if item not in touched:
                        touched.append(item)
            elif current and index - current_index <= WINDOW:
                for item in current:
                    _add_unique(item.emails, emails)
                    _add_unique(item.phones, phones)
                    _add_unique(item.users, users)
                    if len(item.lines) < MAX_KEPT_LINES:
                        _add_unique(item.lines, [text])
            elif emails or phones or users:
                orphan_first = orphan_first or line
                for bucket in (orphan, block_orphan):
                    _add_unique(bucket.emails, emails)
                    _add_unique(bucket.phones, phones)
                    _add_unique(bucket.users, users)
                    if len(bucket.lines) < MAX_KEPT_LINES:
                        _add_unique(bucket.lines, [text])
        # An anchor with no identifier of its own may still belong to the person
        # named elsewhere in the same block (for example a customer header).
        for item in touched:
            if not (item.emails or item.phones or item.users):
                _add_unique(item.emails, block_orphan.emails)
                _add_unique(item.phones, block_orphan.phones)
                _add_unique(item.users, block_orphan.users)
                if block_orphan.emails or block_orphan.phones or block_orphan.users:
                    item.scope = "block"

    facts: list[RawFact] = []
    for item in anchors.values():
        # An anchor that is a strict prefix of another in the same document is most
        # likely a truncated read of it (OCR drops trailing characters).
        longer = [o for o in anchors if o != item.anchor and o.startswith(item.anchor)]
        facts.append(
            RawFact(
                layout=f"{layout}.anchor",
                effective_time=moment,
                span=item.spans[0],
                more_spans=tuple(item.spans[1:]),
                data={
                    "anchor_kind": item.kind,
                    "emails": item.emails,
                    "phones": item.phones,
                    "user_ids": item.users,
                    "lines": item.lines,
                    "dates": find_dates(" ".join(item.lines)),
                    "identifier_scope": item.scope,
                    **({"possible_truncation_of": longer[0]} if longer else {}),
                },
                resource_id=item.anchor,
                provenance={"uncertain": True} if longer else {},
            )
        )
    if orphan_first is not None:
        facts.append(
            RawFact(
                layout=f"{layout}.document",
                effective_time=moment,
                span=span_for(orphan_first),
                data={
                    "emails": orphan.emails,
                    "phones": orphan.phones,
                    "user_ids": orphan.users,
                    "lines": orphan.lines,
                    "dates": find_dates(" ".join(all_text)),
                },
            )
        )
    return facts


def quote_for(line: TextLine) -> str | None:
    return quote_of(line.text)
