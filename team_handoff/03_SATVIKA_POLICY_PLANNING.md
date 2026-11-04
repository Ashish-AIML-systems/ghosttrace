# Satvika build document

## Mission

Build the deterministic Judge–Evidence–Verify pipeline. Your subsystem consumes Manya's `CaseContext`, applies the supplied policy to every relevant record/process, decides the supported status, produces the exact ordered findings/remediation/verification steps, validates them, and exports compliant CSV rows. You do not parse raw evidence, resolve identities, or call models for the final decision.

Read root `AGENTS.md`, `problem_statement.md`, and `team_handoff/SHARED_BUILD_CONTRACT.md`. Contract version `1.0.0` is frozen.

## Owned paths

```text
code/slam/planning/**
tests/planning/**
tests/fixtures/planning/**
```

Do not edit ingestion, reconstruction, runtime, Docker, shared contracts, or dependency locks without an approved change request.

## Required flow

1. Validate that the context is complete enough to evaluate; unresolved blockers prevent certification.
2. If the request does not authorize deletion, return `NOT_APPLICABLE` with no steps.
3. Load and validate the exact rules from `deletion_rules.csv`; do not replace them with assumptions.
4. Judge the required treatment for each relevant resource: delete, redact, anonymize, retain, or retain a compliant tombstone.
5. Check the evidence establishing the state at `audit_at`.
6. Verify whether the observed state satisfies the treatment and whether flows/restores can recreate prohibited data.
7. Decide `COMPLETE` only when all relevant records/processes comply and the required evidence exists.
8. For `INCOMPLETE`, emit all supported findings, the complete safe remediation plan, and a verification for every remediated resource/process.
9. Validate allowed operations/state pairs, evidence requirements, dependencies, ordering, numbering, exact fields, and deterministic JSON.
10. Export rows sorted by `case_id` with exact columns and no extra fields.

## Critical policy cases

- `ACCOUNT_TOMBSTONE`: preserve only the allowed stable subject reference; remove prohibited direct identifiers including exposed hash where the rule requires it.
- Retained security/audit/legal-hold records: preserve when the supplied condition applies; never delete merely to maximize deletion.
- Shared support messages: redact rather than delete when shared context must remain.
- Analytics/telemetry: anonymize when still attributable.
- Backup/archive: retain only under the rule's condition and ensure the affected data cannot be restored unsafely.
- Active sync/import/index/restore: disable or block before dependent record remediation.
- `COMPLETE`: verification steps only, each backed by eligible evidence.
- `INCOMPLETE`: findings cite evidence; proposed remediation and future verification use `evidence_id=""`.

## Ordering algorithm

Construct a remediation dependency DAG from `CaseContext`. Add process-control actions before affected data changes. Add downstream-copy actions before source actions when required. Topologically sort with `(phase priority, system_id, resource_id, operation)` as the deterministic tie-breaker. Detect cycles and use an explicit safe cycle-breaking rule or block certification when no safe order is established. Generate future verification immediately after the full remediation plan, not interleaved with findings.

## Model boundary

No model call is allowed in policy evaluation, status assignment, step generation, validation, or CSV export. These functions must be deterministic and explainable. If an upstream model-assisted proposal remains uncertain, treat the context as unresolved rather than letting the model fill the gap.

## Tests you must own

- Valid retained tombstone is complete; tombstone exposing prohibited PII/hash is incomplete.
- Required retained record remains present and receives evidence-backed verification.
- Shared record uses redaction; attributable analytics uses anonymization.
- Surviving copy produces finding, remediation, and verification.
- Active flow and restore risk are controlled before record changes.
- Every remediated object receives a verification.
- Future actions have empty evidence IDs; findings/complete verifications have eligible IDs.
- Unsupported phase/operation/state or extra/missing step fields fail validation.
- Step numbering and ordering are exact and stable under input shuffling.
- Non-deletion gives exactly `NOT_APPLICABLE` and `[]`.
- Contradiction/insufficient evidence cannot become false `COMPLETE`.
- Export rejects duplicates, missing cases, invalid JSON, incorrect columns, unsorted rows, and unresolved internal answers.
- All official public samples are scored without introducing case-ID-specific logic.

## Acceptance criteria

- Policy is data-driven from the supplied rules and produces an explanation trace.
- No invalid operation/state pair can reach export.
- False completion is treated as the highest-severity planning defect.
- Identical context and rules produce byte-stable `steps_json`.
- Contract and planning tests pass in Docker without an API key.
- The exporter can enforce the required case set supplied by the caller rather than assuming a count in unit tests.

## AI coding agent start prompt

```text
Read AGENTS.md, problem_statement.md, SHARED_BUILD_CONTRACT.md, and this document. Implement only code/slam/planning and tests/planning for contract 1.0.0. Start with an output/step validator and failing policy fixtures. Consume CaseContext and implement deterministic Judge–Evidence–Verify behavior from deletion_rules.csv. Do not parse evidence, resolve identity, or call an AI model. Enforce exact statuses, phases, operations, states, evidence rules, dependency ordering, numbering, JSON serialization, and CSV columns. Unknown or conflicted context must never become false COMPLETE. Do not hardcode sample IDs/answers. Do not edit contracts or locks; request changes. Run contract tests, owned tests, Ruff, and mypy in Docker and finish with changed files, command results, failures/limitations, and contract requests.
```

## Delivery to Lalith

Push branch `satvika` and send the commit hash, policy coverage table, validator/export test results, unresolved policy interpretations, and contract-change requests. Manya reviews the planning work; Satvika reviews Ashish and Lalith as assigned in the shared contract.
