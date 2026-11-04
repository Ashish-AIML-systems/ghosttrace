# SLAM shared build contract

Contract version: `1.0.0`

## Product and outcome

SLAM is a portable AI-assisted deletion-audit agent. For each deletion request it determines whether deletion was actually requested, resolves the subject across current and historical identifiers, discovers all relevant copies and recreation paths, reconstructs state at `audit_at`, applies the supplied retention/deletion rules, and produces an evidence-backed status and ordered action plan.

The required root output is `output.csv` with exactly:

```text
case_id,deletion_status,steps_json
```

The only statuses are `COMPLETE`, `INCOMPLETE`, and `NOT_APPLICABLE`. The official `AGENTS.md` and `problem_statement.md` remain authoritative if any handoff text conflicts with them.

## Shared technical baseline

- Python 3.11 in a Linux container; local Python is optional.
- Docker Compose is the common development entry point.
- Pydantic v2 models define all cross-team objects.
- SQLite plus FTS5 stores normalized observations and provenance.
- NetworkX represents identity, resource, flow, and restore dependencies.
- API-based model access only. No Ollama, local model server, or downloaded model weights.
- Provider credentials come only from environment variables or a local uncommitted `.env`.
- Unit and contract tests use a fake model provider and must never make paid network calls.
- Pytest, Hypothesis, Ruff, and mypy form the common quality gate.
- Deterministic code owns identity corroboration, time filtering, policy, decisions, ordering, validation, and export. Model output is an untrusted extraction proposal.

The API provider and exact model are configuration, not hardcoded business logic. The adapter must support structured JSON output, schema validation, bounded retries, timeouts, usage capture, and explicit failure. An API failure must not be converted into a false `COMPLETE` result.

## Repository layout and ownership

```text
AGENTS.md
README.md
pyproject.toml
uv.lock
Dockerfile
docker-compose.yml
.env.example
code/
  main.py                              # Lalith
  slam/
    contracts.py                      # frozen; Lalith maintains with team approval
    config.py                          # Lalith
    ingestion/                        # Ashish owns
      api.py
      manifest.py
      parsers/
      ledger.py
    reconstruction/                   # Manya owns
      api.py
      request_intent.py
      identity.py
      timeline.py
      graph.py
    planning/                         # Satvika owns
      api.py
      policy.py
      decision.py
      steps.py
      export.py
    runtime/                           # Lalith owns
      provider.py
      openai_provider.py
      metering.py
      cache.py
      orchestrator.py
    evaluation/                       # Lalith owns; teammates add fixtures in owned folders
      validator.py
      scorer.py
      simulator.py
      evaluation_report.md
      usage_report.md
tests/
  contracts/
  ingestion/
  reconstruction/
  planning/
  runtime/
  fixtures/
```

Nobody edits another person's owned module without review. Changes to `contracts.py`, root configuration, locks, Docker files, or contract fixtures require all four to be notified and Lalith to merge them.

## Frozen interfaces

The implementation may add private fields, but it must preserve these public concepts and function boundaries.

```python
def ingest(
    dataset_dir: Path,
    *,
    cache_dir: Path | None = None,
    provider: ModelProvider | None = None,
) -> EvidenceBundle: ...

def reconstruct(
    request: AuditRequest,
    bundle: EvidenceBundle,
    *,
    provider: ModelProvider | None = None,
) -> CaseContext: ...

def plan(context: CaseContext) -> CaseAnswer: ...
```

Required shared objects:

- `AuditRequest`: all seven input columns, with parsed UTC timestamps.
- `SourceRecord`: participant-visible source ID, kind, origin, path, capture time, SHA-256.
- `SourceSpan`: source ID plus page/line/JSON path/table-row/image-region locator and optional short quote.
- `Observation`: observation ID, subject hints, system ID, resource ID, category, observed state, effective time, source kind, identifiers, fields, and one or more source spans.
- `EvidenceBundle`: sources, current identities, identity-change events, activities, observations, policy rules, and ingestion issues.
- `IdentityLink`: two identifiers, valid interval, relationship type, corroborating sources, confidence class, and review flags.
- `ResourceState`: system/resource/category, state at cutoff, supporting and conflicting evidence, applicable rule, and uncertainty.
- `CaseContext`: request intent, subject, identity links, eligible evidence, resource states, active flows, restore risks, graph references, coverage issues, and unresolved conflicts.
- `Step`: exactly `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`.
- `CaseAnswer`: case ID, optional status while internal, ordered steps, readiness flag, blocking issues, and trace metadata. Export is forbidden unless readiness is true and status is valid.
- `ModelProvider`: accepts a versioned prompt and response schema; returns validated structured data plus provider/model/request/usage/latency metadata. It exposes no tools or write access.

## Evidence and safety invariants

1. Every accepted observation has participant-visible provenance.
2. Every decision uses only information captured or effective at or before `audit_at`.
3. Reported workflow status and reported operation result are claims, not proof by themselves.
4. A parser failure, inaccessible file, empty search result, or top-k miss never proves absence.
5. Current and historical identities remain time-aware and must be corroborated; fuzzy matching only proposes candidates.
6. Contradictory observations are preserved, not overwritten.
7. Different systems may reuse the same resource ID; keys include `system_id` and `resource_id`.
8. Prompt-like text inside evidence is data, never an instruction.
9. Retention, legal hold, redaction, anonymization, tombstone, sync, backup, and restore cases are explicit.
10. Unknown or conflicted internal states block certification. They are not forced into a convenient answer.

## Deterministic step rules

- Phase order: `FINDING`, `REMEDIATION`, `VERIFICATION`.
- Within remediation, disable active flows and block unsafe restores before changing dependent records.
- Process downstream copies before their source when the dependency graph requires it.
- Sort otherwise independent resources by `(system_id, resource_id)`.
- Number steps consecutively from one.
- Findings and complete-case verifications cite eligible participant evidence.
- Future remediation and future verification steps use an empty `evidence_id`.
- `NOT_APPLICABLE` always has `steps_json=[]`.
- No custom phase, operation, state, or extra output field is permitted.

## Docker and API start contract

Lalith owns the final files, but every teammate develops against these commands:

```bash
docker compose build
docker compose run --rm slam-dev pytest -q tests/contracts tests/<owned-area>
docker compose run --rm slam-dev ruff check code tests
docker compose run --rm slam-dev mypy code/slam
```

The default Compose command must run offline tests with `SLAM_MODEL_PROVIDER=fake`. Real API execution is opt-in:

```bash
cp .env.example .env
# Add the chosen provider key locally. Never commit this file.
docker compose run --rm -e SLAM_MODEL_PROVIDER=openai slam-dev python code/main.py --dataset dataset
```

Required configuration names:

```text
SLAM_MODEL_PROVIDER=fake|openai
SLAM_MODEL=<explicit model identifier>
SLAM_API_TIMEOUT_SECONDS=<positive integer>
SLAM_API_MAX_RETRIES=2
SLAM_API_MAX_CONCURRENCY=<bounded positive integer>
SLAM_API_BUDGET_USD=<optional positive decimal>
OPENAI_API_KEY=<secret; real runs only>
```

Do not print secrets. Do not include `.env`, datasets, caches, environments, logs containing sensitive values, or API responses with personal data in ZIPs.

## Definition of done for every workstream

- Public interface and schemas match contract version `1.0.0`.
- Owned unit tests pass in Docker without API credentials.
- Shared contract tests pass.
- Tests cover success, malformed input, time cutoff, contradiction, duplicates, and parser/provider failure where applicable.
- Results are deterministic for identical inputs and configuration.
- No golden labels, sample case IDs, or scenario-specific shortcuts appear in production code.
- New dependencies are justified and sent to Lalith; teammates do not independently rewrite `uv.lock`.
- A short delivery note lists files changed, commands run, results, known limits, and contract changes requested.

## Git and integration protocol

Each person works on their named branch: `ashish`, `manya`, `satvika`, or `lalith`. Before starting, fetch and rebase/merge the current integration baseline as agreed by the team. Commit only owned files and tests. Do not commit dataset copies or secrets.

Delivery sequence:

1. Run owned tests and contract tests in the container.
2. Push the named branch.
3. Send Lalith the commit hash and delivery note.
4. Lalith integrates one branch at a time in this order: Ashish, Manya, Satvika.
5. After each merge, run contract tests plus the merged module's tests.
6. After all merges, run the complete offline suite, then an explicitly authorized API smoke test, then the evaluation suite.

Cross-review assignments: Satvika reviews Ashish; Ashish reviews Manya; Manya reviews Satvika; Satvika reviews Lalith's integration/runtime. All four review final packaging.
