---
owner: integration
workstream: Integration, seam tests, CI, packaging
status: IN_PROGRESS
contract_version: 1.0.0
contract_sha256: 7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd
built_on: 0bbee13
merge_after: none
last_updated: 2026-11-04
---

# Integration - mechanism, CI, merge record

<!-- Used by branches named integration/<topic>. The record at the bottom is append-only. -->

## Delivers

- The PR documentation mechanism: `docs/integration/` (README, DEPENDENCY_MATRIX, INTEGRATOR_PLAYBOOK,
  CONTRACT_CHANGELOG, `ownership.toml`, one delivery note per workstream), the PR template, the
  `Delivery check` workflow, and `scripts/delivery_check.py` (`ci`, `preflight`, `status`) with
  tests in `tests/integration/`.
- Later: seam tests between the three modules, `main.py --dataset` wiring, final packaging checks.

## Cross-owner edits

None.

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

- `tests/integration/test_delivery_check.py`: gate rules, preflight and merge dry-run against
  throwaway git repositories, plus validation of the notes committed in this repository.
- The `Delivery check` workflow runs `scripts/delivery_check.py ci` on every PR to `main` and `dev`.

## Known limits

- The gate checks that documentation exists, is well formed, is consistent with the tree and
  declares cross-owner edits. It cannot judge whether a note is *true*; that is the reviewer's job.
- The workflows ship in the same PR that introduces them (`delivery-check.yml` is new; `merge-check.yml`,
  `push-check.yml` and the `python-gate` action were adopted from the working tree and were not written
  by this change). Their first real run on GitHub is that PR's own run; until it is green they are
  untested there. `dev` still needs the two checks marked as required (playbook, Step 0).

## Integration notes

Merge record (append-only; newest last). One row per unit merged into `dev` or `main`.

| Date | Unit | Merged commit | Gates run | Result | Notes |
|---|---|---|---|---|---|
| 2026-11-04 | Ashish ingestion, PR #3, with foundation baseline B1 (`0bbee13`) | `2666ffe` | none recorded: merged before this mechanism, `dev` had no workflows; owner's own Docker run is in `ashish.md` | merged by Lalith; Satvika commented "good", Lalith approved | Retroactive entry. 98 files: 47 ingestion plus the baseline. No delivery note existed; `ashish.md` was written afterwards |
