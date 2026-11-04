from __future__ import annotations

import json

import pytest
from ingestion_helpers import make_pdf, make_png
from slam.contracts import SourceKind
from slam.ingestion.parsers.registry import detect, hinted_kind, image_mime, sniff_kind

LOG = (
    b"2026-03-01T10:00:00Z level=INFO service=a event=x resource_id=account_1\n"
    b"2026-03-01T10:00:01Z level=INFO service=a event=y resource_id=account_2\n"
)
HANDOVER = (
    b"SHIFT HANDOVER\nSnapshot: 2026-10-01T12:00:00Z\n\n"
    b"2026-10-01T12:00:00Z | account_service | account_146 | USER_PROFILE | NOT_FOUND | a@x.com\n"
    b"2026-10-01T12:00:00Z | account_service | account_147 | USER_PROFILE | NOT_FOUND | b@x.com\n"
)
SQL = (
    b"-- header\nBEGIN TRANSACTION;\nCREATE TABLE t (a TEXT);\n"
    b"INSERT INTO t VALUES('x');\nCOMMIT;\n"
)


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (make_png(), SourceKind.IMAGE),
        (make_pdf([[(10, 700, "hello")]]), SourceKind.PDF),
        (json.dumps({"records": []}).encode(), SourceKind.JSON),
        (b"\xef\xbb\xbf" + json.dumps([1, 2]).encode(), SourceKind.JSON),
        (SQL, SourceKind.SQL),
        (LOG, SourceKind.LOG),
        (HANDOVER, SourceKind.TEXT),
        (b"just some prose with no structure", SourceKind.TEXT),
    ],
)
def test_sniffs_kind_from_content(data: bytes, kind: SourceKind) -> None:
    assert sniff_kind(data) is kind


@pytest.mark.parametrize("data", [b"", b"   \n  ", b"\x00\x01\x02\xff\xfe binary"])
def test_empty_or_binary_is_unrecognised(data: bytes) -> None:
    assert sniff_kind(data) is None


def test_broken_json_is_not_called_json() -> None:
    assert sniff_kind(b'{"records": [') is SourceKind.TEXT


def test_detect_trusts_content_over_extension() -> None:
    found = detect(SQL, "evidence/data.json", "evidence_01")
    assert found.kind is SourceKind.SQL
    assert [i.code for i in found.issues] == ["FORMAT_EXTENSION_MISMATCH"]
    assert found.issues[0].severity == "warning"


def test_log_text_disagreement_is_only_informational() -> None:
    found = detect(HANDOVER, "evidence/handover.log", "evidence_01")
    assert found.kind is SourceKind.TEXT
    assert found.issues[0].severity == "info"


def test_detect_matching_extension_has_no_issue() -> None:
    assert detect(LOG, "evidence/a.log", "e").issues == ()


def test_unrecognised_content_is_an_explicit_error() -> None:
    found = detect(b"\x00\xff\xfe", "evidence/a.log", "evidence_01")
    assert found.kind is None
    assert found.issues[0].code == "FORMAT_UNRECOGNISED" and found.issues[0].severity == "error"


@pytest.mark.parametrize(
    ("path", "kind"),
    [("a.PNG", SourceKind.IMAGE), ("x/y.sql", SourceKind.SQL), ("noext", SourceKind.TEXT)],
)
def test_hinted_kind_is_only_a_label_for_failures(path: str, kind: SourceKind) -> None:
    assert hinted_kind(path) is kind


def test_image_mime_detection() -> None:
    assert image_mime(make_png()) == "image/png"
    assert image_mime(b"\xff\xd8\xff\xe0 jpeg") == "image/jpeg"
    assert image_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert image_mime(b"not an image") is None
