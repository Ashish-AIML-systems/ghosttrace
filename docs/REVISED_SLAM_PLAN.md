# Revised SLAM implementation plan

Status: approved build plan, not a completed implementation

Architecture revision: API-model access, portable deterministic audit engine

Shared contract: `team_handoff/SHARED_BUILD_CONTRACT.md` version `1.1.0`

## 1. Product to build

Build a portable AI-assisted deletion-audit agent. For every request, the system must determine whether deletion was actually requested; resolve the person across current and historical identifiers; find relevant data across supplied systems and evidence formats; reconstruct the state at the request's `audit_at`; apply the supplied deletion and retention rules; detect data flows and restore paths that can recreate prohibited data; and output an evidence-backed status and ordered plan.

This competition engine is the first deliverable. A later production platform may add live connectors, approvals, execution workers, and continuous monitoring, but those capabilities must not be presented as already implemented or evaluated.

## 2. Non-negotiable output contract

The root output is `output.csv` with exactly:

```text
case_id,deletion_status,steps_json
```

The only statuses are `COMPLETE`, `INCOMPLETE`, and `NOT_APPLICABLE`. Steps use only the official phases, operations, states, and seven fields. Decisions use only evidence eligible at or before `audit_at`. Reported workflow statuses and activity results are claims until supported by evidence.

`COMPLETE` requires evidence that every relevant copy has the required treatment, required retained records remain, and no active flow or unsafe restore path can recreate prohibited data. Uncertainty, parser failure, or a search miss must never become a false completion.

## 3. Architecture

```text
ingest every participant source once
             ↓
interpret request and resolve historical identity
             ↓
retrieve grounded evidence and filter by audit_at
             ↓
reconstruct records, replicas, flows, backups and restores
             ↓
apply policy with Judge–Evidence–Verify
             ↓
build deterministic findings, remediation and verification
             ↓
validate, export, score and report usage
```

Selected baseline:

- Python 3.11 and a locked `uv` environment.
- Pydantic v2 for shared data contracts.
- SQLite plus FTS5 for the evidence and provenance ledger.
- NetworkX for identity, copy, process, backup, and restore graphs.
- Explicit Python policy functions driven by `deletion_rules.csv`.
- Deterministic parsers for CSV, JSON, text/log, SQL, and PDF; OCR or vision escalation only where required.
- API-based structured extraction through a provider-neutral adapter.
- Pytest, Hypothesis, Ruff, and mypy quality gates.
- Static reports and run manifests; no server is required for the competition engine.

## 4. API-model boundary

There is no Ollama, local inference server, GGUF model, or GPU-specific build in the approved plan. The exact provider and model are explicit run configuration. Credentials come only from environment variables and are never logged, committed, cached in plaintext artifacts, or included in ZIPs.

The model may propose structured facts from difficult evidence or help interpret ambiguous request text. It has no tools, credentials, write access, identity authority, policy authority, or ability to assign final status or steps. Every response is schema-validated and checked against source IDs, spans, timestamps, and deterministic rules.

Required runtime controls:

- native structured output where available plus Pydantic validation;
- bounded output, timeout, concurrency, and at most two repair or retry attempts;
- explicit refusal, truncation, malformed-response, authentication, quota, timeout, and budget failures;
- cache keys containing source, prompt, schema, provider, model, and settings hashes;
- decision-cache keys also containing cutoff, eligible evidence, identity history, and policy version;
- fake provider for all ordinary tests;
- opt-in API calls protected by a configured spend ceiling;
- usage records for actual calls, cache hits, retries, latency, provider/model/request IDs, reported token fields, and versioned cost estimates.

An unavailable usage field is reported as unavailable, not invented.

## 5. Evidence and reconstruction rules

Ingest every manifest source before case retrieval so an initially narrow query cannot hide an unsearched file. Every accepted observation carries participant-visible provenance and preserves system, resource, event/capture time, parser/model version, and source hash.

Resolve stable user IDs, current and historical emails, phones, and supported hashes using time-aware links. Fuzzy matching may propose candidates but requires corroboration. Similar people remain separate. Distinct replicas and contradictions remain distinct. A shared resource ID is scoped by system.

Use an event-sourced temporal fold to reconstruct state at `audit_at`. Later evidence is retained in trace data but excluded from the answer. Positive evidence appropriate to the source is required to establish absence; missing or failed parsing cannot do so.

Build a dependency graph covering copies, indexes, exports, sync/import jobs, backups, restores, and cycles. Surface active flows and unsafe restore paths even when the primary record is absent.

## 6. Policy and planning

Use Judge–Evidence–Verify:

1. Judge the applicable supplied rule and required treatment.
2. Check that eligible evidence actually establishes the linked resource or process state.
3. Verify compliance or produce the supported finding and safe future work.

The plan must handle deletion, redaction, anonymization, retention, legal holds, shared-context records, analytics attribution, tombstones, backups, and restore controls. A tombstone keeps only the allowed stable reference and removes prohibited identifiers under the rule.

For incomplete cases, findings cite evidence. Future remediation and future verification use an empty evidence ID. Disable copying processes and block unsafe restores before changing dependent records. Process downstream copies before sources where the graph requires it. Topologically order dependencies, then use stable system and resource tie-breakers. Every remediated item receives a verification.

## 7. Team division

- Ashish owns evidence discovery, format parsers, normalization, provenance, ledger, and ingestion failure reporting.
- Manya owns request intent, time-aware identity resolution, state reconstruction, and dependency/recreation graphs.
- Satvika owns policy evaluation, final decision, deterministic steps, validation, and CSV export.
- Lalith owns shared contracts, Docker, API adapters, caching and metering, orchestration, evaluation, integration, and packaging.

Each role has a self-contained guide and AI-agent prompt under `team_handoff/`. All modules integrate only through shared contract version `1.1.0`. Shared contract and configuration changes are coordinated centrally instead of being silently rewritten by a single branch.

## 8. Evaluation before tuning

Implement the validator and evaluation harness before the complete engine. Measure status accuracy, full-case exact match, step precision/recall/F1, field and evidence-reference accuracy, exact sequence accuracy, false `COMPLETE`, invalid citations, retention or policy violations, runtime, calls, tokens, retries, cache behavior, and estimated cost.

Keep canonical exact-answer agreement separate from semantic evidence validation.

Create 20 scenario families with three development fixtures and two locked final fixtures per family: surviving replica; historical email; valid tombstone; exposed tombstone; sync recreation; restore risk; retained record; shared redaction; future evidence; similar people; duplicates; clean primary with active flow; prompt injection; non-deletion; parser failure; contradicted success; cross-system resource IDs; temporal identity; retention and hold boundaries; and insufficient or conflicting evidence.

Expected results are authored independently of prediction code. The 60 development fixtures are regression data. The 40 final fixtures remain locked; once inspected to guide a fix, a fixture is recorded as consumed rather than called untouched holdout.

## 9. Measured improvement cycles

Establish a baseline, group failures by root cause, propose testable changes, and implement one change at a time. Keep changes only when safety does not regress and the predefined metric order improves:

1. false completion, invalid evidence, and retention violations;
2. full-case exact match;
3. step F1;
4. sequence accuracy;
5. runtime, call, and cost efficiency without correctness loss.

Run up to six rounds per cycle and stop after two rounds without a qualifying gain. Start another cycle only for a new concrete and testable cause. Preserve the best qualified checkpoint and record rejected changes. Public samples and modeled plan convergence cannot establish hidden accuracy or “best possible” performance.

## 10. Docker and integration

Docker is the shared development environment and contains no local inference runtime. The default Compose service runs offline with `SLAM_MODEL_PROVIDER=fake`. A real API run is explicit, credentialed through a local `.env`, model-pinned, metered, and budget-limited.

Integration order is Ashish, Manya, then Satvika into Lalith's contract and runtime baseline. After every merge, run shared contract tests plus the merged module tests. Final qualification runs all tests and static checks, public evaluation, adversarial and metamorphic cases, a clean-container run, and only then an authorized API smoke or full run.

## 11. Delivery gates

1. Inspect every participant source and record coverage and failures.
2. Build contracts, fixtures, validators, and the offline container foundation.
3. Deliver deterministic ingestion, reconstruction, policy, step, and export stages.
4. Add bounded API assistance only for measured extraction or intent failures.
5. Run measured improvement cycles and adversarial review.
6. Freeze configuration and produce the final full-dataset run.
7. Generate `output.csv`, evaluation and usage reports, run manifest, static reports, logs, and agent traces from the qualified checkpoint.
8. Validate `code.zip` and exclude datasets, secrets, environments, caches, weights, API-response caches containing unnecessary personal data, and nested archives.

Success means a reproducible, evidence-grounded and validated agent with honest measured results and explicit limitations. This plan itself is not evidence that the implementation works.
