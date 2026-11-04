---
owner: ashish
workstream: Evidence ingestion
status: INTEGRATED
contract_version: 1.0.0
contract_sha256: 7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd
built_on: 0bbee13
merge_after: none
last_updated: 2026-11-04
---

# Ashish - evidence ingestion

<!-- Living document: update it in every PR from your branch (CI enforces it). -->

## Delivers

- `ingest(dataset_dir, *, cache_dir=None, provider=None) -> EvidenceBundle` and
  `load_requests(dataset_dir) -> tuple[AuditRequest, ...]`, with the frozen signatures, in
  `code/slam/ingestion/api.py`, re-exported from `slam.ingestion`. Also `ingest_with_ocr(...)`
  so OCR can be injected in tests; `ingest` itself keeps the frozen signature.
- Parsers for JSON, six log layouts, text, PDF (text layer), image (OCR first, bounded model
  fallback) and SQL snapshots (deny-by-default SQLite sandbox); the normalizer and `vocab.py`
  (the only place vocabulary is applied); a SQLite/FTS5 ledger; an integrity-checked extraction
  cache; a counts-only corpus report (`python -m slam.ingestion.report`).
- Source of truth for the design and the downstream rules:
  `code/slam/ingestion/INGESTION_PLAN.md`. Coverage: `CORPUS_REPORT.md`.
- Commit `bfe33f4` on branch `ashish`. **Merged into `dev` as `2666ffe`** by Lalith through PR #3 on
  2026-11-04 16:31 UTC. PR #3 changed 98 files: 47 are ingestion, the rest is the foundation baseline
  `0bbee13` that `dev` did not have yet.
- That merge predates this mechanism: it had no delivery note and no CI ran on it (`dev` had no
  workflows), so the results under `Verification` are Ashish's own Docker run, not a recorded CI result.

## Cross-owner edits

- `tests/contracts/test_owned_boundaries.py` (Lalith's): the test that expected `ingest()` to raise
  `NotImplementedError` described the old stub. It now asserts that a dataset with no manifest
  returns an error issue instead of a silent empty bundle. Lalith to confirm.

## Requires from others

| From | What | Why | Status |
|---|---|---|---|
| Lalith / integrator | Baseline `0bbee13` present on the target branch | Ingestion is built on it | MET: it is in `dev` since `2666ffe` |
| Lalith | Confirm the replaced stub test above | Cross-owner edit | MET implicitly: Lalith approved and merged PR #3 with it; no separate sign-off recorded |
| Lalith | Decide the contract request below | Rejected manifest rows have no `SourceRecord` | OPEN, not blocking |
| Satvika | Cross-review of ingestion against `INGESTION_PLAN.md` sections 3 and 5 | Assigned in `SHARED_BUILD_CONTRACT.md` | PARTLY: Satvika left a comment-only review ("good") on PR #3; no findings against sections 3 and 5 are recorded |
| Lalith | `tesseract-ocr` in the Docker image | OCR only runs in Docker | MET (`Dockerfile`) |

## Provides to others

| To | What | Where | They must honour |
|---|---|---|---|
| Manya | `EvidenceBundle`: sources, observations, current identities, identity changes, activities, issues | `ingest()` | The nine rules in `INGESTION_PLAN.md` section 3. The ones people get wrong: `effective_time` is when the evidence *saw* the state (snapshot capture time), not when data last changed; evidence after `audit_at` is kept and **you** filter it; `NOT_FOUND` is a lookup result, not proof of deletion; `SNAPSHOT_SCOPE` observations are what make absence meaningful; systems are kept as logged (`profile_service` is not merged into `account_service` for you); document/OCR facts only say "this id appears with these identifiers"; `uncertain=true` and `ingestion issues` must reach `coverage_issues`, never be dropped |
| Manya | `AuditRequest` rows | `load_requests()` | Emails keep original text; `email_normalized` is the matching key |
| Satvika | `EvidenceBundle.policy_rules` (15 rules in the supplied dataset), `PolicyRule.required_action/condition/attributes` | bundle | `plan(context)` does not receive the bundle: see open question Q1 in `DEPENDENCY_MATRIX.md` |
| Satvika | Participant-visible ids usable as citations: `SourceRecord.source_id` (file_id), `Activity.activity_id`, `IdentityChangeEvent.audit_id`; `SourceRecord.captured_at` for eligibility | bundle | Which of these ids appear in `*_evidence_ids` is open question Q2 |
| Lalith | `ingest` once per run, `load_requests`, corpus report, ledger and extraction cache under `cache_dir` | `slam.ingestion` | Orchestrator should call `ingest` once and reuse the bundle for all 518 requests |

## Contract and dependency requests

- Contract request (not applied): allow a `failed` `SourceRecord` for a manifest row whose hash or
  time is unusable, so such rows are accounted for as sources and not only as error issues.
- Dependencies: no change relative to the baseline. `pypdf`, `Pillow` and `pytesseract` were added
  by `0bbee13`; the Debian package `tesseract-ocr` is already in the `Dockerfile`.

## Verification

| Check | Result | Where |
|---|---|---|
| `docker compose run --rm slam-dev ruff check code tests` | all checks passed | Docker, Tesseract 5.3.0, 2026-11-04, `INGESTION_PLAN.md` section 4 |
| `docker compose run --rm slam-dev mypy code/slam` (strict) | no issues in 38 source files | same |
| `docker compose run --rm slam-dev pytest -q` | 380 passed | same |
| Real dataset | 94/94 sources `parsed`, 3,020 observations, no error issues, byte-identical re-run | same |
| `python -m pytest -q` on the Windows host, no Tesseract, `.venv` from `uv.lock` | 421 passed (380 existing + 41 in `tests/integration`); the 11 images fail explicitly with `OCR_ENGINE_UNAVAILABLE` and a test asserts it | host, 2026-11-04, after PR #3 |

No real model API call was ever made; every model path is verified with the fake provider only.

## Known limits

- The vision fallback is unmeasured on a real API. On this corpus OCR resolves every image, so the
  model path is never exercised by real data.
- OCR association is heuristic; ambiguous cases are flagged `uncertain` or
  `IMAGE_ASSOCIATION_UNRESOLVED`, not hidden. Scanned PDFs are not OCR'd (`PDF_PAGE_NO_TEXT`).
- `vocab.py` is derived from this corpus. A hidden dataset with new collections raises
  `CATEGORY_UNMAPPED` and needs a reviewed vocabulary addition.
- Rejected manifest rows have no `SourceRecord` (contract request above).

## Integration notes

- **Already merged first** (`dev` @ `2666ffe`); Manya and Satvika consume it and start from `dev`.
- **Collision file.** `dev` now carries Ashish's version of `tests/contracts/test_owned_boundaries.py`.
  Manya (reconstruction stub test) and Satvika (planning stub test) will each replace their own hunk in
  the same file. Resolve in merge order and keep every owner's hunk; do not take one side wholesale.
- **Gates after merging.** `docker compose run --rm slam-dev pytest -q tests/contracts tests/ingestion`,
  then `ruff check code tests scripts` and `mypy code/slam code/main.py`. The real-dataset tests need
  `dataset/` present in the mounted checkout.
- **Windows quirks.** `scripts/export_contracts.py` rewrites `contracts/` with CRLF; restore with
  `git checkout -- contracts/` (not real drift). `python -m slam.ingestion.report` needs
  `PYTHONPATH=code`. OCR tests that need Tesseract only run in Docker.
