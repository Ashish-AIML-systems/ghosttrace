"""Frozen cross-team data contracts for SLAM contract version 1.0.0."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "1.0.0"


class ContractModel(BaseModel):
    """Immutable, strict base for every object crossing a team boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DeletionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RequestIntent(StrEnum):
    DELETION = "DELETION"
    NON_DELETION = "NON_DELETION"
    UNCLEAR = "UNCLEAR"


class Phase(StrEnum):
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"


class Operation(StrEnum):
    REPORT_REMAINING_RECORD = "REPORT_REMAINING_RECORD"
    REPORT_EXPOSED_PII = "REPORT_EXPOSED_PII"
    REPORT_ACTIVE_DATA_FLOW = "REPORT_ACTIVE_DATA_FLOW"
    REPORT_RESTORE_RISK = "REPORT_RESTORE_RISK"
    DISABLE_DATA_FLOW = "DISABLE_DATA_FLOW"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    DELETE_RECORD = "DELETE_RECORD"
    REDACT_RECORD = "REDACT_RECORD"
    ANONYMIZE_RECORD = "ANONYMIZE_RECORD"
    VERIFY_RECORD_ABSENT = "VERIFY_RECORD_ABSENT"
    VERIFY_RECORD_PRESENT = "VERIFY_RECORD_PRESENT"
    VERIFY_RECORD_REDACTED = "VERIFY_RECORD_REDACTED"
    VERIFY_RECORD_ANONYMIZED = "VERIFY_RECORD_ANONYMIZED"
    VERIFY_DATA_FLOW_DISABLED = "VERIFY_DATA_FLOW_DISABLED"
    VERIFY_RESTORE_BLOCKED = "VERIFY_RESTORE_BLOCKED"


class StepState(StrEnum):
    PRESENT = "PRESENT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"


class EvidenceNature(StrEnum):
    CLAIM = "CLAIM"
    OBSERVATION = "OBSERVATION"


class ConfidenceClass(StrEnum):
    EXACT = "EXACT"
    CORROBORATED = "CORROBORATED"
    CANDIDATE = "CANDIDATE"


class IssueSeverity(StrEnum):
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


class AuditRequest(ContractModel):
    case_id: str = Field(min_length=1)
    email: str = Field(min_length=3)
    requested_at: datetime
    reported_status: str = Field(min_length=1)
    reported_at: datetime
    audit_at: datetime
    request_text: str = Field(min_length=1)

    @field_validator("requested_at", "reported_at", "audit_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a UTC offset")
        return value


class SourceRecord(ContractModel):
    source_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    captured_at: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_name: str | None = None
    parser_version: str | None = None

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return AuditRequest.require_timezone(value)


class SourceSpan(ContractModel):
    source_id: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    quote: str | None = Field(default=None, max_length=1000)


class Observation(ContractModel):
    observation_id: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    state: str = Field(min_length=1)
    effective_at: datetime
    nature: EvidenceNature
    identifiers: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)
    provenance: tuple[SourceSpan, ...] = Field(min_length=1)

    @field_validator("effective_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return AuditRequest.require_timezone(value)


class IdentitySnapshot(ContractModel):
    user_id: str = Field(min_length=1)
    identifiers: dict[str, str]
    updated_at: datetime
    source_id: str

    @field_validator("updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return AuditRequest.require_timezone(value)


class IdentityChange(ContractModel):
    event_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    old_value: str | None = None
    new_value: str | None = None
    changed_at: datetime
    source_id: str

    @field_validator("changed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return AuditRequest.require_timezone(value)


class ActivityEvent(ContractModel):
    activity_id: str = Field(min_length=1)
    activity_type: str = Field(min_length=1)
    occurred_at: datetime
    system_id: str | None = None
    resource_id: str | None = None
    reported_result: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return AuditRequest.require_timezone(value)


class PolicyRule(ContractModel):
    rule_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    required_action: str = Field(min_length=1)
    condition: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class IngestionIssue(ContractModel):
    issue_id: str = Field(min_length=1)
    severity: IssueSeverity
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source_id: str | None = None


class EvidenceBundle(ContractModel):
    contract_version: str = CONTRACT_VERSION
    sources: tuple[SourceRecord, ...] = ()
    current_identities: tuple[IdentitySnapshot, ...] = ()
    identity_changes: tuple[IdentityChange, ...] = ()
    activities: tuple[ActivityEvent, ...] = ()
    observations: tuple[Observation, ...] = ()
    policy_rules: tuple[PolicyRule, ...] = ()
    issues: tuple[IngestionIssue, ...] = ()

    @field_validator("contract_version")
    @classmethod
    def require_current_contract(cls, value: str) -> str:
        if value != CONTRACT_VERSION:
            raise ValueError(f"expected contract version {CONTRACT_VERSION}")
        return value


class IdentityLink(ContractModel):
    left_identifier: str = Field(min_length=1)
    right_identifier: str = Field(min_length=1)
    relationship: str = Field(min_length=1)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    confidence: ConfidenceClass
    review_required: bool = False

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        for value in (self.valid_from, self.valid_to):
            if value is not None:
                AuditRequest.require_timezone(value)
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot be earlier than valid_from")
        return self


class ResourceState(ContractModel):
    system_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    state: str = Field(min_length=1)
    at: datetime
    supporting_evidence_ids: tuple[str, ...] = ()
    conflicting_evidence_ids: tuple[str, ...] = ()
    applicable_rule_id: str | None = None
    uncertain: bool = False

    @field_validator("at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return AuditRequest.require_timezone(value)


class GraphEdge(ContractModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relationship: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    active: bool


class CaseContext(ContractModel):
    contract_version: str = CONTRACT_VERSION
    request: AuditRequest
    request_intent: RequestIntent
    subject_id: str | None = None
    identity_links: tuple[IdentityLink, ...] = ()
    eligible_observation_ids: tuple[str, ...] = ()
    excluded_future_observation_ids: tuple[str, ...] = ()
    resource_states: tuple[ResourceState, ...] = ()
    active_flows: tuple[GraphEdge, ...] = ()
    restore_risks: tuple[GraphEdge, ...] = ()
    coverage_issues: tuple[str, ...] = ()
    unresolved_conflicts: tuple[str, ...] = ()

    @field_validator("contract_version")
    @classmethod
    def require_current_contract(cls, value: str) -> str:
        return EvidenceBundle.require_current_contract(value)


_OPERATION_RULES: dict[Operation, tuple[Phase, StepState]] = {
    Operation.REPORT_REMAINING_RECORD: (Phase.FINDING, StepState.PRESENT),
    Operation.REPORT_EXPOSED_PII: (Phase.FINDING, StepState.PRESENT),
    Operation.REPORT_ACTIVE_DATA_FLOW: (Phase.FINDING, StepState.ACTIVE),
    Operation.REPORT_RESTORE_RISK: (Phase.FINDING, StepState.ACTIVE),
    Operation.DISABLE_DATA_FLOW: (Phase.REMEDIATION, StepState.DISABLED),
    Operation.BLOCK_RESTORE: (Phase.REMEDIATION, StepState.BLOCKED),
    Operation.DELETE_RECORD: (Phase.REMEDIATION, StepState.ABSENT),
    Operation.REDACT_RECORD: (Phase.REMEDIATION, StepState.REDACTED),
    Operation.ANONYMIZE_RECORD: (Phase.REMEDIATION, StepState.ANONYMIZED),
    Operation.VERIFY_RECORD_ABSENT: (Phase.VERIFICATION, StepState.ABSENT),
    Operation.VERIFY_RECORD_PRESENT: (Phase.VERIFICATION, StepState.PRESENT),
    Operation.VERIFY_RECORD_REDACTED: (Phase.VERIFICATION, StepState.REDACTED),
    Operation.VERIFY_RECORD_ANONYMIZED: (Phase.VERIFICATION, StepState.ANONYMIZED),
    Operation.VERIFY_DATA_FLOW_DISABLED: (Phase.VERIFICATION, StepState.DISABLED),
    Operation.VERIFY_RESTORE_BLOCKED: (Phase.VERIFICATION, StepState.BLOCKED),
}


class Step(ContractModel):
    step_no: int = Field(ge=1)
    phase: Phase
    system_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    operation: Operation
    state: StepState
    evidence_id: str

    @model_validator(mode="after")
    def validate_operation_pair(self) -> Self:
        expected_phase, expected_state = _OPERATION_RULES[self.operation]
        if self.phase is not expected_phase or self.state is not expected_state:
            raise ValueError(
                f"{self.operation} requires phase={expected_phase} and state={expected_state}"
            )
        return self


class CaseAnswer(ContractModel):
    contract_version: str = CONTRACT_VERSION
    case_id: str = Field(min_length=1)
    deletion_status: DeletionStatus | None = None
    steps: tuple[Step, ...] = ()
    ready_for_export: bool = False
    blocking_issues: tuple[str, ...] = ()
    trace: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_export_readiness(self) -> Self:
        EvidenceBundle.require_current_contract(self.contract_version)
        if self.ready_for_export and (self.deletion_status is None or self.blocking_issues):
            raise ValueError("export-ready answers need a status and no blocking issues")
        if self.deletion_status is DeletionStatus.NOT_APPLICABLE and self.steps:
            raise ValueError("NOT_APPLICABLE answers cannot contain steps")
        if tuple(step.step_no for step in self.steps) != tuple(range(1, len(self.steps) + 1)):
            raise ValueError("step numbers must be consecutive from one")
        phase_order = {Phase.FINDING: 0, Phase.REMEDIATION: 1, Phase.VERIFICATION: 2}
        ranks = [phase_order[step.phase] for step in self.steps]
        if ranks != sorted(ranks):
            raise ValueError("steps must follow FINDING, REMEDIATION, VERIFICATION order")
        return self


CONTRACT_MODELS: tuple[type[ContractModel], ...] = (
    AuditRequest,
    SourceRecord,
    SourceSpan,
    Observation,
    IdentitySnapshot,
    IdentityChange,
    ActivityEvent,
    PolicyRule,
    IngestionIssue,
    EvidenceBundle,
    IdentityLink,
    ResourceState,
    GraphEdge,
    CaseContext,
    Step,
    CaseAnswer,
)
