---
owner: satvika
workstream: Policy, decision, ordered steps, CSV export
status: NOT_STARTED
contract_version: 1.1.0
contract_sha256: 95cfa189ae07490fe5b42527dc08990b50779d83fa7a82965caefeeb28275a23
built_on: none
merge_after: ashish, manya
last_updated: 2026-11-04
---

# Satvika - policy, decision, steps, export

<!--
Pre-filled by the integrator from team_handoff/03_SATVIKA_POLICY_PLANNING.md and from reading
code/slam/contracts.py. Replace this file's contents on your first PR from branch `satvika`, set
status to IN_PROGRESS and fill every section (CI rejects TODO/TBD placeholders and empty sections).
-->

## Requires from others

| From | What | Why | Status |
|---|---|---|---|
| Lalith / integrator | Start from `dev` and adopt contract 1.1.0 | The current shared contract includes policy rules and timestamped participant-visible citations in `CaseContext` | Required before implementation/integration; use the current `contracts/SCHEMA_SHA256` |
| Lalith / integrator | Contract 1.1.0 interface and exporter signature | `CaseContext.policy_rules`, `evidence_captured_at`, visible citation IDs, and `export_output_csv(answers, required_case_ids, path) -> None` are now specified | Implement against current contract; reject evidence citations missing from the map or later than `request.audit_at` |
| Manya | `CaseContext` | Your only input | Not started; build against fixtures of the contract type |
| Ashish | `PolicyRule` rows (15 in the supplied dataset): `rule_id`, `category`, `required_action`, `condition`, `attributes`; ingestion's `observed_state` vocabulary | Planning, not ingestion, maps free-string states to the closed output states (`CONTRACT_DECISIONS.md`) | Merged in `dev` @ `2666ffe`; vocabulary in `INGESTION_PLAN.md` section 3 |
| Ashish | You review ingestion | Cross-review assignment in `SHARED_BUILD_CONTRACT.md` | PARTLY: your comment-only review of PR #3 said "good"; record any findings against `INGESTION_PLAN.md` sections 3 and 5 here |

## Provides to others

| To | What | Where | They must honour |
|---|---|---|---|
| Lalith / orchestrator | `plan(context) -> CaseAnswer` | `code/slam/planning/api.py` | Never returns a convenient status: unresolved or conflicted context gives `ready_for_export=False` with `blocking_issues`; `NOT_APPLICABLE` always has no steps |
| Lalith / orchestrator | CSV exporter that enforces the required case set | `code/slam/planning/export.py` | Rejects duplicates, missing cases, unsorted rows, invalid JSON, wrong columns, unresolved answers; takes the required case ids from the caller |
| Lalith / evaluation | Same step/operation/state tables as `contracts.py` | `code/slam/planning/steps.py` | One source of truth: do not fork the `_OPERATION_RULES` table |
| Everyone | Policy coverage table and an explanation trace in `CaseAnswer.trace` | delivery note, `trace` | Byte-stable `steps_json` for identical input |
