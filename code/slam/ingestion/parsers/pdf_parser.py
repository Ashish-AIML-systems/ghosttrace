"""PDF text-layer parser with page and position provenance.

Only the text layer is read, through pypdf. Nothing in the document is executed:
scripts, launch actions and links are ignored, and encrypted or unreadable files
are reported as failures. Positions are composed from the content-stream and
text matrices; the right/top edge of a box is estimated from the font size, so
it is approximate and meant for locating a line, not for pixel-exact cropping.

A page with no text layer is reported explicitly (``PDF_PAGE_NO_TEXT``). It is
never read as an empty page.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..issues import Issue
from .base import ParseOutput, ParseState, RawFact, SourceContext, pdf_span
from .doctext import TextLine, extract_facts, quote_for, split_blocks

PARSER_NAME = "pdf"
PARSER_VERSION = "1.0.0"

MAX_PAGES = 200
_Y_TOLERANCE = 1.5  # fragments within this vertical distance share a line
_WIDTH_PER_EM = 0.5  # rough average glyph width as a fraction of the font size


@dataclass(slots=True)
class _Fragment:
    text: str
    x: float
    y: float
    size: float


@dataclass(slots=True)
class _Line:
    y: float
    fragments: list[_Fragment] = field(default_factory=list)


def _origin(cm: list[float], tm: list[float]) -> tuple[float, float]:
    """Page-space origin of a text fragment from content-stream and text matrices."""
    x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
    return x, y


def _page_lines(page: Any, number: int) -> list[TextLine]:
    fragments: list[_Fragment] = []

    def visitor(text: str, cm: list[float], tm: list[float], _font: Any, size: float) -> None:
        if not text.strip():
            return
        x, y = _origin(cm, tm)
        fragments.append(_Fragment(text, x, y, float(size) if size else 10.0))

    page.extract_text(visitor_text=visitor)
    rows: list[_Line] = []
    for fragment in sorted(fragments, key=lambda f: (-round(f.y, 1), f.x)):
        for row in rows:
            if abs(row.y - fragment.y) <= _Y_TOLERANCE:
                row.fragments.append(fragment)
                break
        else:
            rows.append(_Line(fragment.y, [fragment]))

    lines: list[TextLine] = []
    for row in sorted(rows, key=lambda r: -r.y):
        ordered = sorted(row.fragments, key=lambda f: f.x)
        text = " ".join(f.text.strip() for f in ordered)
        x0 = min(f.x for f in ordered)
        x1 = max(f.x + len(f.text) * f.size * _WIDTH_PER_EM for f in ordered)
        size = max(f.size for f in ordered)
        lines.append(TextLine(page=number, text=text, box=(x0, row.y, x1, row.y + size)))
    return lines


def parse_pdf(ctx: SourceContext, data: bytes) -> ParseOutput:
    def done(
        facts: list[RawFact], issues: list[Issue], status: ParseState, stats: dict[str, int]
    ) -> ParseOutput:
        return ParseOutput(PARSER_NAME, PARSER_VERSION, tuple(facts), tuple(issues), status, stats)

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            issue = Issue(
                "PDF_ENCRYPTED", "error", "PDF is encrypted; not decrypted", ctx.source_id
            )
            return done([], [issue], "failed", {})
        page_count = len(reader.pages)
    except (PdfReadError, ValueError, KeyError, OSError, RecursionError) as exc:
        issue = Issue(
            "PDF_UNREADABLE",
            "error",
            f"PDF could not be read ({type(exc).__name__})",
            ctx.source_id,
        )
        return done([], [issue], "failed", {})

    issues: list[Issue] = []
    if page_count > MAX_PAGES:
        issues.append(
            Issue(
                "PDF_TOO_MANY_PAGES",
                "warning",
                f"{page_count} pages; only the first {MAX_PAGES} were read",
                ctx.source_id,
            )
        )
    lines: list[TextLine] = []
    blank_pages: list[int] = []
    failed_pages: list[int] = []
    for number in range(1, min(page_count, MAX_PAGES) + 1):
        try:
            page_lines = _page_lines(reader.pages[number - 1], number)
        except (PdfReadError, ValueError, KeyError, TypeError, RecursionError):
            failed_pages.append(number)
            continue
        if not page_lines:
            blank_pages.append(number)
        lines.extend(page_lines)

    for number in blank_pages:
        issues.append(
            Issue(
                "PDF_PAGE_NO_TEXT",
                "warning",
                "page has no text layer; its content was not read (not proof it is empty)",
                ctx.source_id,
                f"page {number}",
            )
        )
    for number in failed_pages:
        issues.append(
            Issue(
                "PDF_PAGE_UNREADABLE",
                "error",
                "page text could not be extracted",
                ctx.source_id,
                f"page {number}",
            )
        )

    facts = extract_facts(
        ctx,
        split_blocks(lines),
        layout="pdf",
        span_for=lambda ln: pdf_span(ctx.source_id, ln.page, ln.box, quote_for(ln)),
    )
    if not facts and not blank_pages and not failed_pages:
        issues.append(
            Issue(
                "PDF_NO_ANCHORS",
                "warning",
                "text was read but no resource ids or identifiers were recognised",
                ctx.source_id,
            )
        )
    clean = not blank_pages and not failed_pages and page_count <= MAX_PAGES and bool(facts)
    status: ParseState = "parsed" if clean else ("failed" if not lines and not facts else "partial")
    stats = {"pages": page_count, "lines": len(lines), "facts": len(facts)}
    return done(facts, issues, status, stats)
