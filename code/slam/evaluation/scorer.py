"""Transparent exact and component-level scoring against a reference CSV."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from slam.evaluation.validator import OUTPUT_COLUMNS

STEP_FIELDS = (
    "step_no",
    "phase",
    "system_id",
    "resource_id",
    "operation",
    "state",
    "evidence_id",
)


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    cases: int
    status_accuracy: float
    exact_case_accuracy: float
    step_precision: float
    step_recall: float
    step_f1: float
    field_accuracy: float
    sequence_accuracy: float
    false_complete_count: int
    prediction_case_ids: tuple[str, ...]
    reference_case_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_outputs(prediction_path: Path, reference_path: Path) -> EvaluationMetrics:
    """Compute metrics without silently aligning or dropping missing cases."""

    predictions = _read_rows(prediction_path)
    references = _read_rows(reference_path)
    pred_ids = tuple(row["case_id"] for row in predictions)
    ref_ids = tuple(row["case_id"] for row in references)
    pred_by_id = {row["case_id"]: row for row in predictions}
    ref_by_id = {row["case_id"]: row for row in references}
    all_ids = sorted(set(pred_by_id) | set(ref_by_id))
    count = len(all_ids)
    if count == 0:
        return EvaluationMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, pred_ids, ref_ids)

    status_correct = 0
    exact_cases = 0
    sequence_correct = 0
    field_correct = 0
    field_total = 0
    predicted_steps: list[tuple[str, ...]] = []
    reference_steps: list[tuple[str, ...]] = []
    false_complete = 0

    for case_id in all_ids:
        pred = pred_by_id.get(case_id)
        ref = ref_by_id.get(case_id)
        if pred is None or ref is None:
            continue
        if pred["deletion_status"] == ref["deletion_status"]:
            status_correct += 1
        if pred["deletion_status"] == "COMPLETE" and ref["deletion_status"] != "COMPLETE":
            false_complete += 1
        psteps = _parse_steps(pred["steps_json"])
        rsteps = _parse_steps(ref["steps_json"])
        pnorm = [_normalize_step(step) for step in psteps]
        rnorm = [_normalize_step(step) for step in rsteps]
        if pred["deletion_status"] == ref["deletion_status"] and pnorm == rnorm:
            exact_cases += 1
        if pnorm == rnorm:
            sequence_correct += 1
        for index in range(max(len(pnorm), len(rnorm))):
            pstep = pnorm[index] if index < len(pnorm) else None
            rstep = rnorm[index] if index < len(rnorm) else None
            for field_index in range(len(STEP_FIELDS)):
                field_total += 1
                if (
                    pstep is not None
                    and rstep is not None
                    and pstep[field_index] == rstep[field_index]
                ):
                    field_correct += 1
        predicted_steps.extend(pnorm)
        reference_steps.extend(rnorm)

    pred_set = set(predicted_steps)
    ref_set = set(reference_steps)
    true_positive = len(pred_set & ref_set)
    precision = true_positive / len(pred_set) if pred_set else float(not ref_set)
    recall = true_positive / len(ref_set) if ref_set else float(not pred_set)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return EvaluationMetrics(
        cases=count,
        status_accuracy=status_correct / count,
        exact_case_accuracy=exact_cases / count,
        step_precision=precision,
        step_recall=recall,
        step_f1=f1,
        field_accuracy=field_correct / field_total if field_total else 1.0,
        sequence_accuracy=sequence_correct / count,
        false_complete_count=false_complete,
        prediction_case_ids=pred_ids,
        reference_case_ids=ref_ids,
    )


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTPUT_COLUMNS:
            raise ValueError(f"{path}: expected columns {','.join(OUTPUT_COLUMNS)}")
        rows = list(reader)
    ids = [row["case_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate case_id")
    return rows


def _parse_steps(value: str) -> list[dict[str, Any]]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("steps_json must contain a JSON array")
    if any(not isinstance(step, dict) for step in parsed):
        raise ValueError("each step must be a JSON object")
    return parsed


def _normalize_step(step: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(step.get(field, "")) for field in STEP_FIELDS)
