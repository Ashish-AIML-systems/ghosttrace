---
owner: manya
workstream: Request intent, identity, temporal state, dependency graph
status: NOT_STARTED
contract_version: 1.0.0
contract_sha256: 7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd
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
| Lalith / integrator | Start from `dev`, **not** `origin/lalith` | `origin/lalith` is still the earlier shape of contract 1.0.0 (hash `1d4ca61a...`); `dev` has `7beb34d3...`, which renamed `Observation.state` to `observed_state`, `effective_at` to `effective_time`, `provenance` to `spans`, `SourceRecord.relative_path` to `path`, and lowercased issue severities. See `CONTRACT_CHANGELOG.md` | MET: `dev` @ `2666ffe`. Your branch is still at the initial commit, so `git merge origin/dev` first |
| Ashish | `EvidenceBundle` from `ingest()` and `AuditRequest` rows from `load_requests()` | Your only input | MET: merged in `dev` @ `2666ffe`; read `INGESTION_PLAN.md` section 3 and `CORPUS_REPORT.md` before using states |
| Integrator / Lalith | Answer to open question Q2: what `*_evidence_ids` hold (file_id/activity_id/audit_id or observation_id) | You fill `IdentityLink.evidence_ids`, `ResourceState.supporting_evidence_ids`, `GraphEdge.evidence_ids`; Satvika copies them into `Step.evidence_id` | OPEN, decide before you return any `ResourceState` |
| Lalith | Fake `ModelProvider` for tests; approval for any new dependency | RapidFuzz is mentioned in your handoff but is not in `uv.lock` (`networkx` is) | OPEN until requested |

## Provides to others

| To | What | Where | They must honour |
|---|---|---|---|
| Satvika | `CaseContext` from `reconstruct(request, bundle, *, provider=None)` | `code/slam/reconstruction/api.py` | `request_intent`, `subject_id`, `identity_links`, `eligible_observation_ids`, `excluded_future_observation_ids`, `resource_states`, `active_flows`, `restore_risks`, `coverage_issues`, `unresolved_conflicts`. Conflicts are preserved, uncertainty is flagged, absence needs positive eligible evidence; no status, no steps, no policy action |
| Lalith | A pure, deterministic per-request function | same | No hidden global state, so the orchestrator can isolate and retry cases; same input gives identical output under row shuffling |
| Lalith | Fixtures for the evaluation harness | `tests/fixtures/reconstruction/**` | Expected results written independently of the code under test |
