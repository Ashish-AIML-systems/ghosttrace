from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from slam.contracts import (
    AuditRequest,
    CaseAnswer,
    DeletionStatus,
    Operation,
    Phase,
    Step,
    StepState,
)


def test_request_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        AuditRequest(
            case_id="case-1",
            email="person@example.test",
            requested_at=datetime(2026, 1, 1),
            reported_status="COMPLETE",
            reported_at=datetime.now(UTC),
            audit_at=datetime.now(UTC),
            request_text="Delete my account",
        )


def test_step_rejects_invalid_operation_pair() -> None:
    with pytest.raises(ValidationError):
        Step(
            step_no=1,
            phase=Phase.VERIFICATION,
            system_id="accounts",
            resource_id="r1",
            operation=Operation.DELETE_RECORD,
            state=StepState.ABSENT,
            evidence_id="",
        )


def test_not_applicable_has_no_steps() -> None:
    answer = CaseAnswer(
        case_id="case-1",
        deletion_status=DeletionStatus.NOT_APPLICABLE,
        ready_for_export=True,
    )
    assert answer.model_dump(mode="json")["steps"] == []
