"""Builders shared by ingestion tests: contexts, real PDF/PNG bytes, a fake OCR engine."""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, datetime

from PIL import Image
from slam.ingestion.parsers.base import SourceContext
from slam.ingestion.parsers.image_parser import OcrLine, OcrResult

CAPTURED = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
SHA = "a" * 64


def ctx(source_id: str = "evidence_01", origin: str = "test_origin") -> SourceContext:
    return SourceContext(source_id, origin, CAPTURED, f"evidence/{source_id}", SHA)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: Sequence[Sequence[tuple[float, float, str]]]) -> bytes:
    """A small but valid PDF whose text layer holds ``(x, y, text)`` items per page."""
    count = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(count))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, items in enumerate(pages):
        body = "BT /F1 10 Tf " + " ".join(
            f"1 0 0 1 {x} {y} Tm ({_escape(text)}) Tj" for x, y, text in items
        )
        stream = (body + " ET").encode("latin-1")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>"
            ).encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    out = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, body_bytes in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body_bytes + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return out


def make_png(width: int = 320, height: int = 180) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (240, 240, 240)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeOcr:
    """OCR engine returning a fixed result, so no Tesseract binary is needed."""

    def __init__(self, result: OcrResult) -> None:
        self._result = result
        self.calls = 0

    def read(self, image: Image.Image) -> OcrResult:
        self.calls += 1
        return self._result


def ocr_of(*rows: str, confidence: float = 90.0, block: int = 0) -> OcrResult:
    """An OCR result with one line per string, stacked top to bottom."""
    lines = tuple(
        OcrLine(block=block, text=text, box=(10, 20 + 20 * i, 200, 14), confidence=confidence)
        for i, text in enumerate(rows)
    )
    return OcrResult(lines=lines)


def observation(resource_id: str = "account_1", **overrides: object):  # type: ignore[no-untyped-def]
    """A real contract ``Observation`` produced through the normalizer."""
    from slam.contracts import SourceKind
    from slam.ingestion.normalizer import normalize
    from slam.ingestion.parsers.base import ParseOutput, RawFact, json_span

    data = {"resource_id": resource_id, "email": "ana@example.com", "note": "hello ledger"}
    data.update(overrides.pop("data", {}))  # type: ignore[call-overload]
    fact = RawFact(
        layout="json.snapshot",
        effective_time=overrides.pop("effective_time", CAPTURED),  # type: ignore[arg-type]
        span=json_span(str(overrides.pop("source_id", "evidence_01")), "$.records[0]"),
        data=data,
        system_id=str(overrides.pop("system_id", "account_service")),
        resource_id=resource_id,
        collection="customer_profiles",
    )
    observations, _ = normalize(
        ctx(), SourceKind.JSON, ParseOutput("p", "1", (fact,), (), "parsed")
    )
    return observations[0]


def source_record(source_id: str = "evidence_01", sha256: str = SHA):  # type: ignore[no-untyped-def]
    from slam.contracts import ParseStatus, SourceKind, SourceRecord

    return SourceRecord(
        source_id=source_id,
        kind=SourceKind.JSON,
        origin="test_origin",
        path=f"evidence/{source_id}.json",
        captured_at=CAPTURED,
        sha256=sha256,
        parse_status=ParseStatus.PARSED,
    )
