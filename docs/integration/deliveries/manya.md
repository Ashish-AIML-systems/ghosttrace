---
owner: manya
workstream: Request intent, identity, temporal state, dependency graph
status: NOT_STARTED
contract_version: 1.1.0
contract_sha256: 95cfa189ae07490fe5b42527dc08990b50779d83fa7a82965caefeeb28275a23
built_on: none
merge_after: ashish
last_updated: 2026-11-04
---

# Manya - request intent, identity, temporal state, graph

<!--
Pre-filled by the integrator from team_handoff/02_MANYA_IDENTITY_TIMELINE.md and from reading
code/slam/contracts.py. Replace this file's contents on your first PR from branch `manya`, set
status to IN_PROGRESS and fill every section (CI rejects TODO/TBD placeholders and empty sections).
-->

## Requires from others

| From | What | Why | Status |
|---|---|---|---|
| Lalith / integrator | Contract 1.1.0 adoption | `origin/manya` (`152b0a2`) contains reconstruction implementation/tests built on contract 1.0.0; `CaseContext` gained policy rules and evidence timestamps in 1.1.0 | Update branch to 1.1.0, populate both new fields, refresh hash, rerun owned checks |
| Ashish | `EvidenceBundle` from `ingest()` and `AuditRequest` rows from `load_requests()` | Your only input | MET: merged in `dev` @ `2666ffe`; read `INGESTION_PLAN.md` section 3 and `CORPUS_REPORT.md` before using states |
| Lalith / integrator | Contract 1.1.0 interface | `CaseContext.policy_rules` carries exact rules; `evidence_captured_at` maps participant-visible file/activity/audit IDs to aware timestamps. Evidence ID tuples must never contain observation hashes. | Required before integration; copy rules and complete timestamp map, including later evidence so the planner can enforce `audit_at` |
| Lalith | Fake `ModelProvider` for tests; approval for any new dependency | RapidFuzz is mentioned in your handoff but is not in `uv.lock` (`networkx` is) | OPEN until requested |

## Provides to others

| To | What | Where | They must honour |
|---|---|---|---|
| Satvika | `CaseContext` from `reconstruct(request, bundle, *, provider=None)` | `code/slam/reconstruction/api.py` | `request_intent`, `subject_id`, `identity_links`, `eligible_observation_ids`, `excluded_future_observation_ids`, `resource_states`, `active_flows`, `restore_risks`, `coverage_issues`, `unresolved_conflicts`. Conflicts are preserved, uncertainty is flagged, absence needs positive eligible evidence; no status, no steps, no policy action |
| Lalith | A pure, deterministic per-request function | same | No hidden global state, so the orchestrator can isolate and retry cases; same input gives identical output under row shuffling |
| Lalith | Fixtures for the evaluation harness | `tests/fixtures/reconstruction/**` | Expected results written independently of the code under test |
