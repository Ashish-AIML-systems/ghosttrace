"""Machine-readable results the run writes to ``results/``.

``python code/main.py --dataset dataset`` writes ``results/run_summary.json`` and
``results/sample_scores.json`` next to ``output.csv``; ``--insight`` adds
``results/insight_summary.json``. Everything is derived from files the run just produced and is
deterministic (no timestamps or timings), so a rerun on the same data gives the same bytes and the
files are safe to commit.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from slam.evaluation.scorer import EvaluationMetrics
from slam.pipeline import RunSummary, evaluate_samples


def _dump(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_summary(summary: RunSummary, output_path: Path) -> dict[str, Any]:
    """What the full run produced: counts per status and a fingerprint of ``output.csv``."""

    raw = output_path.read_bytes()
    with output_path.open(encoding="utf-8", newline="") as handle:
        rows = sum(1 for _ in csv.DictReader(handle))
    return {
        "cases": summary.cases,
        "statuses": dict(sorted(summary.statuses.items())),
        "not_certified_uncertain": summary.uncertain_cases,
        "failed_cases": len(summary.failures),
        "output_file": output_path.name,
        "output_rows": rows,
        "output_sha256": hashlib.sha256(raw).hexdigest(),
    }


def sample_scores(metrics: EvaluationMetrics) -> dict[str, Any]:
    """The 32 public samples scored against the answers HackerRank publishes for them."""

    scores = metrics.to_dict()
    scores.pop("prediction_case_ids", None)
    scores.pop("reference_case_ids", None)
    return {"source": "dataset/sample_output.csv", **scores}


def insight_summary(data: Mapping[str, Any]) -> dict[str, Any]:
    """The headline numbers of ``dashboard/insight_data.json``, without the per-case rows."""

    model, graph, llm = data["model"], data["graph"], data["llm"]
    usage = llm.get("usage") or {}
    return {
        "audit": data["summary"],
        "predictor": {
            "algorithm": model["algorithm"],
            "audited_cases": model["n_train"],
            "cross_validated": model["cv"],
            "baselines": model["baselines"],
            "held_out_samples": model["external"],
            "per_failure_type": [
                {"type": t["type"], "cases": t["positives"], "auc": t["auc"]}
                for t in model["per_type"]
            ],
        },
        "patterns": [
            {"id": p["pattern_id"], "cases": p["size"], "label": p["label"]}
            for p in data["patterns"]["items"]
        ],
        "graph": {
            "engine": graph["engine_version"],
            "crosscheck": graph["crosscheck"],
            "systems_with_a_recreation_path": sorted(k for k, v in graph["paths"].items() if v),
        },
        "explanations": {
            "written_by_model": llm["accepted"],
            "incomplete_cases": data["meta"]["failed_cases"],
            "model": usage.get("model"),
            "stored_reply_tokens": llm["reply_tokens"],
        },
    }


def write_results(
    results_dir: Path, summary: RunSummary, output_path: Path, dataset_dir: Path
) -> list[Path]:
    """Write the run summary and the sample scores; returns the files written."""

    _, metrics = evaluate_samples(dataset_dir)
    return [
        _dump(results_dir / "run_summary.json", run_summary(summary, output_path)),
        _dump(results_dir / "sample_scores.json", sample_scores(metrics)),
    ]


def write_insight_summary(results_dir: Path, insight_data: Path) -> Path:
    data = json.loads(insight_data.read_text(encoding="utf-8"))
    return _dump(results_dir / "insight_summary.json", insight_summary(data))
