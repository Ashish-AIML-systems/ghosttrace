# Manya build document

## Mission

Build request interpretation, historical identity resolution, temporal state reconstruction, and the resource/process dependency graph. Your subsystem converts one `AuditRequest` plus Ashish's `EvidenceBundle` into a grounded `CaseContext` at that request's `audit_at`. You do not apply final deletion policy, assign the final status, serialize steps, or write `output.csv`.

Read root `AGENTS.md`, `problem_statement.md`, and `team_handoff/SHARED_BUILD_CONTRACT.md` before coding. Contract version `1.1.0` is current; use the schema hash in `contracts/SCHEMA_SHA256`.

## Owned paths

```text
code/slam/reconstruction/**
tests/reconstruction/**
tests/fixtures/reconstruction/**
```

Do not edit ingestion internals, planning, runtime, Docker, shared contracts, or dependency locks. Consume the public contracts and submit change requests when necessary.

## Required flow

1. Interpret `request_text` as deletion-authorizing or non-deletion. Use deterministic multilingual patterns first and a bounded API proposal only for ambiguous text.
2. Match the request email to current or historical identifiers without assuming the workflow's reported status is true.
3. Build time-aware identity links among stable user IDs, emails, phones, and supported hashes.
4. Require corroboration for fuzzy candidates; never merge two people only because names or strings are similar.
5. Filter observations and activity by `audit_at`, while retaining later items only as excluded trace evidence.
6. Reconstruct each `(system_id, resource_id)` state from eligible observations, preserving contradictions and uncertainty.
7. Build a directed graph for identity relationships, resource copies, synchronization/import/indexing, backups, restores, and dependencies.
8. Detect active recreation paths, surviving downstream copies, unsafe restore paths, cycles, and missing coverage.
9. Return a validated `CaseContext` with provenance for every link/state and explicit blocking issues.

## Algorithms and rules

- Use exact stable IDs and exact supported identifier matches as strongest links.
- Normalize only where the data contract supports it. Do not assume arbitrary email case/whitespace/hash behavior beyond verified rules.
- Use temporal intervals for historical identifiers and prevent links that were impossible at the relevant time.
- RapidFuzz or similar scoring may rank review candidates, never establish identity alone.
- Prefer an event-sourced state fold: order eligible observations deterministically by effective time, capture time, source priority, and stable ID; retain conflicting terminal states rather than choosing silently.
- Graph node keys include type, system, and resource/identifier. Edge metadata includes relationship type, valid interval, provenance, and confidence class.
- A workflow success claim cannot override observed surviving data.
- Absence requires positive eligible evidence appropriate to that source; a missing search result or failed parser is not absence.

## Model/API boundary

The provider may propose request intent or extract an identity hint from ambiguous text. It cannot decide final identity, resource state, completeness, policy, or steps. Validate every proposal against deterministic rules and cited source spans. Use strict structured output, at most two repair retries, and explicit failure states. Fake-provider tests are the default; real calls are opt-in.

## Tests you must own

- Current email and historical email resolve to the same subject when audit history supports it.
- Similar people remain separate without corroboration.
- A historical identifier is not used outside its supported interval without a valid persistent link.
- Evidence after `audit_at` never changes reconstructed state.
- Same resource ID across two systems remains two nodes.
- Duplicate observations do not duplicate logical state.
- Conflicting replicas remain conflicted and block a false complete result downstream.
- An active sync from a surviving source creates a recreation path.
- A backup with an unblocked restore path is surfaced.
- Cycles are detected without infinite traversal.
- Non-deletion requests are recognized, including access, correction, export, and marketing-only requests.
- Prompt injection and malformed provider output do not control the pipeline.
- Reconstruction is deterministic under input-row shuffling and unrelated-user additions.

## Acceptance criteria

- Every identity link and resource state cites participant-visible provenance.
- `CaseContext` cleanly separates eligible, excluded-future, conflicting, and missing evidence.
- All graph traversals are bounded and deterministic.
- No final deletion status, output step, or policy action is produced.
- Contract and reconstruction tests pass in Docker without API credentials.
- A per-case trace can explain why each identifier/resource was included or excluded.

## AI coding agent start prompt

```text
Read AGENTS.md, problem_statement.md, SHARED_BUILD_CONTRACT.md, and this file completely. Implement only code/slam/reconstruction and tests/reconstruction for contract 1.1.0. Populate `CaseContext.policy_rules` from the bundle and `evidence_captured_at` with participant-visible `file_id`, `activity_id`, and `audit_id` timestamps, including post-cutoff evidence so planning can exclude it. Never use observation hashes as output evidence IDs. Begin with temporal identity and cutoff tests. Consume EvidenceBundle through its public interface and return CaseContext. Use deterministic exact/time-aware linking and event-sourced state reconstruction; fuzzy matching only proposes corroborated candidates. Build bounded dependency graphs for copies, sync/import, backups, restores, and cycles. The shared API provider may propose only ambiguous request intent or hints; it cannot decide identity, state, policy, status, or steps. Default every test to the fake provider. Do not edit contracts or locks; request changes explicitly. Run contract tests, owned tests, Ruff, and mypy in Docker, then deliver changed files, commands/results, known ambiguities, and contract requests.
```

## Delivery to Lalith

Push branch `manya` and send the commit hash, test report, unresolved identity/state cases, graph assumptions, performance notes, and contract-change requests. Ashish reviews this work before Lalith integrates it.
