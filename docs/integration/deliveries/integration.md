---
owner: integration
workstream: Integration, seam tests, CI, packaging
status: IN_PROGRESS
contract_version: 1.1.0
contract_sha256: 95cfa189ae07490fe5b42527dc08990b50779d83fa7a82965caefeeb28275a23
built_on: bf40c395628b508f43a61ebdd4178fefdce1ee0d
merge_after: none
last_updated: 2026-11-05
---

# Integration - mechanism, CI, merge record

<!-- Used by branches named integration/<topic>. The record at the bottom is append-only. -->

## Delivers

**This PR (on top of PR #5, already in `dev`):** quality pass measured against HackerRank's own 32 published answers.
- Ingestion: bulleted table rows are parsed as rows (explicit `NOT_FOUND`/`SUPPORT_ATTACHMENT` columns were ignored); `uploaded_by` is an owner identifier.
- Reconstruction: dynamic account/resource-to-person linking (`ownership.py`, `linking.py`, `absence.py`; windows and a status/result agreement are learned and held-out validated, nothing dataset-specific); retained records seen before the cutoff in later-exported files become uncited verification-only states; `reconstruct_with_links` added, frozen `reconstruct` unchanged.
- Planner: steps ordered exactly as the problem statement specifies.
- `scripts/build_submission.py` (code.zip + self-check), `scripts/smoke_test.py`, a diagram-conformance test, `docs/integration/RCA_ACCURACY.md`.

Branch `integration/reconstruction`: Manya's reconstruction merged intact (`152b0a2`, her `log.txt` left out), Lalith's evaluation scorer/validator/data-quality (`e3d16b4`) and Satvika's answer validator (`d70892e`) merged unchanged, plus:
- fixes to Manya's code found by running it on the real corpus: intent recall 20/32 -> 32/32 samples (0/518 unclear, 10 non-deletion = exactly the 10 CLASSIFY_REQUEST claims); activity edges no longer invert mitigations (116 flow + 58 restore edges) and 303 plain records no longer read as flows; info-level ingestion notes no longer block certification; identity as of `audit_at`; names no longer attach evidence; injection guard accepts plurals.
- `plan_case(context, bundle)` (policy + ordered steps), `export_output_csv`, `slam.pipeline.run/evaluate_samples`, `code/main.py --dataset dataset [--evaluate]`.
- **Account/resource linking (dynamic, no dataset-specific constants)**: `ownership.py` (L1 explicit owner index + L2 closure), `linking.py` (L3: timing signatures learned per (activity type, target system) from labelled pairs and enabled only after held-out validation with zero wrong), `absence.py` (ABSENT proven by the latest complete snapshot lacking the record); `reconstruct_with_links(request, bundle, link_model)` added, frozen `reconstruct` unchanged; ingestion maps `uploaded_by`. Plan: `docs/integration/ACCOUNT_LINKING_PLAN.md`.
- Contract 1.1.0 adoption (Lalith `fa6076a`): reconstruction fills `policy_rules` and `evidence_captured_at`; `plan(context)` works from the context alone.
- `scripts/smoke_test.py` and `docs/integration/RCA_ACCURACY.md` (root causes of the step-level gap).
- Tests: `tests/reconstruction/test_integration_fixes.py`, `tests/planning/test_engine.py`, `tests/integration/test_pipeline_seam.py`; reports in `evaluation/`.

## Cross-owner edits

Each file below is another owner's or unowned; the owner must confirm.

- `code/slam/ingestion/parsers/text_parser.py` - Ashish: parser fix for bulleted table rows (explicit state/category columns were ignored) and `uploaded_by` owner identifier; Ashish to confirm
- `code/slam/ingestion/vocab.py` - Ashish: parser fix for bulleted table rows (explicit state/category columns were ignored) and `uploaded_by` owner identifier; Ashish to confirm
- `code/slam/pipeline.py` - unowned new module: end-to-end run and link-model fitting; Lalith to confirm placement
- `code/slam/planning/engine.py` - Satvika: planner, exporter and evaluation cases written because plan() was still a stub; Satvika to review
- `code/slam/reconstruction/__init__.py` - Manya: merged from origin/manya, then fixed and extended (see Delivers); Manya to confirm
- `code/slam/reconstruction/absence.py` - Manya: merged from origin/manya, then fixed and extended (see Delivers); Manya to confirm
- `code/slam/reconstruction/api.py` - Manya: merged from origin/manya, then fixed and extended (see Delivers); Manya to confirm
- `code/slam/reconstruction/graph.py` - Manya: merged from origin/manya, then fixed and extended (see Delivers); Manya to confirm
- `code/slam/reconstruction/linking.py` - Manya: merged from origin/manya, then fixed and extended (see Delivers); Manya to confirm
- `code/slam/reconstruction/ownership.py` - Manya: merged from origin/manya, then fixed and extended (see Delivers); Manya to confirm
- `code/slam/reconstruction/timeline.py` - Manya: merged from origin/manya, then fixed and extended (see Delivers); Manya to confirm
- `evaluation/evaluation_report.md` - unowned: required submission reports (`main.py --evaluate`) and the side-by-side
- `evaluation/side_by_side_samples.md` - unowned: required submission reports (`main.py --evaluate`) and the side-by-side
- `evaluation/usage_report.md` - unowned: required submission reports (`main.py --evaluate`) and the side-by-side
- `scripts/build_submission.py` - unowned new tool (smoke test / code.zip builder with self-check)
- `scripts/smoke_test.py` - unowned new tool (smoke test / code.zip builder with self-check)
- `tests/ingestion/test_ingestion_text_and_doctext.py` - Ashish: parser fix for bulleted table rows (explicit state/category columns were ignored) and `uploaded_by` owner identifier; Ashish to confirm
- `tests/planning/test_engine.py` - Satvika: planner, exporter and evaluation cases written because plan() was still a stub; Satvika to review
- `tests/reconstruction/test_linking.py` - Manya: merged from origin/manya, then fixed and extended (see Delivers); Manya to confirm

## Requires from others

| From | What | Why | Status |
|---|---|---|---|
| Ashish, Manya, Satvika, Lalith | A current delivery note in every PR from their branch | The gate fails otherwise, and the preflight reads `merge_after`, `built_on` and `Integration notes` from it | Ashish done; others pre-filled |
| Lalith | Approve this mechanism and the two contract-related decisions in `DEPENDENCY_MATRIX.md` | `contracts.py` and `SHARED_BUILD_CONTRACT.md` are his | OPEN |

## Provides to others

| To | What | Where | They must honour |
|---|---|---|---|
| Everyone | Rules for what a PR must contain | `docs/integration/README.md`, `.github/PULL_REQUEST_TEMPLATE.md` | Update your own note in every PR; declare cross-owner edits |
| Everyone | A local way to run the same gate before pushing | `python scripts/delivery_check.py ci --base origin/dev --head HEAD --branch <you>` | Run it before opening the PR |
| Everyone | A merge order, conflict table and Q1-Q4 decisions | `INTEGRATOR_PLAYBOOK.md`, `DEPENDENCY_MATRIX.md` | Merges happen only through the integrator |

## Contract and dependency requests

None. The checker is standard-library only.

## Verification

Docker (`docker compose run --rm -T slam-dev ...`), 2026-11-05: `ruff check code tests scripts` clean; `mypy code/slam code/main.py` no issues in 54 files; `pytest -q` **552 passed, 18 skipped** (git-dependent, no git in image). `python code/main.py --dataset dataset --evaluate`: 518 rows, 0 failures, accepted by `validate_output_csv`, byte-identical on a fresh CRLF clone of the official repo. `python scripts/build_submission.py`: 133 files, self-check OK (no dataset, no archives, no `.env`).

Against HackerRank's own `sample_output.csv` (32 cases, official clone): status accuracy 0.906 (29/32), **false COMPLETE 0**, step precision 0.744, recall 0.663, **F1 0.701**, exact cases 11/32, field accuracy 0.771; 161 of 193 expected steps reproduced, evidence id correct on every matched step. HackerRank publishes no answers for the 518, so those cannot be scored.

## Known limits

- 7 hand-made teaching cases (`account_001`..`010`) use a different timing regime with too few labelled pairs to validate; 7 further cases stay ambiguous (request order, case number and activity-id order were tested as tiebreakers and are at chance).
- Support records: HackerRank's DELETE-vs-REDACT choice for 2 cases has no safe general rule; `support_replica` is not aliased to `support_platform`.
- The linker's validated groups were learned on the 518; the 32 public samples are only a proxy and some of their timing patterns differ.
- `usage_report.md` states 0 model calls (true, the pipeline is deterministic); no real API run has been measured.
- See `docs/integration/RCA_ACCURACY.md` for the evidence behind every item.

## Integration notes

Merge record (append-only; newest last). One row per unit merged into `dev` or `main`.

| Date | Unit | Merged commit | Gates run | Result | Notes |
|---|---|---|---|---|---|
| 2026-11-04 | Ashish ingestion, PR #3, with foundation baseline B1 (`0bbee13`) | `2666ffe` | none recorded: merged before this mechanism, `dev` had no workflows; owner's own Docker run is in `ashish.md` | merged by Lalith; Satvika commented "good", Lalith approved | Retroactive entry. 98 files: 47 ingestion plus the baseline. No delivery note existed; `ashish.md` was written afterwards |
