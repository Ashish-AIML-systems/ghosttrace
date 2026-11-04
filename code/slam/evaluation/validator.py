"""Strict, deterministic validation for the challenge output CSV."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from slam.contracts import CaseAnswer, DeletionStatus, Phase, Step

OUTPUT_COLUMNS = ("case_id", "deletion_status", "steps_json")
PHASE_ORDER = {Phase.FINDING: 0, Phase.REMEDIATION: 1, Phase.VERIFICATION: 2}


class OutputValidationError(ValueError):
    """Raised when output violates the participant-facing submission contract."""


def validate_output_csv(
    path: Path,
    *,
    expected_case_ids: Iterable[str],
    eligible_evidence_ids: Iterable[str] | None = None,
    evidence_captured_at: Mapping[str, Mapping[str, datetime]] | None = None,
    audit_cutoffs: Mapping[str, datetime] | None = None,
) -> tuple[CaseAnswer, ...]:
    """Read and validate CSV shape, row set, step semantics, order, and citations.

    `eligible_evidence_ids` is a legacy run-wide allowlist. Prefer the per-case
    `evidence_captured_at` and `audit_cutoffs` pair, which validates citation
    existence and temporal eligibility independently for each case.
    """

    expected = tuple(expected_case_ids)
    if len(expected) != len(set(expected)):
        raise OutputValidationError("expected_case_ids contains duplicates")
    expected_set = set(expected)
    evidence_set = set(eligible_evidence_ids) if eligible_evidence_ids is not None else None
    if (evidence_captured_at is None) != (audit_cutoffs is None):
        raise ValueError("evidence_captured_at and audit_cutoffs must be provided together")

    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != OUTPUT_COLUMNS:
                raise OutputValidationError(
                    f"columns must be exactly {','.join(OUTPUT_COLUMNS)} in that order"
                )
            rows = list(reader)
    except OSError as exc:
        raise OutputValidationError(f"cannot read output CSV: {exc}") from exc

    seen: set[str] = set()
    answers: list[CaseAnswer] = []
    row_ids: list[str] = []
    for row_number, row in enumerate(rows, start=2):
        case_id = (row.get("case_id") or "").strip()
        row_ids.append(case_id)
        if not case_id:
            raise OutputValidationError(f"row {row_number}: case_id is empty")
        if case_id in seen:
            raise OutputValidationError(f"row {row_number}: duplicate case_id {case_id}")
        seen.add(case_id)
        if case_id not in expected_set:
            raise OutputValidationError(f"row {row_number}: unexpected case_id {case_id}")

        try:
            status = DeletionStatus((row.get("deletion_status") or "").strip())
            raw_steps: Any = json.loads(row.get("steps_json") or "")
            if not isinstance(raw_steps, list):
                raise ValueError("steps_json must be a JSON array")
            if status is DeletionStatus.NOT_APPLICABLE and raw_steps:
                raise OutputValidationError(
                    f"row {row_number}: NOT_APPLICABLE requires steps_json=[]"
                )
            steps = tuple(Step.model_validate(item) for item in raw_steps)
            answer = CaseAnswer(
                case_id=case_id,
                deletion_status=status,
                steps=steps,
                ready_for_export=True,
            )
        except (ValueError, TypeError, ValidationError, json.JSONDecodeError) as exc:
            raise OutputValidationError(f"row {row_number} ({case_id}): {exc}") from exc

        case_evidence = evidence_set
        if evidence_captured_at is not None and audit_cutoffs is not None:
            if case_id not in evidence_captured_at or case_id not in audit_cutoffs:
                raise OutputValidationError(
                    f"row {row_number} ({case_id}): missing per-case evidence times or audit cutoff"
                )
            cutoff = audit_cutoffs[case_id]
            if cutoff.tzinfo is None or cutoff.utcoffset() is None:
                raise OutputValidationError(
                    f"row {row_number} ({case_id}): audit cutoff must be timezone-aware"
                )
            case_times = evidence_captured_at[case_id]
            if any(
                captured_at.tzinfo is None or captured_at.utcoffset() is None
                for captured_at in case_times.values()
            ):
                raise OutputValidationError(
                    f"row {row_number} ({case_id}): evidence timestamps must be timezone-aware"
                )
            case_evidence = {
                evidence_id
                for evidence_id, captured_at in case_times.items()
                if captured_at <= cutoff
            }
            if evidence_set is not None:
                case_evidence &= evidence_set
        _validate_case_semantics(answer, row_number, case_evidence)
        answers.append(answer)

    missing = expected_set - seen
    if missing:
        preview = ", ".join(sorted(missing)[:10])
        raise OutputValidationError(f"missing {len(missing)} expected case(s): {preview}")
    if len(rows) != len(expected):
        raise OutputValidationError(f"expected {len(expected)} data rows, found {len(rows)}")
    if row_ids != sorted(row_ids):
        raise OutputValidationError("rows must be sorted by case_id")
    return tuple(answers)


def _validate_case_semantics(
    answer: CaseAnswer,
    row_number: int,
    eligible_evidence_ids: set[str] | None,
) -> None:
    status = answer.deletion_status
    steps = answer.steps
    if status is DeletionStatus.NOT_APPLICABLE and steps:
        raise OutputValidationError(f"row {row_number}: NOT_APPLICABLE requires steps_json=[]")

    if status is DeletionStatus.COMPLETE and any(
        step.phase is not Phase.VERIFICATION for step in steps
    ):
        raise OutputValidationError(f"row {row_number}: COMPLETE may contain verification only")

    previous_phase = -1
    for step in steps:
        phase_rank = PHASE_ORDER[step.phase]
        if phase_rank < previous_phase:
            raise OutputValidationError(f"row {row_number}: phases are out of order")
        previous_phase = phase_rank

        must_cite = step.phase is Phase.FINDING or status is DeletionStatus.COMPLETE
        if must_cite and not step.evidence_id:
            raise OutputValidationError(
                f"row {row_number}, step {step.step_no}: evidence_id is required"
            )
        if (
            status is DeletionStatus.INCOMPLETE
            and step.phase is not Phase.FINDING
            and step.evidence_id
        ):
            raise OutputValidationError(
                f"row {row_number}, step {step.step_no}: future steps need empty evidence_id"
            )
        if (
            step.evidence_id
            and eligible_evidence_ids is not None
            and step.evidence_id not in eligible_evidence_ids
        ):
            raise OutputValidationError(
                f"row {row_number}, step {step.step_no}: ineligible evidence_id {step.evidence_id}"
            )
