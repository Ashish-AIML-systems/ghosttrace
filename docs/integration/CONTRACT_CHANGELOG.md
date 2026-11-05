# Contract changelog

Every change to `code/slam/contracts.py` or `contracts/**` gets an entry here **in the same PR**
(CI enforces it). The identity of a contract is its `contracts/SCHEMA_SHA256`, not the version
string: the version has stayed `1.0.0` while the schema changed, which is how two incompatible
"1.0.0" contracts came to exist (entry B1). Contract 1.1.0 is the current additive interface.

An entry needs: the new hash, the commit, who approved (`contract_approver` in
[`ownership.toml`](ownership.toml)), what changed for each consumer, and the date all four owners were told.

## Current baseline

| Id | Schema hash | Commit | Where it lives today |
|---|---|---|---|
| **1.1.0** | `95cfa189ae07490fe5b42527dc08990b50779d83fa7a82965caefeeb28275a23` | working tree | current local schema; pending PR and branch updates |
| **B1 / 1.0.0** | `7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd` | `0bbee13` | **`origin/dev`** (since `2666ffe`), `origin/codex/dev-ingestion-contracts`, `origin/ashish` |
| B0 | `1d4ca61a9ff698a68e806f3dc28c428880c93e56ec044f804ebb5003f4de9735` | `0e27272` | historical only; superseded on `lalith` by B1 |

`origin/main` has no contracts. `origin/manya` has B1 and reconstruction work; `origin/satvika` has not
yet adopted the contract. Snapshot of 2026-11-04; run `python scripts/delivery_check.py status` for live refs.

## Entries (newest first)

### 1.1.0 - Shared planner/reconstruction interfaces - 2026-11-04

Author and approver: Lalith. Additive contract change from B1. Adds `policy_rules` and
`evidence_captured_at` to `CaseContext`. `policy_rules` carries the supplied rules into the pure planner.
`evidence_captured_at` maps participant-visible `file_id`, `activity_id`, and `audit_id` citations to
aware timestamps so planning and validation can enforce each request's `audit_at` cutoff. Observation
hashes remain separate and are never output citations. The exporter interface is
`export_output_csv(answers, required_case_ids, path) -> None`.

Affected consumers: Manya populates the new fields; Satvika consumes policy rules and validates citation
IDs/times; Lalith's orchestrator and output validator enforce the same cutoff. Ashish's bundle shape is
unchanged. All owners must update to this schema hash before integration. Lalith approved this change.
Schema hash: `95cfa189ae07490fe5b42527dc08990b50779d83fa7a82965caefeeb28275a23`.

### B1 - frozen 1.0.0 baseline - 2026-11-04

`7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd` is the canonical schema for
contract 1.0.0. All new schema changes increment the version.

### B1 - `0bbee13` "Expand ingestion contracts and image provider" - 2026-11-04

Author: Lalith. Version string **unchanged** (`1.0.0`). Breaking for any code written against B0.
Rationale and decisions: [`docs/CONTRACT_DECISIONS.md`](../CONTRACT_DECISIONS.md).

| Model | B0 -> B1 | Who is affected |
|---|---|---|
| `IssueSeverity` | `WARNING/ERROR/BLOCKING` (uppercase) -> `info/warning/error` (lowercase); `BLOCKING` removed | everyone who reads issues |
| `SourceRecord` | `kind: str` -> `SourceKind` enum; `relative_path` -> `path`; `parser_name/parser_version` replaced by `parse_status` and `extraction` | Ashish, Manya, Satvika |
| `SourceSpan` | free-text `locator` -> exactly one of `table_row`, `line_range`, `json_path`, `pdf_position`, `image_region`; quote limit 1000 -> 500 | Manya, Satvika |
| `Observation` | `state` -> `observed_state`; `effective_at` -> `effective_time`; `nature` -> `source_kind`; `provenance` -> `spans`; `observation_id` must be 64-hex SHA-256; new `subject_hints`, `extraction` | Manya, Satvika |
| `IdentitySnapshot`, `IdentityChange`, `ActivityEvent` | renamed `CurrentIdentity`, `IdentityChangeEvent` (`event_id` -> `audit_id`), `Activity`; `CurrentIdentity` now has `name`, `email`, `email_normalized`, `phone`, `email_hash`. Old names kept as import aliases | Manya |
| `IngestionIssue` | `issue_id` removed; optional `locator` added | Ashish, Manya |
| New | `ParseStatus`, `SourceKind`, `TableRowLocator`, `LineRangeLocator`, `PdfPositionLocator`, `ImageRegionLocator`, `ExtractionProvenance` | everyone |

`ModelProvider` also gained image input in the same commit (`runtime/provider.py`).

**Status:** B1 reached `dev` through PR #3 (`2666ffe`, merged by Lalith) as contract 1.0.0. Contract
1.1.0 is the current local schema after the additive interface change above; it is not yet published.
Teammates must merge this update before implementing planner seams.

Approval for 1.1.0: recorded by Lalith. All four owners told: pending.

### B0 - `0e27272` "Build shared SLAM foundation contracts" - 2026-11-04

Initial executable contract. Hash `1d4ca61a...` as above.

## Open contract requests (not yet applied)

| Request | From | Why | Decision |
|---|---|---|---|
| Allow a `failed` `SourceRecord` for a manifest row with an unusable hash or time | Ashish | Such rows exist only as error issues today | open |
| Q1 - get `PolicyRule`s to `plan()` | Satvika | `CaseContext.policy_rules` added in 1.1.0 | resolved |
| Q2 - define what `*_evidence_ids` contain | Manya, Satvika | Visible IDs only; capture times in `CaseContext.evidence_captured_at` | resolved |
| Q3 - freeze the exporter's signature | Satvika, Lalith | `export_output_csv(answers, required_case_ids, path) -> None` | resolved |
