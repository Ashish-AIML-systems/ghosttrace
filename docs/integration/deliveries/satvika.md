---
owner: satvika
workstream: Policy, decision, ordered steps, CSV export
status: IN_PROGRESS
contract_version: 1.0.0
contract_sha256: 7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd
built_on: 0d02a57be96b70f055e69e7c0d16adb652b7b882
merge_after: ashish, manya
last_updated: 2026-11-04
---

# Satvika - policy, decision, steps, export

## Delivers

- `validate_answer(answer, *, eligible_evidence_ids=None) -> CaseAnswer` in `code/slam/planning/validation.py` checks contract invariants, evidence on findings and complete-case verifications, future-action citation rules, and optional evidence eligibility. It makes no policy decision.
- Synthetic validator coverage in `tests/planning/test_validation.py` for valid incomplete/complete/non-applicable answers, invalid operation/state pairs, step numbering and phase order, evidence rules, ineligible evidence, and extra fields.
- This is the first planning slice; policy loading, treatment decisions, plan generation, and CSV export are not implemented yet.

## Cross-owner edits

None.

## Requires from others

| From | What | Why | Status |
|---|---|---|---|
| Ashish / integrator | Decide how `PolicyRule`s reach `plan()` | The frozen `CaseContext` has no policy rules; this blocks policy implementation | OPEN (Q1) |
| Manya / integrator | Confirm evidence IDs and eligibility guarantees | Findings and completed verifications must cite eligible participant-visible evidence | OPEN (Q2; Manya's note defines visible IDs as source/activity/audit IDs) |
| Lalith / integrator | Confirm exporter signature and call site | Needed before implementing export and orchestration wiring | OPEN (Q3) |
| Ashish | Supply/locate the participant policy rule data and observed-state vocabulary | The rules file is not present in this checkout | OPEN |

## Provides to others

| To | What | Where | They must honour |
|---|---|---|---|
| Lalith / orchestrator | `validate_answer` | `code/slam/planning/validation.py` | This validates a single answer; it does not decide status or replace `CaseAnswer` contract validation. Pass eligible evidence IDs when known. |

## Contract and dependency requests

None for this slice. Q1 may require a contract change; no contract was edited.

## Verification

Run in Docker on 2026-11-04:

- `docker compose run --rm slam-dev pytest -q tests/contracts tests/planning` — 38 passed.
- `docker compose run --rm slam-dev ruff check code/slam/planning tests/planning` — passed.
- `docker compose run --rm slam-dev mypy code/slam/planning` — passed.

## Known limits

- This validator does not implement the Judge–Evidence–Verify policy engine or export.
- Evidence eligibility is checked only when the caller supplies `eligible_evidence_ids`; resolution of the citation/eligibility contract remains open.
- `deletion_rules.csv` is absent from this checkout. Production policy behavior must wait for the participant rule data and Q1 resolution.

## Integration notes

- Work is on `satvika`, based on `origin/dev` at `0d02a57`; it must not be merged until Ashish and Manya are integrated, per `merge_after`.
- No tests outside contract and planning validator suites were run for this slice.
