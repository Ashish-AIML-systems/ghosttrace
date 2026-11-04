---
owner: lalith
workstream: Contracts, runtime, evaluation, Docker
status: IN_PROGRESS
contract_version: 1.0.0
contract_sha256: 7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd
built_on: 0bbee13
merge_after: none
last_updated: 2026-11-04
---

# Lalith - contracts, runtime, evaluation, Docker

<!--
Pre-filled by the integrator from git history and team_handoff/04_LALITH_RUNTIME_EVALUATION_INTEGRATION.md.
Lalith: correct anything that is wrong and keep this current in every PR from branch `lalith`.
-->

## Delivers

- Foundation baseline, authored by Lalith: commits `c0523a0` and `0e27272`, and `0bbee13`
  ("Expand ingestion contracts and image provider"). All three are on `dev` since PR #3 (`2666ffe`,
  merged by Lalith). `origin/lalith` itself is still at `0e27272`, three commits behind `dev`, and
  `main` has none of them.
- Contract models and generated schema (`code/slam/contracts.py`, `contracts/`), `ModelProvider`
  with fake and OpenAI providers (`code/slam/runtime/`), cache keys, usage metering, `Settings`,
  Docker/Compose, `uv.lock`, and `run_cases` in `runtime/orchestrator.py`.
- Not visible on any branch yet: evaluation harness (`code/evaluation`, `tests/evaluation`),
  `main.py --dataset` wiring, usage and evaluation reports, packaging checks.

## Cross-owner edits

None.

## Requires from others

| From | What | Why | Status |
|---|---|---|---|
| Ashish, Manya, Satvika | A delivery note, commit hash and passing owned tests per branch | Integration protocol in `SHARED_BUILD_CONTRACT.md` | Ashish integrated (`2666ffe`); Manya and Satvika not started |
| Manya, Satvika | Fixtures under `tests/fixtures/<area>/` | The evaluation harness needs independent expected results | OPEN |
| Satvika | The exporter's signature | The orchestrator and `main.py` must call it (open question Q3) | OPEN |
| Integrator | Decisions on Q1-Q4 in `DEPENDENCY_MATRIX.md` | They change `contracts.py` or the frozen signatures, which you approve | OPEN |

## Provides to others

| To | What | Where | They must honour |
|---|---|---|---|
| Everyone | The contract and its schema hash | `code/slam/contracts.py`, `contracts/SCHEMA_SHA256` | Changes need your approval, a `CONTRACT_CHANGELOG.md` entry and notice to all four. A change under the same version string is exactly how the two `1.0.0` hashes appeared |
| Ashish, Manya | `ModelProvider` (structured output, image input, usage), fake provider | `code/slam/runtime/` | No tools, no write access, no authority over identity, policy or status |
| Everyone | `build_model_cache_key`, `Settings`, Docker image, locked dependencies | `runtime/cache.py`, `config.py`, `Dockerfile`, `uv.lock` | Dependency changes go through you only |
| Integrator | `run_cases` and the validators/scorers once written | `runtime/orchestrator.py`, `code/evaluation/` | The orchestrator refuses to fabricate results for unresolved cases |

## Contract and dependency requests

None open from this workstream. Open requests from others are tracked in `CONTRACT_CHANGELOG.md`
(Ashish: allow a failed `SourceRecord` for rejected manifest rows).

## Verification

Baseline checks are recorded in the commits above. This note has not been re-verified by its owner
since the integrator created it; run `docker compose run --rm slam-dev pytest -q tests/contracts
tests/runtime` and record the result here.

## Known limits

Evaluation harness, wiring and reports are not started. Real-API behaviour has never been measured.

## Integration notes

- Merge `origin/dev` into `lalith` before the next push: the branch is still on the earlier shape of
  the contract (B0), and CI will report the hash mismatch in this note.
- `main` is five commits behind `dev` and has no `contracts/`; decide when `dev` is promoted to `main`.
- Hotspot files you own that others will edit: `tests/contracts/test_owned_boundaries.py`,
  `pyproject.toml`, `uv.lock`, `README.md`, `code/main.py`.
