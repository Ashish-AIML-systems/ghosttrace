# Integrator playbook

> Historical baseline snapshot below describes the state before contract 1.1.0. The interface decisions
> are now recorded in `DEPENDENCY_MATRIX.md`; merge the current shared contract before teammate work.

Everything the integrator does, in order, with the command and the stop condition for each step.
Commands are plain `git`, `docker compose` and `python`, so they run unchanged in PowerShell and bash.

**Principles.** One unit at a time. Nothing merges without a green preflight, a rehearsal and the gates.
Merge with a **merge commit** (not squash, not rebase): `built_on` and `merge_after` depend on ancestry,
and `git revert -m 1` can undo a whole unit. Record every merge. Never fill a gap with a convenient
answer: an unresolved case stays unresolved.

## Step 0 - Align the baseline (once, before the first merge)

Snapshot of 2026-11-04 after PR #3 was merged (live view: `python scripts/delivery_check.py status`):

| Ref | Commit | Contract | State |
|---|---|---|---|
| `origin/dev` | `2666ffe` | B1 `7beb34d3...` | foundation + ingestion (PR #3, merged by Lalith, **no CI ran**: `dev` has no workflows) |
| `origin/main` | `066aa6c` | none | plan and handoff only; 5 behind `dev` |
| `origin/lalith` | `0e27272` | B0 `1d4ca61a...` | **old** contract; 3 behind `dev` |
| `origin/manya`, `origin/satvika` | `346e811` | none | not started; 9 behind `dev` |
| `origin/ashish` | `bfe33f4` | B1 | merged |

The code baseline is settled. What is missing is the *process* around it: nothing on `dev` enforces notes,
ownership or the contract hash, the contract identity is not written down, and three branches still start
from the wrong place. Do these once, in this order:

1. **Land this mechanism** so every later PR is gated. Branch from `dev` (not from `ashish`: the gate would
   treat these integrator files as foreign to Ashish):

   ```text
   git fetch origin
   git switch -c integration/mechanism origin/dev
   ```

   Then commit `docs/integration/`, `scripts/delivery_check.py`, `tests/integration/` and `.github/`
   (PR template, `delivery-check.yml`, and the existing `merge-check.yml`, `push-check.yml`, `python-gate`
   action, which are untracked in the checkout this was written in and were not written by this change).
   Open the PR to `dev`; its own `Delivery check` should pass (author `integration`, everything within
   the integration paths). `.github/` stays inert until it is committed.
2. **Record the contract decision.** Add the explicit "B1 is the frozen `1.0.0`" line to
   [`CONTRACT_CHANGELOG.md`](CONTRACT_CHANGELOG.md) with Lalith's approval. *Stop if Lalith has not agreed.*
3. **Protect `dev` properly.** In repository settings require a PR, one approval, and the status checks
   `Delivery check / Delivery note` and `Merge check / Merge gate`. (The API reported no classic branch
   protection on `dev`, yet direct pushes were rejected before; if a ruleset is in use, add the checks
   there. Verify on the settings page.) The two checks only exist after step 1 has run once.
4. **Decide Q1-Q3** in [`DEPENDENCY_MATRIX.md`](DEPENDENCY_MATRIX.md) section 4 with Lalith and the
   affected owner. Q1-Q2 change `contracts.py`: one contract PR from Lalith (new hash, changelog entry,
   notes updated). Do this *before* Satvika writes `policy.py` and before Manya returns `ResourceState`.
5. **Tell Lalith, Manya and Satvika** (template below): `git merge origin/dev` into your branch, then set
   `built_on` and `contract_sha256`. Change the README's "branch from `lalith`" to "branch from `dev`".
6. **Optional, recommended:** a small PR that splits `tests/contracts/test_owned_boundaries.py` into one
   file per workstream, removing the one collision file Manya and Satvika must both edit.
7. **Decide when `dev` is promoted to `main`.** `main` has no foundation. Recommended: promote only at a
   qualified checkpoint (Step 3), by PR, with a merge commit, so `main` always holds a state that passed
   the full gates.

Exit: the gate is on `dev` and required; the contract identity is written down; Q1-Q3 are decided; every
branch starts from `dev`.

## Step 1 - The loop for each unit

Order of units: **Ashish (done, `2666ffe`) -> Manya -> Satvika -> integration wiring.** Lalith's own
changes go through the same loop whenever they appear (contract changes jump the queue: merge, then
everyone re-verifies).

### 1A Intake

The owner sets `status: READY_FOR_INTEGRATION`, opens the PR with the template filled, and posts the commit hash.
Check: the PR targets `dev`, CI is green, the cross-reviewer has approved (Satvika reviews Ashish; Ashish
reviews Manya; Manya reviews Satvika; Satvika reviews Lalith).

### 1B Preflight (read-only)

```text
git fetch --all --prune
python scripts/delivery_check.py status
python scripts/delivery_check.py preflight origin/<branch>
```

| Output | Meaning | Action |
|---|---|---|
| `ERROR ... does not contain <commit>` | the branch was built on a commit the target does not have | the owner built on the wrong base: have them rebuild from `dev`, or land that commit first |
| `ERROR merge_after <x>` | predecessor not `INTEGRATED` on `dev` | merge the predecessor first, or `--allow-out-of-order` with a written reason |
| `ERROR branch is on contract A but dev has B` | contract moved since the branch forked | owner merges `dev`, re-tests, updates the note |
| `WARNING branch CHANGES the contract` | contract PR | needs approver sign-off, a changelog entry and notice to all four |
| `ERROR merging would conflict in ...` | textual conflict | see "Conflicts" below; resolve in the rehearsal, never on `dev` |
| `WARNING ... known collision files` | expected overlap | check the conflict table in the matrix |
| `ERROR ... not declared` | undeclared cross-owner edit | owner declares it or reverts it |

### 1C Read the note against the diff

- `Delivers` agrees with `git diff --stat origin/dev...origin/<branch>`; nothing unmentioned.
- `Cross-owner edits` equals the real out-of-ownership files; the owner of each file has confirmed.
- Every row in `Requires from others` is `MET` or consciously `OPEN`.
- Each `Provides` row matches the consumer's `Requires` row ([matrix](DEPENDENCY_MATRIX.md) section 2).
- `Known limits` is honest; `Verification` lists commands you can repeat.

### 1D Rehearse in an isolated worktree

The dataset is gitignored, so copy it in. This never touches your own working tree.

```text
git worktree add ../slam-rehearsal -b rehearsal/<unit> origin/dev
```

Copy `dataset/` into `../slam-rehearsal/dataset` (PowerShell: `Copy-Item -Recurse dataset ../slam-rehearsal/dataset`;
bash: `cp -r dataset ../slam-rehearsal/dataset`). Then, inside `../slam-rehearsal`:

```text
git merge --no-ff origin/<branch>
docker compose build
docker compose run --rm slam-dev uv lock --check
docker compose run --rm slam-dev pytest -q
docker compose run --rm slam-dev ruff check code tests scripts
docker compose run --rm slam-dev mypy code/slam code/main.py
docker compose run --rm slam-dev python scripts/export_contracts.py
git status --porcelain contracts
```

The last two lines must leave `contracts/` unchanged (on Windows, CRLF noise is not drift: `git checkout -- contracts/`).
The default Compose provider is `fake`: no key, no spend, no network. *Stop on any red.*

### 1E Seam checks for this unit

Type-checking proves the pieces fit; these prove they mean the same thing. Add the test to
`tests/integration/` in the same rehearsal (skipped when `dataset/` or the next module is absent).

| Unit | Check | Assertion |
|---|---|---|
| Ashish (retroactive: already on `dev`) | Real dataset ingest on `dev` | every manifest row has a `SourceRecord`; `parsed` count matches `CORPUS_REPORT.md` (94/94); two runs give byte-identical bundles; no `error` issue. Worth running once in the rehearsal worktree, because no CI ever ran on this merge |
| Manya | **S1: ingest -> reconstruct on every request** | `reconstruct` returns a valid `CaseContext` for all 518 requests without exceptions; output identical under shuffled bundle rows; every id in any `*_evidence_ids` resolves to a `source_id`, `activity_id` or `audit_id` in the bundle (Q2); ingestion error issues and `uncertain` observations appear in `coverage_issues` or `unresolved_conflicts`; no observation with `effective_time` > `audit_at` is in `eligible_observation_ids` |
| Satvika | **S2: reconstruct -> plan** | every `CaseAnswer` validates; `NOT_APPLICABLE` has no steps; a context with `unresolved_conflicts` never yields `COMPLETE`; remediation puts `DISABLE_DATA_FLOW` / `BLOCK_RESTORE` before record changes; every remediated resource has a verification; `evidence_id` is empty exactly for future steps; two runs give byte-identical `steps_json` |
| Satvika | **S3: end to end on the 32 public samples** | status accuracy and full-row match against `dataset/sample_output.csv` (use Lalith's scorer when it exists; until then a plain diff). Report numbers; do not tune the code to sample ids |
| Satvika | Exporter | 518 unique sorted rows, exact columns, invalid JSON rejected, missing case rejected (caller supplies the required ids) |
| Lalith | Contract | `contracts/SCHEMA_SHA256` equals the changelog's current hash; `uv lock --check`; image builds; validators pass hand-checked mini examples |

### 1F Merge

On GitHub use **Create a merge commit**. After it lands, confirm the post-merge `Merge check` on `dev` is
green. If it is red, revert first (step 4), diagnose after.

### 1G Record

On `integration/record-<unit>`: set the unit's note to `status: INTEGRATED`, append a row to the merge record in
[`deliveries/integration.md`](deliveries/integration.md) (date, unit, merged commit, gates run, result, notes),
and open a PR. Never edit the record's earlier rows.

### 1H Notify

Send to all four, the same day:

```text
dev is now <short-hash> (<unit> merged).
Contract: unchanged <hash8> | CHANGED to <hash8> - read CONTRACT_CHANGELOG.md.
Dependencies: none | <package version> added to uv.lock.
Collision files touched: <list or none>.
You must: git fetch; git merge origin/dev; re-run your tests; update built_on (and contract_sha256 if changed) in your note.
Next in line: <unit>, which needs <thing> from <owner>.
```

### 1I Checkpoint and clean up

```text
git tag -a integ-<n>-<unit> <merge-commit> -m "<unit> integrated; gates green"
git worktree remove ../slam-rehearsal
git branch -D rehearsal/<unit>
```

Push the tag only when you mean to publish it (it is visible to everyone).

## Conflicts

- **Textual.** Resolve in the rehearsal worktree, never on `dev`. Keep every owner's intent: for
  `tests/contracts/test_owned_boundaries.py` keep each workstream's replaced test. If a conflict is in a
  file owned by X and you are not X, ask X to resolve and push; do not guess their logic.
- **Semantic** (tests green, meaning differs): the seam tests and the matrix are the defence. When one
  fails, write the disagreement into both owners' `Integration notes`, decide in writing, then fix on the
  owner's branch, not in the merge commit.
- **Contract.** Whoever changed it updates the changelog; everyone else re-verifies and updates the hash.

## Step 2 - Wire the whole pipeline (after all three units)

1. `code/main.py --dataset` currently exits with "must be integrated". Wire: `load_requests` -> `ingest` once ->
   per request `reconstruct` -> `plan` -> `export_output_csv(answers, required_case_ids, path)` (Q3), writing
   `output.csv` at the repository root. A case failure is isolated and recorded, and the run exits non-zero
   until every required case has a supported answer. Declare `code/main.py` and `runtime/orchestrator.py`
   as cross-owner edits in `integration.md`; Lalith confirms.
2. Add `tests/integration/test_pipeline.py`: the same run on the 32 public samples, offline, fake provider.
3. Re-run the full gate set from 1D, then Step 3.

## Step 3 - Final qualification

| # | Gate | Command / evidence | Pass condition |
|---|---|---|---|
| 1 | Static + tests | `ruff`, `mypy`, `pytest -q` in a clean container with no `.env` and no network | all green |
| 2 | Public samples | S3 with the scorer | numbers recorded in `evaluation_report.md`; no false `COMPLETE` |
| 3 | Determinism | run twice, compare SHA-256 of `output.csv` | identical (API-dependent differences, if any, recorded) |
| 4 | Metamorphic / adversarial | row shuffling, unrelated users, duplicate evidence, future evidence, prompt-injection text | outputs unchanged or correctly changed |
| 5 | Output validity | validator on `output.csv` | 518 rows, sorted unique `case_id`, exact columns, valid JSON, consecutive `step_no`, allowed operation/state, citations eligible at `audit_at` |
| 6 | API smoke | explicit, budget-capped real-provider run on a handful of cases | usage metered; failures explicit; never part of ordinary tests |
| 7 | Full run | one run id links `output.csv`, evaluation report, usage report, run manifest | reports contain the required metrics and costs (`AGENTS.md` 6.8) |
| 8 | Package | inspect `code.zip` | no `dataset/`, `.env`, keys, caches, venvs, weights, nested archives, personal data (6.9); README run instructions work from a clean clone |
| 9 | Transcript | root `log.txt` complete and secret-free | one entry per turn with `tool=` and `model=` |
| 10 | Review | all four review the final run and the package | sign-off recorded in the merge record |

## Step 4 - Recovery

A red `Merge check` on `dev`, or a unit that breaks someone else's work:

```text
git switch -c integration/revert-<unit> origin/dev
git revert -m 1 <merge-commit>
```

Open a PR, merge it, set the unit back to `IN_PROGRESS`, tell the owner what failed and where. Never
force-push `dev` or rewrite a merged commit. The owner fixes on their branch, merges `dev`, and re-enters at 1A.

## Per-unit checklist (paste into the merge PR)

```text
[ ] 1A  PR to dev, CI green, cross-review approved, note status READY_FOR_INTEGRATION
[ ] 1B  preflight: no ERROR (warnings explained)
[ ] 1C  note matches diff; cross-owner edits confirmed by their owners
[ ] 1D  rehearsal: build, uv lock --check, pytest, ruff, mypy, contracts unchanged
[ ] 1E  seam checks for this unit written and green
[ ] 1F  merge commit; post-merge Merge check green
[ ] 1G  unit INTEGRATED; merge record row added
[ ] 1H  four owners notified (contract/deps/collisions/what to rebase)
[ ] 1I  tag created; rehearsal worktree and branch removed
```
