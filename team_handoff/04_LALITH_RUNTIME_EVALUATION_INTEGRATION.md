# Lalith build document

## Mission

Own the shared foundation, API-model runtime, observability, evaluation harness, Docker environment, integration, reproducible full run, and submission packaging. You coordinate contracts and merge the other three workstreams, but you do not silently rewrite their business logic. Your primary responsibility is to make the assembled system reproducible, measurable, safe, and honestly reported.

Read root `AGENTS.md`, `problem_statement.md`, `team_handoff/SHARED_BUILD_CONTRACT.md`, and all three teammate documents. Contract version `1.0.0` is the starting integration boundary.

## Owned paths

```text
pyproject.toml
uv.lock
Dockerfile
docker-compose.yml
.env.example
README.md
code/main.py
code/slam/contracts.py
code/slam/config.py
code/slam/runtime/**
code/evaluation/**
tests/contracts/**
tests/runtime/**
tests/evaluation/**
tests/fixtures/shared/**
```

## Phase 1 shared baseline

1. Create the package skeleton and frozen Pydantic contracts before teammates code against them.
2. Add import/serialization round-trip contract tests and identical canonical fixtures.
3. Create a multi-stage Python 3.11 Dockerfile, non-root runtime user, read-only source mount where practical, cache volumes outside the submission, and health/smoke commands.
4. Pin Python dependencies through `uv.lock`; record the base-image digest after qualification.
5. Make offline fake-provider tests the default Compose behavior.
6. Provide `.env.example` with names and safe placeholders only. `.env` must be ignored.
7. Pull/build the selected Docker images only after the files exist, then run a clean-container smoke test.

Do not require Docker in the final competition runtime if the official environment expects a direct terminal command; provide both container and documented `uv sync`/Python paths. Docker is the team reproducibility layer.

## API model adapter

Implement a provider-neutral `ModelProvider` with an OpenAI Responses API adapter as the initial real provider and a deterministic fake provider for tests. Configuration selects an explicit model; never guess or silently change it. Use native structured output when supported, then validate again with Pydantic and semantic checks.

Required controls:

- environment-only credentials;
- connect/read/overall timeouts;
- at most two bounded retries with jitter for retryable failures only;
- bounded async concurrency and rate-limit handling;
- optional run budget that stops further calls safely;
- refusal, truncation, schema, timeout, authentication, quota, and provider errors represented explicitly;
- cache keys containing source/prompt/schema/provider/model/settings hashes;
- no tools, write actions, or policy authority granted to the model;
- request metadata without secret or unnecessary personal-data logging.

Meter actual calls separately from cache hits. Capture provider, exact model, request ID, input/output/cached/reasoning tokens when reported, retries, latency, and price-table version. If the provider does not report a field, mark it unavailable—never invent it. Cost is an estimate based on a versioned rate table.

## Orchestrator

Implement a thin typed flow:

```text
load requests and shared sources
        -> Ashish ingest once
        -> for each request: Manya reconstruct
        -> Satvika plan and validate
        -> final cross-case export validation
        -> reports and run manifest
```

Use bounded concurrency only where determinism and provider limits remain controlled. Resume from content-addressed checkpoints. A case failure must be isolated and recorded, but final submission certification must fail until every required case has a supported valid answer. Never fill a failed case with a convenient status.

## Evaluation harness first

Build validators/scorers before tuning the engine:

- schema/case coverage/order/JSON/step/operation/state/evidence validation;
- public-sample case status, full-case exact match, step precision/recall/F1, field accuracy, sequence accuracy;
- semantic evidence checks reported separately from exact-answer agreement;
- false `COMPLETE`, invalid citation, retention/policy violation counts;
- runtime, call, token, cache, retry, and cost metrics;
- per-case diffs without leaking answers into production code.

Create 20 scenario families with three development fixtures and two locked final fixtures each: replica survival; historical email; valid tombstone; exposed tombstone; sync recreation; restore risk; retained record; shared redaction; future evidence; similar people; duplicates; clean primary with active flow; prompt injection; non-deletion; parser failure; contradicted success; cross-system resource IDs; temporal identity; retention/hold boundaries; insufficient/conflicting evidence.

Expected fixture results must be specified independently of the predictor. The 60 development fixtures are regression data; the 40 final fixtures remain locked until final qualification. Once inspected to guide a fix, a fixture is consumed and no longer called untouched holdout.

## Measured improvement loop

Run a baseline and up to six rounds per cycle. In each round group failures by root cause, propose testable changes, implement one change at a time, and keep it only if safety does not regress and the predefined metric order improves: safety/false-complete first, then full-case exact match, step F1, sequence, and efficiency. Stop after two rounds without a qualifying gain. Start a new cycle only for a new concrete cause. Do not claim “best possible” or hidden accuracy.

## Tests you must own

- Pydantic contract serialization, rejection, versioning, and canonical-fixture round trips.
- Fake provider success, refusal, malformed response, truncation, timeout, authentication, rate-limit, retry, budget, and cache behavior.
- Usage aggregation separates real calls, retries, and cache hits and never invents unavailable token fields.
- Orchestration isolates case failures but refuses final certification while any required case is unresolved.
- Resume/checkpoint behavior is content-addressed and does not reuse decisions across different cutoffs, policies, prompts, schemas, models, or evidence sets.
- Output validator catches every schema, row-set, ordering, citation, phase, operation/state, numbering, and JSON defect.
- Scorers have independently hand-checked miniature examples.
- Metamorphic tests cover row shuffling, unrelated users, duplicate evidence, safe renaming, future evidence, restart/cache reuse, and poisoned instructions.
- Clean-container tests work with no `.env` and no network access.
- Packaging tests inspect the archive and reject datasets, secrets, caches, environments, model weights, and nested archives.

## Integration procedure

1. Freeze and distribute the contract fixture hash.
2. Integrate Ashish; run contracts plus ingestion tests and inspect the corpus inventory.
3. Integrate Manya; run contracts, ingestion, and reconstruction tests plus trace samples.
4. Integrate Satvika; run all prior tests plus planning/export tests.
5. Run Ruff, mypy, full pytest, public evaluation, adversarial/metamorphic tests, and clean-container run.
6. Run a small explicitly authorized real-API smoke test with a spend ceiling; never make paid calls as part of ordinary tests.
7. Run the final full dataset once configuration is frozen; generate `output.csv`, reports, and manifest from the same run ID.
8. Validate every required artifact and inspect the archive contents before submission.

## Final gates

- Exact required row set, unique sorted case IDs, exact columns, valid JSON and steps.
- No unresolved internal status, invalid citation, unsupported operation/state, or false-success fallback.
- All tests and static checks pass in a clean container.
- Re-running the frozen offline parts is deterministic; API-dependent differences are recorded.
- `code/evaluation/evaluation_report.md` contains required metrics, custom cases, failures, and improvements.
- `code/evaluation/usage_report.md` contains exact providers/models, call/token totals, averages, cost estimates, and unavailable fields.
- Run manifest records code commit, data/policy hashes, prompts, schemas, model, provider, dependencies, container digest, settings, cache state, and run ID.
- `code.zip` excludes dataset, `.env`, keys, caches, virtual environments, model responses containing unnecessary personal data, weights, and nested archives.
- Root `log.txt` and required agent trace are complete and secret-free.

## Acceptance criteria

- A new teammate can clone the repository and run the complete offline quality gate with the documented Docker commands.
- All three teammate modules integrate only through contract `1.0.0` or an explicitly approved replacement.
- Real API access is opt-in, bounded, metered, and never required for ordinary unit/contract tests.
- The same final run ID links `output.csv`, evaluation report, usage report, and run manifest.
- No unresolved case, false-success fallback, secret, or organizer-only artifact reaches the submission package.
- Reported metrics and costs are reproducible from retained non-secret run artifacts and clearly distinguish measured facts from limitations.

## AI coding agent start prompt

```text
Read AGENTS.md, problem_statement.md, SHARED_BUILD_CONTRACT.md, and all four role documents. You are Lalith's integration agent for SLAM contract 1.0.0. First create frozen Pydantic contracts, canonical fixtures, contract tests, Docker/Compose, dependency lock, fake ModelProvider, and evaluation validators. Do not implement teammates' owned business modules beyond typed NotImplemented stubs. Real model access is API-only through environment credentials; no Ollama or local weights. Ordinary tests must be offline and use the fake provider. Implement strict structured-response validation, bounded retries/concurrency/budget, content-addressed caching, usage metering, and explicit failures. Integrate teammate branches one at a time only after their contract and owned tests pass. Never fabricate missing outputs or claim hidden accuracy. Run the complete containerized quality/evaluation gates and produce a delivery/integration report with exact commands, results, limitations, and artifact hashes.
```

## Coordination checklist

Maintain a contract-change log. Reject undocumented interface drift. Require each teammate's commit hash and delivery note. Resolve dependency requests centrally. Keep shared fixtures identical. Tag qualified integration checkpoints. Preserve the best measured version and rejected-change evidence. Have all four members review the final run and package before submission.

## Delivery to Lalith

This is Lalith's own workstream. Preserve integration commits, contract hashes, container/base-image digest, test and evaluation reports, API usage summary, run manifest, package inventory, and the final artifact hashes. Share the qualified checkpoint and these records with all teammates for final review before submission.
