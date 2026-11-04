import csv
import json

from slam.evaluation.scorer import score_outputs


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for row in rows:
            writer.writerow(row)


def test_scorer_reports_perfect_match(tmp_path):
    step = {
        "step_no": 1,
        "phase": "VERIFICATION",
        "system_id": "account",
        "resource_id": "r1",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
        "evidence_id": "ev1",
    }
    payload = json.dumps([step])
    pred = tmp_path / "pred.csv"
    ref = tmp_path / "ref.csv"
    rows = [["case_001", "COMPLETE", payload]]
    write(pred, rows)
    write(ref, rows)
    metrics = score_outputs(pred, ref)
    assert metrics.status_accuracy == 1.0
    assert metrics.exact_case_accuracy == 1.0
    assert metrics.step_f1 == 1.0
    assert metrics.sequence_accuracy == 1.0
    assert metrics.false_complete_count == 0


def test_scorer_flags_false_complete_and_missing_step(tmp_path):
    step = {
        "step_no": 1,
        "phase": "VERIFICATION",
        "system_id": "account",
        "resource_id": "r1",
        "operation": "VERIFY_RECORD_ABSENT",
        "state": "ABSENT",
        "evidence_id": "ev1",
    }
    pred = tmp_path / "pred.csv"
    ref = tmp_path / "ref.csv"
    write(pred, [["case_001", "COMPLETE", "[]"]])
    write(ref, [["case_001", "INCOMPLETE", json.dumps([step])]])
    metrics = score_outputs(pred, ref)
    assert metrics.status_accuracy == 0.0
    assert metrics.false_complete_count == 1
    assert metrics.step_precision == 0.0
    assert metrics.step_recall == 0.0
