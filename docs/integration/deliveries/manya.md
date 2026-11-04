---
owner: manya
workstream: Request intent, identity, temporal state, dependency graph
status: READY_FOR_INTEGRATION
contract_version: 1.0.0
contract_sha256: 7beb34d395f8c05729e3fa7584eb21d82e4c9a130465038d03ae0c9e97a837bd
built_on: 0d02a57be96b70f055e69e7c0d16adb652b7b882
merge_after: ashish
last_updated: 2026-11-04
---

# Manya - request intent, identity, temporal state, graph

## Delivers

- `reconstruct(request, bundle, *, provider=None) -> CaseContext` through the frozen
  public interface in `code/slam/reconstruction/api.py`.
- Deterministic request intent, exact temporal identity resolution, cutoff-aware
  resource reconstruction, and bounded dependency/restore graph analysis.
- Offline reconstruction tests and fixtures under `tests/reconstruction/**` and
  `tests/fixtures/reconstruction/**`.

## Cross-owner edits

- `tests/contracts/test_owned_boundaries.py` (Lalith's): replaced only Manya's obsolete
  reconstruction-stub assertion with an empty-evidence non-fabrication assertion.

## Requires from others

| From | What | Why | Status |
|---|---|---|---|
| Ashish | `EvidenceBundle` and `AuditRequest` contract inputs | Reconstruction accepts only the frozen B1 boundary | MET on `dev` |
| Lalith | Frozen `ModelProvider` protocol and fake provider | Optional model fallback must remain testable and tool-free | MET on `dev` |
| Integrator | Meaning of participant-visible evidence references | Downstream planning must resolve every evidence ID | RESOLVED: source, activity, and audit IDs are used |

## Provides to others

| To | What | Where | Integration rule |
|---|---|---|---|
| Satvika | Grounded `CaseContext` | `code/slam/reconstruction/api.py` | Preserve conflicts and uncertainty; planning owns actions and policy |
| Lalith | Pure per-request reconstruction function | `code/slam/reconstruction/api.py` | Call through the frozen keyword-only provider interface |
| Ashish | Reconstruction fixtures and unit tests | `tests/reconstruction/**` | Keep tests offline and deterministic |

## Contract and dependency requests

No contract or dependency change is requested. The implementation uses the existing
`networkx` dependency. Evidence references intentionally use IDs visible in the input
bundle: `SourceRecord.source_id`, `Activity.activity_id`, and
`IdentityChangeEvent.audit_id`. They do not use internal observation IDs.

## Implemented behavior

- Classifies clear deletion and non-deletion requests deterministically, including a
  bounded multilingual vocabulary. Ambiguous text may use the injected provider, but
  only a schema-valid answer citing an exact request excerpt is accepted.
- Treats request and evidence text as untrusted data. Prompt-injection wording fails
  closed to `UNCLEAR`; the provider receives no tools or authority to mutate state.
- Resolves current and historical email identities with exact normalization and
  time-bounded identity links. Similar identifiers are never fuzzily merged.
- Excludes observations whose effective or source capture time is after `audit_at`,
  deduplicates observations, and folds terminal states deterministically.
- Gives direct observations precedence over claims, preserves same-time conflicts, and
  marks cross-system replica disagreements uncertain.
- Does not treat `NOT_FOUND` as absence unless an eligible same-system, same-source
  `SNAPSHOT_SCOPE` observation establishes coverage.
- Builds active data-flow and restore-risk edges, merges duplicate evidence references,
  and reports active graph cycles.
- Surfaces ingestion errors, relevant parse failures, uncertain observations, identity
  ambiguity, future evidence exclusions, graph gaps, and provider failures.

## Verification

The branch gate is containerized and offline:

```text
docker compose run --rm slam-dev pytest -q tests/contracts tests/reconstruction
docker compose run --rm slam-dev ruff check code/slam/reconstruction tests/reconstruction
docker compose run --rm slam-dev mypy code/slam/reconstruction
```

Unit coverage includes multilingual intent, injection resistance, provider grounding,
historical identities, non-merging of similar people, cutoff enforcement, observation
deduplication, absence semantics, evidence conflicts, replica disagreement, active flow
cycles, restore risks, and end-to-end `CaseContext` assembly.

## Known limits

- Intent rules cover common English, Spanish, Portuguese, French, German, Italian, and
  Japanese deletion phrases; unfamiliar wording remains `UNCLEAR` unless a provider is
  explicitly supplied.
- Identity linkage is deliberately exact. A typo or unsupported alias becomes a
  coverage issue instead of a guessed match.
- Policy rules are not present in `CaseContext`, so this subsystem reconstructs facts
  only. It does not decide final compliance status, remediation steps, or user output.
- Graph endpoints depend on normalized source metadata. Missing endpoint metadata is
  retained as an unknown endpoint and reported as a coverage issue.

## Integration notes

Review and merge after Ashish's ingestion boundary is stable. Satvika should consume
the returned context without discarding `coverage_issues`, `unresolved_conflicts`, or
the `uncertain` flags on resource states. Lalith should keep each case isolated and may
retry provider failures safely because reconstruction has no hidden mutable state.

The former reconstruction-stub assertion in
`tests/contracts/test_owned_boundaries.py` was replaced with an empty-evidence safety
assertion now that the implementation is present.
