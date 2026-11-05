"""``results/*.json``: deterministic, free of timings, and tied to the file the run wrote."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from slam.evaluation.scorer import EvaluationMetrics
from slam.pipeline import RunSummary
from slam.results import insight_summary, run_summary, sample_scores, write_insight_summary


def _summary() -> RunSummary:
    summary = RunSummary(cases=3, seconds=12.5)
    summary.statuses.update({"INCOMPLETE": 2, "COMPLETE": 1})
    summary.uncertain_cases = 1
    return summary


def test_run_summary_fingerprints_the_output_and_has_no_timings(tmp_path: Path) -> None:
    out = tmp_path / "output.csv"
    out.write_text('case_id,deletion_status,steps_json\na,COMPLETE,"[]"\nb,INCOMPLETE,"[]"\n')
    data = run_summary(_summary(), out)
    assert data == {
        "cases": 3,
        "statuses": {"COMPLETE": 1, "INCOMPLETE": 2},
        "not_certified_uncertain": 1,
        "failed_cases": 0,
        "output_file": "output.csv",
        "output_rows": 2,
        "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    assert "seconds" not in json.dumps(data)


def test_sample_scores_drop_the_case_id_lists() -> None:
    metrics = EvaluationMetrics(
        cases=32,
        status_accuracy=0.9,
        exact_case_accuracy=0.3,
        step_precision=0.7,
        step_recall=0.7,
        step_f1=0.7,
        field_accuracy=0.8,
        sequence_accuracy=0.4,
        false_complete_count=0,
        prediction_case_ids=("a",),
        reference_case_ids=("a",),
    )
    scores = sample_scores(metrics)
    assert scores["cases"] == 32 and scores["false_complete_count"] == 0
    assert "prediction_case_ids" not in scores and scores["source"] == "dataset/sample_output.csv"


def _insight() -> dict[str, Any]:
    return {
        "summary": {"status": {"COMPLETE": 1}},
        "meta": {"failed_cases": 7},
        "model": {
            "algorithm": "LightGBM",
            "n_train": 10,
            "cv": {"auc": 0.8},
            "baselines": {},
            "external": None,
            "per_type": [{"type": "EXPOSED_PII", "positives": 3, "auc": None}],
        },
        "graph": {
            "engine_version": "networkx",
            "crosscheck": None,
            "paths": {"a": [["x", "a"]], "b": []},
        },
        "patterns": {"items": [{"pattern_id": "P1", "size": 4, "label": "x"}]},
        "llm": {"accepted": 2, "reply_tokens": {"input": 1}, "usage": None},
        "cases": [{"id": "case_1", "secret": "not in the summary"}],
    }


def test_insight_summary_keeps_headlines_and_drops_case_rows(tmp_path: Path) -> None:
    summary = insight_summary(_insight())
    assert summary["graph"]["systems_with_a_recreation_path"] == ["a"]
    assert summary["explanations"] == {
        "written_by_model": 2,
        "incomplete_cases": 7,
        "model": None,
        "stored_reply_tokens": {"input": 1},
    }
    assert "case_1" not in json.dumps(summary)

    source = tmp_path / "insight_data.json"
    source.write_text(json.dumps(_insight()), encoding="utf-8")
    first = write_insight_summary(tmp_path / "results", source).read_bytes()
    assert (
        write_insight_summary(tmp_path / "results", source).read_bytes() == first
    )  # deterministic
