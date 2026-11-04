# Contract changelog

Every change to `code/slam/contracts.py` or `contracts/**` gets an entry here **in the same PR**
(CI enforces it). The identity of a contract is its `contracts/SCHEMA_SHA256`, not the version
string: the version has stayed `1.0.0` while the schema changed, which is how two incompatible
"1.0.0" contracts came to exist (entry B1).

An entry needs: the new hash, the commit, who approved (`contract_approver` in
[`ownership.toml`](ownership.toml)), what changed for each consumer, and the date all four owners were told.

## Current baseline

| Id | Schema hash | Commit | Where it lives today |
|---|---|---|---|
| **B1** | `7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd` | `0bbee13` | **`origin/dev`** (since `2666ffe`), `origin/codex/dev-ingestion-contracts`, `origin/ashish` |
| B0 | `1d4ca61a9ff698a68e806f3dc28c428880c93e56ec044f804ebb5003f4de9735` | `0e27272` | `origin/lalith` only, reached by anyone following the README's "branch from `lalith`" |

`main` has neither (no `contracts/`). `manya` and `satvika` are still at the initial commit.
Snapshot of 2026-11-04 after PR #3; `python scripts/delivery_check.py status` shows the live picture.

## Entries (newest first)

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

**Status:** B1 reached `dev` through PR #3 (`2666ffe`, merged by Lalith), so it is the working baseline
de facto. Still to do:

- Record the explicit decision here. Recommended: declare B1 the frozen `1.0.0` and treat the hash as
  the identity from now on. Bumping the version would instead force edits to
  `EvidenceBundle.require_current_contract`, fixtures and every note, for no extra safety beyond what the
  hash gate already gives.
- The README still tells teammates to branch from `origin/lalith`, which is B0; `origin/lalith` has not
  yet merged `dev`. Manya and Satvika must start from `dev`.

Approval: implicit (Lalith merged it); explicit declaration pending. All four told: pending.

### B0 - `0e27272` "Build shared SLAM foundation contracts" - 2026-11-04

Initial executable contract. Hash `1d4ca61a...` as above.

## Open contract requests (not yet applied)

| Request | From | Why | Decision |
|---|---|---|---|
| Allow a `failed` `SourceRecord` for a manifest row with an unusable hash or time | Ashish | Such rows exist only as error issues today | open |
| Q1 - get `PolicyRule`s to `plan()` | Satvika (found by integrator) | `CaseContext` has no rules and `plan()` takes only a context | open, see [`DEPENDENCY_MATRIX.md`](DEPENDENCY_MATRIX.md) |
| Q2 - define what `*_evidence_ids` contain | Manya, Satvika | Output needs participant-visible ids | open |
| Q3 - freeze the exporter's signature | Satvika, Lalith | Not among the frozen interfaces | open |
