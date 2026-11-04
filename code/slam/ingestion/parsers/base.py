"""Format-agnostic parser output.

Parsers turn bytes into ``RawFact`` records that keep the source's own words and
a provenance span. They never decide categories, states or identities: that is
the normalizer's single, reviewable job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from slam.contracts import (
    ImageRegionLocator,
    LineRangeLocator,
    PdfPositionLocator,
    SourceSpan,
    TableRowLocator,
)

from ..issues import Issue

Nature = Literal["observation", "claim"]
ParseState = Literal["parsed", "partial", "failed"]

MAX_QUOTE = 300  # contract allows 500; shorter keeps spans and reports compact


@dataclass(frozen=True, slots=True)
class SourceContext:
    """What a parser may know about the file it is reading."""

    source_id: str
    origin: str
    captured_at: datetime
    rel_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RawFact:
    """One statement found in a source, before normalization.

    ``data`` holds the source fields verbatim. ``state`` is the source's own
    result/status token (for example ``NOT_FOUND`` or ``enabled=false`` already
    spelled as a token by the parser), never an inferred conclusion.
    """

    layout: str
    effective_time: datetime
    span: SourceSpan
    data: dict[str, Any]
    system_id: str | None = None
    resource_id: str | None = None
    collection: str | None = None
    container: str | None = None  # table / snapshot / page that held it, so copies stay distinct
    category: str | None = None
    state: str | None = None
    nature: Nature = "observation"
    subject_keys: tuple[str, ...] = ()
    more_spans: tuple[SourceSpan, ...] = ()  # further places the same fact appears
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParseOutput:
    parser_name: str
    parser_version: str
    facts: tuple[RawFact, ...]
    issues: tuple[Issue, ...]
    status: ParseState
    stats: dict[str, int] = field(default_factory=dict)


def quote_of(text: str) -> str | None:
    """A short single-line excerpt for a span, or ``None`` if there is nothing to quote."""
    flat = " ".join(text.split())
    if not flat:
        return None
    return flat if len(flat) <= MAX_QUOTE else flat[: MAX_QUOTE - 1] + "…"


def row_span(source_id: str, table: str, row: int, quote: str | None = None) -> SourceSpan:
    return SourceSpan(
        source_id=source_id, table_row=TableRowLocator(table=table, row=row), quote=quote
    )


def line_span(
    source_id: str, start: int, end: int | None = None, quote: str | None = None
) -> SourceSpan:
    return SourceSpan(
        source_id=source_id,
        line_range=LineRangeLocator(start=start, end=end if end is not None else start),
        quote=quote,
    )


def json_span(source_id: str, path: str, quote: str | None = None) -> SourceSpan:
    return SourceSpan(source_id=source_id, json_path=path, quote=quote)


def pdf_span(
    source_id: str,
    page: int,
    box: tuple[float, float, float, float] | None = None,
    quote: str | None = None,
) -> SourceSpan:
    if box is None:
        locator = PdfPositionLocator(page=page)
    else:
        locator = PdfPositionLocator(page=page, x0=box[0], y0=box[1], x1=box[2], y1=box[3])
    return SourceSpan(source_id=source_id, pdf_position=locator, quote=quote)


def image_span(
    source_id: str, region: tuple[int, int, int, int], quote: str | None = None
) -> SourceSpan:
    x, y, width, height = region
    return SourceSpan(
        source_id=source_id,
        image_region=ImageRegionLocator(x=x, y=y, width=width, height=height),
        quote=quote,
    )
