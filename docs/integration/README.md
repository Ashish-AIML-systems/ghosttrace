# How we integrate

Four people push to four branches; one person (the integrator) merges. This folder exists so that
**nothing the integrator needs to know about a merge lives only in someone's head**.

| Read this if you are... | Start here |
|---|---|
| opening a PR | this page, then your note in [`deliveries/`](deliveries/) |
| wondering who needs what from you | [`DEPENDENCY_MATRIX.md`](DEPENDENCY_MATRIX.md) |
| merging | [`INTEGRATOR_PLAYBOOK.md`](INTEGRATOR_PLAYBOOK.md) |
| touching `contracts.py` | [`CONTRACT_CHANGELOG.md`](CONTRACT_CHANGELOG.md) |

## The six rules

1. **Every PR updates your delivery note** - `docs/integration/deliveries/<you>.md`. The CI job
   `Delivery check` fails without it. One living note per workstream, not one per PR.
2. **Say what you need and what you give.** `Requires from others` and `Provides to others` are
   tables, one row per person. If a row exists in someone else's note about you, answer it.
3. **Stay in your paths.** Ownership is in [`ownership.toml`](ownership.toml). If you must edit
   someone else's file, list it in `## Cross-owner edits` (in backticks, with the reason) and tell the owner.
4. **Never change the contract, dependencies or Docker files directly.** Ask in
   `## Contract and dependency requests`. Contract changes also need an entry in
   [`CONTRACT_CHANGELOG.md`](CONTRACT_CHANGELOG.md), the approver's sign-off and notice to all four.
5. **Record the contract you built against.** `contract_sha256` in your note must equal
   `contracts/SCHEMA_SHA256`. If it stops matching, the contract moved: read the changelog, adapt,
   re-run your tests, then update the hash. Do not just paste the new hash.
6. **Merges happen only through the integrator**, one workstream at a time, in `merge_after` order.
   Do not merge your own PR or someone else's branch into yours without saying so.

## Branches and flow

```text
ashish ─┐
manya  ─┤   PR (CI: Delivery check + Merge check)         integrator: preflight, rehearse, gates
satvika─┼──────────────────────────────────────────►  dev  ───────────────────────────►  main
lalith ─┤                                                (integration branch)            (release candidate)
integration/<topic> ┘
```

- Your branch is `ashish`, `manya`, `satvika` or `lalith` (sub-branches like `manya/graph` also count).
  Integrator work uses `integration/<topic>`. The branch name decides whose note CI expects.
- Start from `dev`, not from another person's branch. Merge `dev` into yours before opening the PR.
- `dev` is protected: changes arrive only by pull request.

## The delivery note

File: `docs/integration/deliveries/<owner>.md`. Copy the structure of
[`deliveries/ashish.md`](deliveries/ashish.md), which is a complete example.

### Front matter (machine-read)

| Field | Meaning |
|---|---|
| `owner` | your key; must match the file name |
| `status` | `NOT_STARTED` -> `IN_PROGRESS` -> `READY_FOR_INTEGRATION` (you set) -> `INTEGRATED` (the integrator sets after merging) |
| `contract_version`, `contract_sha256` | the contract your code was written and tested against; must equal the tree |
| `built_on` | the commit of `dev` (or baseline) you branched from; must be an ancestor of your branch; `none` only while `NOT_STARTED` |
| `merge_after` | owners that must be `INTEGRATED` on `dev` before this merges, or `none` |
| `last_updated` | ISO date |

### Sections (all required once you start)

| Section | Write here |
|---|---|
| `Delivers` | What the PR adds: public functions with signatures, files, commit hash. A reader should know what exists after the merge without opening the diff |
| `Cross-owner edits` | Every file you changed that is not yours: path in backticks, why, who must confirm. `None` if none |
| `Requires from others` | Table: from whom, what, why, status (`OPEN` / `MET`). Include decisions you are waiting for |
| `Provides to others` | Table: to whom, what, where, **what they must honour** - the semantics a type checker will not catch |
| `Contract and dependency requests` | New or changed contract fields, new packages (name, version, who needs them). `None` only if truly none; the gate rejects `None` when `pyproject.toml`, `uv.lock` or Docker files changed |
| `Verification` | Exact commands run and their results, with where (Docker or host) and date |
| `Known limits` | What does not work, what is unmeasured, what you assumed |
| `Integration notes` | What the merge will do to others: collision files, order constraints, environment needs, gates to run after merging, things that look like bugs but are not |

`NOT_STARTED` notes only need `Requires from others` and `Provides to others`. Placeholders (`TODO`,
`TBD`, `<fill`) and empty sections fail the gate; write `None` or `Nothing` if that is the honest answer.

## What CI checks, and how to fix each failure

| Message contains | Meaning | Fix |
|---|---|---|
| `... but docs/integration/deliveries/<you>.md was not updated` | You changed non-documentation files and did not touch your note | Update the note (at least `Delivers`, `Verification`, `last_updated`) |
| `outside your ownership are not declared` | You edited another owner's file | List it under `## Cross-owner edits`, or revert it |
| `CONTRACT_CHANGELOG.md was not updated` | Contract files changed | Add the entry; get the approver's sign-off |
| `the contract moved since you wrote the note` | Someone merged a contract change into `dev` | Read the changelog, adapt, re-test, then update `contract_sha256` |
| `you changed the contract` | `contract_sha256` in your note is stale after your own change | Run `python scripts/export_contracts.py` and copy the hash |
| `built_on ... is not an ancestor` | You wrote a commit you did not branch from | Put the real base commit, or merge `dev` first |
| `dependency/build files changed` | `pyproject.toml`, `uv.lock`, `Dockerfile` or Compose changed but the note says `None` | Name the package/version and who needs it |
| `status is NOT_STARTED but this change touches code` | Status not advanced | Set `IN_PROGRESS` or `READY_FOR_INTEGRATION` |
| `cannot tell whose work this is` | Branch is not an owner branch and no note changed | Rename the branch (`<you>/<topic>`) or update your note |
| `missing section` / `is empty` / `placeholder` | Note shape | Fill it in |

Documentation-only changes (anything under `docs/`, `team_handoff/`, root `*.md`, `log.txt`) need no note.
Changing `ownership.toml` is the exception: it changes the rules, so it counts as a code change.

## Before you push

Run the gate you will be judged by, plus your own tests:

```text
git fetch origin
git merge origin/dev
python scripts/delivery_check.py ci --base origin/dev --head HEAD --branch <your-branch>
docker compose run --rm slam-dev pytest -q tests/contracts tests/<your-area> tests/integration
docker compose run --rm slam-dev ruff check code tests scripts
docker compose run --rm slam-dev mypy code/slam code/main.py
```

`delivery_check.py` needs only Python 3.11+ and git; no virtual environment.

## The integrator's view

```text
python scripts/delivery_check.py status                        # one row per workstream
python scripts/delivery_check.py preflight origin/manya        # what would merging it do?
```

`status` shows each owner's note status, how far their branch is ahead of and behind `dev`, which
contract they are on and what they wait for. `preflight` is read-only and reports ownership, contract
position, merge order, textual conflicts (via `git merge-tree`, no working-tree changes) and the author's
own `Requires` and `Integration notes`. Full procedure: [`INTEGRATOR_PLAYBOOK.md`](INTEGRATOR_PLAYBOOK.md).

## Who is the integrator?

`[roles] integrator` in [`ownership.toml`](ownership.toml). It is a role, not a set of paths, so handing
it over changes who is asked, never who may edit what. `contract_approver` is the person who must
approve contract changes.
