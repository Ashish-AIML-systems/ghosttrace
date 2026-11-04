# Ashish build document

## Mission

Build the evidence-ingestion subsystem that turns every participant-facing source into a complete, queryable, provenance-preserving `EvidenceBundle`. Your work answers: “What sources exist, what grounded facts do they contain, when were those facts valid, and exactly where did each fact come from?” You do not decide whether deletion is complete and you do not create remediation steps.

Read first: root `AGENTS.md`, `problem_statement.md`, and `team_handoff/SHARED_BUILD_CONTRACT.md`. Give all three to your AI coding agent. The shared contract is version `1.0.0` and overrides guesses made by the coding agent.

## Owned paths

```text
code/slam/ingestion/**
tests/ingestion/**
tests/fixtures/ingestion/**
```

You may request contract changes, but must not directly alter shared contracts, Docker files, root dependency locks, planning, reconstruction, runtime, or evaluation code.

## Inputs and output

Inputs are the dataset directory, the evidence manifest, all tabular files, and every evidence file reachable from the manifest. Support CSV, JSON, text/log, SQLite-compatible SQL snapshots, PDF, and PNG/image evidence. Paths must be resolved safely under the dataset root; reject traversal and record the issue.

Output is one validated `EvidenceBundle`. Preserve raw-source hashes, source IDs, origins, capture times, parser identity/version, structured observations, parse warnings, conflicts, and extraction failures. A partially parsed bundle may be returned only when failures are explicit; failure is never silently treated as “no data.”

## Required components

1. Manifest loader that validates required columns, unique IDs, safe relative paths, file existence, timestamps, and hashes.
2. Loaders for deletion requests, current identities, identity audit history, system activity, rules, and evidence manifest.
3. Parser registry selected by verified content/type rather than filename alone.
4. JSON parser that preserves JSON paths and value types.
5. Text/log parser that preserves line ranges and original encoding decisions.
6. SQL parser using an isolated temporary SQLite database or a safe read-only parser. Never execute shell commands, extensions, attachments, or untrusted external references.
7. PDF parser preserving page and text-location provenance.
8. Image pipeline: deterministic metadata/OCR first; call the configured API vision/extraction adapter only for unresolved evidence and only through `ModelProvider`.
9. Normalizer that emits `Observation` objects without merging distinct systems, resources, times, replicas, or contradictory states.
10. SQLite/FTS5 evidence ledger with repeatable schema migration and idempotent ingestion.
11. Cache keyed by source hash, parser version, prompt version, response schema, provider, model, and relevant settings.

## Model/API boundary

The model may propose typed fields from difficult PDF/image/text evidence. It receives only the necessary source material and a strict schema. It has no tools, policy authority, credentials, or write access. Validate source IDs, locators, timestamps, systems, resources, and quotations after the API response. At most two bounded repair attempts are allowed. Refusal, truncation, invalid JSON, timeout, or budget exhaustion becomes an explicit ingestion issue.

Never let model output invent a file ID or turn an unverified interpretation into an established absence. Store provider/model/request ID, prompt/schema versions, usage, latency, and source hash; never store the API key.

## Tests you must own

- Every supported format produces stable observations and source spans.
- Duplicate ingestion is idempotent.
- Same resource ID in different systems stays separate.
- Conflicting replicas remain distinct.
- Evidence captured after a supplied cutoff remains available in the bundle but is marked with its real time for downstream exclusion.
- SQL cannot escape its sandbox or load extensions.
- A malicious instruction embedded in a PDF/image/log is treated as evidence text.
- Bad OCR/model output is rejected or marked uncertain.
- Parser failure is reported and does not become proof of absence.
- Hash/cache changes when source, schema, prompt, parser, provider, model, or settings change.
- Fake provider tests cover valid, malformed, refusal, timeout, and retry paths without network access.

## Acceptance criteria

- All manifest entries are attempted exactly once per source version and accounted for as parsed, partially parsed, or failed.
- Every accepted observation has at least one valid source span.
- Re-running identical input yields byte-stable normalized records aside from explicitly excluded run metadata.
- No decision status or `Step` is produced by ingestion.
- Contract and ingestion tests pass in Docker with no API key.
- A corpus inventory report lists source counts, format counts, failures, warnings, and parser coverage without revealing secrets.

## AI coding agent start prompt

```text
Read AGENTS.md, problem_statement.md, SHARED_BUILD_CONTRACT.md, and this file completely before editing. You are implementing only code/slam/ingestion and tests/ingestion for SLAM contract 1.1.0. Start by writing tests and a format inventory. Implement deterministic, provenance-preserving ingestion for all declared formats. Treat model output as an untrusted structured extraction proposal accessed only through the shared ModelProvider; default tests to the fake provider and never require an API key. Do not implement identity decisions, deletion policy, statuses, plans, or export. Do not edit shared contracts or dependency locks; write a change request if they are insufficient. Run contract tests, owned tests, Ruff, and mypy in Docker. Finish with a delivery note containing changed files, commands/results, risks, and requested contract changes.
```

## Delivery to Lalith

Push your work to branch `ashish`. Send the commit hash, inventory report, test results, any failed/partially parsed sources, new dependency requests, and contract-change requests. Satvika performs the primary peer review before integration.
