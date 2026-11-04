# SLAM four-person build handoff

This directory divides the approved SLAM portable deletion-audit-agent plan into four independently buildable workstreams. It is a build specification, not a completed solution.

## Send these files

| Teammate | Primary document | Owned implementation area |
|---|---|---|
| Ashish | `01_ASHISH_EVIDENCE_INGESTION.md` | Evidence discovery, parsing, normalization, provenance |
| Manya | `02_MANYA_IDENTITY_TIMELINE.md` | Request intent, identity resolution, temporal state and dependency graph |
| Satvika | `03_SATVIKA_POLICY_PLANNING.md` | Policy evaluation, decision, ordered steps, CSV export |
| Lalith | `04_LALITH_RUNTIME_EVALUATION_INTEGRATION.md` | API-model adapter, metering, evaluation, Docker and final integration |

Every teammate must also receive `SHARED_BUILD_CONTRACT.md`. The shared contract is frozen at version `1.0.0`; nobody may silently change its schemas or module boundaries.

## Integration order

1. Lalith creates the shared repository skeleton and contract tests.
2. Ashish delivers a validated `EvidenceBundle`.
3. Manya consumes that bundle and delivers a `CaseContext`.
4. Satvika consumes the context and delivers a validated `CaseAnswer` and `output.csv`.
5. Lalith integrates, runs the full test/evaluation gates, meters API use, and packages the submission.

The role documents intentionally stop short of hardcoded challenge answers or organizer-only information.
