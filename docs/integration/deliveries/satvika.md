---
owner: satvika
workstream: Policy, decision, ordered steps, CSV export
status: NOT_STARTED
contract_version: 1.0.0
contract_sha256: 7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd
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
| Lalith / integrator | Start from `dev`, **not** `origin/lalith` | Same reason as Manya: the contract shape differs between the two (`CONTRACT_CHANGELOG.md`) | MET: `dev` @ `2666ffe`. Your branch is still at the initial commit, so `git merge origin/dev` first |
| Integrator / Lalith | Answer to open question Q1: how `PolicyRule`s reach `plan()` | `plan(context: CaseContext)` is frozen and `CaseContext` has no rules, yet your flow starts with "load the exact rules" and `ResourceState.applicable_rule_id` only names a rule | OPEN, **decide before you write `policy.py`** |
| Integrator / Lalith | Answer to open question Q2: what `*_evidence_ids` hold | `Step.evidence_id` must be a participant-visible file_id/activity_id/audit_id; eligibility needs a capture time | OPEN |
| Integrator / Lalith | Answer to open question Q3: the exporter's name, signature and call site | The frozen interface lists `ingest`, `reconstruct`, `plan` only; `main.py` and the orchestrator need to call your CSV export | OPEN |
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
