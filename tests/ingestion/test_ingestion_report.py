from __future__ import annotations

import json
from pathlib import Path

import pytest
from ingestion_helpers import FakeOcr, ocr_of
from slam.ingestion.api import ingest_with_ocr
from slam.ingestion.parsers.image_parser import OcrResult
from slam.ingestion.report import build_report, main, render_markdown
from test_ingestion_api import build

PARTICIPANT_VALUES = [
    "ana.rios@example.com",
    "Ana.Rios@Example.com",
    "Ana Ríos",
    "+34 612 847 593",
    "areed1433@gmail.com",
]


def make_report(tmp_path: Path, *, ocr_ok: bool = True) -> tuple[dict, str]:  # type: ignore[type-arg]
    ocr = FakeOcr(
        ocr_of("backup_9287 areed1433@gmail.com")
        if ocr_ok
        else OcrResult(available=False, error="x")
    )
    bundle = ingest_with_ocr(build(tmp_path), ocr=ocr)
    report = build_report(bundle)
    return report, render_markdown(report)


def test_counts_are_consistent_with_the_bundle(tmp_path: Path) -> None:
    report, _ = make_report(tmp_path)
    assert report["sources"]["total"] == 6
    kinds = report["sources"]["by_kind"]
    assert sum(sum(c.values()) for c in kinds.values()) == 6
    assert report["observations"]["total"] == sum(report["observations"]["by_category"].values())
    assert report["observations"]["total"] == sum(report["observations"]["by_system"].values())
    assert report["tables"] == {
        "current_identities": 1,
        "identity_changes": 1,
        "activities": 1,
        "policy_rules": 1,
    }
    assert report["unresolved_sources"] == []


def test_report_reveals_no_participant_values_or_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Built at runtime so no key-shaped literal sits in source (the CI secret scan would flag it).
    fake_key = "sk" + "-" + "test-do-not-leak-0123456789"
    monkeypatch.setenv("OPENAI_API_KEY", fake_key)
    report, markdown = make_report(tmp_path)
    blob = markdown + json.dumps(report)
    for value in PARTICIPANT_VALUES:
        assert value not in blob
    assert fake_key not in blob and "test-do-not-leak" not in blob and str(tmp_path) not in blob


def test_failed_sources_are_listed_with_their_issue_codes(tmp_path: Path) -> None:
    report, markdown = make_report(tmp_path, ocr_ok=False)
    (problem,) = report["unresolved_sources"]
    assert problem["source_id"] == "evidence_06" and problem["parse_status"] == "failed"
    assert {"OCR_ENGINE_UNAVAILABLE", "IMAGE_UNRESOLVED"} <= set(problem["issue_codes"])
    assert "never evidence that the records it may contain are absent" in markdown
    assert (
        "image" in report["parser_coverage"] and report["parser_coverage"]["image"]["failed"] == 1
    )


def test_report_is_deterministic(tmp_path: Path) -> None:
    first, md_first = make_report(tmp_path / "a")
    second, md_second = make_report(tmp_path / "b")
    assert first == second and md_first == md_second


def test_command_line_writes_markdown_and_json(tmp_path: Path) -> None:
    dataset = build(tmp_path, manifest=[], files={})
    out, js = tmp_path / "report.md", tmp_path / "report.json"
    assert main(["--dataset", str(dataset), "--out", str(out), "--json-out", str(js)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Corpus inventory report")
    assert json.loads(js.read_text(encoding="utf-8"))["sources"]["total"] == 0
