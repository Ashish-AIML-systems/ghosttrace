<!--
Rules and examples: docs/integration/README.md. Your note: docs/integration/deliveries/<you>.md.
CI ("Delivery check") enforces the note; the integrator reads this list during preflight.
Delete nothing - tick or explain.
-->

## What this PR delivers

<!-- Two or three sentences and the head commit hash. Public functions with signatures if any. -->

## Whose workstream

- [ ] ashish
- [ ] manya
- [ ] satvika
- [ ] lalith
- [ ] integration

## Delivery note

- [ ] I updated `docs/integration/deliveries/<me>.md` in this PR (`status`, `Delivers`, `Verification`, `last_updated`)
- [ ] `Requires from others` lists what I am waiting for; `Provides to others` says what each person must honour
- [ ] Every file outside my paths is listed under `Cross-owner edits`, and I told its owner
- [ ] I merged `dev` into my branch; `built_on` and `contract_sha256` in my note are current
- [ ] Contract, dependency or Docker changes are requested in the note (contract changes also in `CONTRACT_CHANGELOG.md`)

## Merge impact

<!-- Copy from your note's "Integration notes". -->

- Merge after:
- Collision files touched:
- What the other workstreams must do after this merges:

## Checks run

<!-- Paste the real output, not "passed". -->

```text
python scripts/delivery_check.py ci --base origin/dev --head HEAD --branch <branch>
docker compose run --rm slam-dev pytest -q tests/contracts tests/<area> tests/integration
docker compose run --rm slam-dev ruff check code tests scripts
docker compose run --rm slam-dev mypy code/slam code/main.py
```

## For the integrator

```text
python scripts/delivery_check.py preflight origin/<branch>
```
