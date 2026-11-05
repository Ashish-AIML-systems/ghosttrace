# Who needs what from whom

This is the map the integrator uses to decide *what a merge will change for the other three*. Each
owner's live version of their row is the **Requires from others** / **Provides to others** tables in
their [delivery note](deliveries/); when the two disagree, the note wins and this page is updated.

Owners and paths: [`ownership.toml`](ownership.toml). Contract identity and history:
[`CONTRACT_CHANGELOG.md`](CONTRACT_CHANGELOG.md).

## 1. The data flow, with the owner of each hop

```text
dataset/ ──► ingest() ──► EvidenceBundle ──► reconstruct() ──► CaseContext ──► plan() ──► CaseAnswer ──► export ──► output.csv
            Ashish        (Ashish)           Manya            (Manya)         Satvika    (Satvika)       Satvika?
                                                      all of it composed, configured, metered and scored by Lalith
```

## 2. Who needs what

Read a row as "**consumer** needs **thing** from **producer**".

| Consumer | Producer | Needs | Interface | What the consumer must honour (the part that does not show up as a type error) |
|---|---|---|---|---|
| Manya | Ashish | The evidence | `ingest() -> EvidenceBundle`; `load_requests() -> tuple[AuditRequest, ...]` | `effective_time` is the time the evidence *saw* the state; evidence after `audit_at` is kept and must be filtered by Manya; `NOT_FOUND` is not proof of absence; `SNAPSHOT_SCOPE` is what makes absence meaningful; systems are kept as logged (`profile_service` is not folded into `account_service`); document and OCR facts only say "this id appears with these identifiers"; ingestion issues and `uncertain` flags must surface as `coverage_issues` |
| Satvika | Ashish | Rules and citation ids | `EvidenceBundle.policy_rules`, `SourceRecord`, `Activity`, `IdentityChangeEvent` | Apply policy fields verbatim; evidence ids are participant-visible file/activity/audit IDs; planning maps free-string `observed_state` to closed output states |
| Satvika | Manya | The case | `reconstruct() -> CaseContext` | Contradiction and uncertainty arrive as `unresolved_conflicts`, `coverage_issues`, `ResourceState.uncertain` and must block certification; `active_flows` / `restore_risks` are what force `DISABLE_DATA_FLOW` / `BLOCK_RESTORE` before record changes |
| Manya | Lalith | Contract, provider, fixtures | `contracts.py`, `ModelProvider`, fake provider | The model proposes request intent or an identity hint only; deterministic code decides |
| Ashish | Lalith | Contract, provider, cache key, Docker | `contracts.py`, `ModelProvider` (image input), `build_model_cache_key`, `tesseract-ocr` in the image | No real model call in tests |
| Satvika | Lalith | `Step` / `CaseAnswer` validators | `contracts.py` | One operation/state table; do not fork `_OPERATION_RULES` |
| Lalith | Ashish | Ingest once, request loader, corpus report | `ingest`, `load_requests`, `slam.ingestion.report` | The orchestrator reuses one bundle for all 518 cases |
| Lalith | Manya | A pure, deterministic `reconstruct` | `code/slam/reconstruction/api.py` | A failure in one case must not stop the others |
| Lalith | Satvika | `plan` and the CSV exporter | `code/slam/planning/api.py`, `export.py` | Exporter signature: `export_output_csv(answers, required_case_ids, path) -> None` |
| Everyone | Lalith | Approval of `contracts.py`, `pyproject.toml`, `uv.lock`, Docker files | change request in the delivery note | Nobody edits these directly (`ownership.toml`) |
| Integrator | Everyone | A current delivery note, a commit hash, passing owned tests | PR + note | `merge_after`, `built_on`, `Integration notes` are read by the preflight |

Review assignments from `SHARED_BUILD_CONTRACT.md`: Satvika reviews Ashish; Ashish reviews Manya;
Manya reviews Satvika; Satvika reviews Lalith's runtime and integration. All four review packaging.

## 3. Files where two workstreams collide

The preflight prints a warning for any branch that touches one of these (list lives in `ownership.toml`).

| File | Who edits it | What will happen | Resolution |
|---|---|---|---|
| `tests/contracts/test_owned_boundaries.py` | Ashish (already on `dev`), Manya and Satvika each replace *their* stub test; Lalith owns the file | Adjacent-hunk textual conflicts, likely once both remaining branches touch it | Merge in order; keep every owner's hunk. Better: split it into one file per workstream in a small PR now, so the conflict cannot occur |
| `pyproject.toml`, `uv.lock` | Lalith only | A teammate who needs a package (e.g. RapidFuzz for Manya) cannot import it in CI, because `uv sync --frozen` | Dependency request in the note; the integrator lands it on `dev` first; teammates merge `dev` |
| `code/slam/contracts.py`, `contracts/**` | Lalith only, with notice to all | Hash mismatch in every other note after the change | Changelog entry in the same PR; every owner re-verifies and updates `contract_sha256` |
| `code/main.py`, `code/slam/runtime/orchestrator.py` | Lalith / integration | `main.py --dataset` still exits with "must be integrated"; wiring touches Lalith's files | Integrator wires after all three modules merge, declared as a cross-owner edit |
| `README.md` | Lalith | Each owner is tempted to add run instructions | Put them in your delivery note; the README is edited once at the end |

## 4. Interface decisions - agreed by Lalith on 2026-11-04

Found by reading `code/slam/contracts.py` at `0bbee13` and every document in the repo. These decisions
are recorded here; the additive contract update uses version 1.1.0.

### Q1 - How do the policy rules reach `plan()`? (resolved)

- `plan(context: CaseContext) -> CaseAnswer` is a frozen signature (`SHARED_BUILD_CONTRACT.md`).
- `CaseContext` carries observation ids, resource states and edges, but no `PolicyRule`s, and
  `ResourceState.applicable_rule_id` is only a name. The rules live on `EvidenceBundle.policy_rules`.
- Satvika's brief says "load the exact rules from `deletion_rules.csv`", but `plan()` has no dataset
  path, so reading the CSV would be hidden global state and would break determinism and tests.
- Options: (a) add `policy_rules: tuple[PolicyRule, ...]` to `CaseContext`, filled by `reconstruct`
  from the bundle - one field, fully typed, planning stays a pure function; (b) change the signature to
  `plan(context, *, rules)` - the orchestrator passes `bundle.policy_rules`; (c) planning loads the CSV itself.
- **Decision:** (a). `CaseContext.policy_rules` contains the exact `EvidenceBundle.policy_rules` tuple.
  Manya copies it during reconstruction; `plan(context)` remains pure and performs no file or global reads.

### Q2 - What do the `*_evidence_ids` fields contain? (resolved)

- `IdentityLink.evidence_ids`, `ResourceState.supporting_evidence_ids` / `conflicting_evidence_ids` and
  `GraphEdge.evidence_ids` are untyped `str` tuples with no stated meaning.
- `Step.evidence_id` in the output must be a participant-visible `file_id`, `activity_id` or `audit_id`
  (`AGENTS.md` 6.6), while an `Observation` is identified by a 64-hex hash and cites sources through its spans.
- If Manya puts `observation_id`s there and Satvika copies them, the output contains hashes and every
  finding is an invalid citation, with no type error anywhere.
- **Decision:** evidence-ID fields and `Step.evidence_id` hold only participant-visible `file_id`,
  `activity_id`, or `audit_id`; never `observation_id`. `eligible_observation_ids` is specifically for
  observation hashes. `CaseContext.evidence_captured_at` maps each visible evidence ID to its aware
  capture/event time. Manya supplies the map from bundle sources, activities, and identity changes;
  Satvika excludes citations later than `request.audit_at`. The orchestrator/export validator also rejects
  citations absent from the map or after the cutoff.

### Q3 - Who writes `output.csv`, and with what signature? (resolved)

- Frozen interfaces are `ingest`, `reconstruct`, `plan`. The layout puts export in
  `planning/export.py`, the validator in `evaluation/validator.py`, the call site in `main.py` /
  `orchestrator.py`; no signature is written down.
- **Decision:** Satvika provides `export_output_csv(answers, required_case_ids, path) -> None` that
  raises on any defect; Lalith's validator re-reads the written file independently; the integrator calls
  both from `main.py`.

### Q4 - Which contract is "1.0.0"? (resolved)

- Two incompatible schemas carried the same version: historical B0 and B1. B1 is the canonical 1.0.0
  baseline; the new additive interface is contract 1.1.0.
- **Decision:** B1 was the exact 1.0.0 baseline. This additive interface update is version 1.1.0;
  teams must update to its contract hash before integration. Branch from `dev`.

## 5. Inconsistencies found in the existing documents

| Where | Says | Reality / conflict | Suggested fix |
|---|---|---|---|
| `SHARED_BUILD_CONTRACT.md`, `04_LALITH...md`, workflow warning text, `INGESTION_PLAN.md` | Lalith integrates | The integrator role is now held by the person named in `ownership.toml` `[roles]` | Update those lines once the team confirms; until then `ownership.toml` is the authority for this mechanism |
| `SHARED_BUILD_CONTRACT.md` layout | evaluation code in `code/slam/evaluation/` | `04_LALITH...md` says `code/evaluation/**` | Both listed as Lalith's in `ownership.toml`; pick one |
| `README.md` | teammate start point | must follow the published shared branch | Branch from `dev` and use the schema hash |
| `SHARED_BUILD_CONTRACT.md` | contract version | schemas changed under the old version | Version 1.1.0 and hash are current |
