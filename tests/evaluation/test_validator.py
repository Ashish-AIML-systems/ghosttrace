import csv
import json

import pytest
from slam.evaluation.validator import OutputValidationError, validate_output_csv


def write_output(tmp_path, rows, columns=("case_id", "deletion_status", "steps_json")):
    path = tmp_path / "output.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    return path


def test_valid_not_applicable_row(tmp_path):
    path = write_output(tmp_path, [["case_001", "NOT_APPLICABLE", "[]"]])
    answers = validate_output_csv(path, expected_case_ids=["case_001"])
    assert answers[0].case_id == "case_001"


def test_rejects_wrong_header(tmp_path):
    path = write_output(tmp_path, [], columns=("deletion_status", "case_id", "steps_json"))
    with pytest.raises(OutputValidationError, match="columns"):
        validate_output_csv(path, expected_case_ids=[])


def test_rejects_missing_or_duplicate_cases(tmp_path):
    path = write_output(tmp_path, [["case_001", "NOT_APPLICABLE", "[]"]])
    with pytest.raises(OutputValidationError, match="missing"):
        validate_output_csv(path, expected_case_ids=["case_001", "case_002"])

    duplicate = write_output(
        tmp_path,
        [["case_001", "NOT_APPLICABLE", "[]"], ["case_001", "NOT_APPLICABLE", "[]"]],
    )
    with pytest.raises(OutputValidationError, match="duplicate"):
        validate_output_csv(duplicate, expected_case_ids=["case_001"])


def test_rejects_non_deletion_with_steps(tmp_path):
    path = write_output(tmp_path, [["case_001", "NOT_APPLICABLE", '[{"step_no":1}]']])
    with pytest.raises(OutputValidationError, match=r"steps_json=\[\]"):
        validate_output_csv(path, expected_case_ids=["case_001"])


def test_rejects_complete_with_finding_phase(tmp_path):
    step = {
        "step_no": 1,
        "phase": "FINDING",
        "system_id": "account",
        "resource_id": "r1",
        "operation": "REPORT_REMAINING_RECORD",
        "state": "PRESENT",
        "evidence_id": "ev1",
    }
    path = write_output(tmp_path, [["case_001", "COMPLETE", json.dumps([step])]])
    with pytest.raises(OutputValidationError, match="verification only"):
        validate_output_csv(path, expected_case_ids=["case_001"])


def test_rejects_ineligible_citation_and_nonempty_future_evidence(tmp_path):
    finding = {
        "step_no": 1,
        "phase": "FINDING",
        "system_id": "account",
        "resource_id": "r1",
        "operation": "REPORT_REMAINING_RECORD",
        "state": "PRESENT",
        "evidence_id": "ev1",
    }
    proposed = {
        "step_no": 2,
        "phase": "REMEDIATION",
        "system_id": "account",
        "resource_id": "r1",
        "operation": "DELETE_RECORD",
        "state": "ABSENT",
        "evidence_id": "ev2",
    }
    path = write_output(
        tmp_path, [["case_001", "INCOMPLETE", json.dumps([finding, proposed])]]
    )
    with pytest.raises(OutputValidationError, match="future steps need empty"):
        validate_output_csv(path, expected_case_ids=["case_001"], eligible_evidence_ids={"ev1"})


def test_rejects_unsorted_cases(tmp_path):
    path = write_output(
        tmp_path,
        [["case_002", "NOT_APPLICABLE", "[]"], ["case_001", "NOT_APPLICABLE", "[]"]],
    )
    with pytest.raises(OutputValidationError, match="sorted"):
        validate_output_csv(path, expected_case_ids=["case_001", "case_002"])
