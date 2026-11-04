# Evaluation report

Scored with `slam.evaluation.scorer` against `dataset/sample_output.csv` (32 public cases, offline, no model call).

| Metric | Value |
|---|---|
| Case-level deletion-status accuracy | 0.906 |
| Exact case accuracy | 0.125 |
| Step precision / recall / F1 | 0.491 / 0.425 / 0.456 |
| Field-level accuracy | 0.603 |
| Sequence accuracy | 0.125 |
| False COMPLETE count | 0 |

Full run: 518 cases, statuses {'INCOMPLETE': 356, 'COMPLETE': 152, 'NOT_APPLICABLE': 10}, 1 not certified (uncertain), 0 failed.

## Additional evaluation cases (created by us)

`tests/planning/test_engine.py` holds three: a clean COMPLETE case, an INCOMPLETE case with an active flow and a restorable backup (flow disabled and restore blocked before records change, downstream copies before the profile), and a non-deletion request (NOT_APPLICABLE, no steps).

## Failures found and improvements made

- Intent recall rose from 20/32 to 32/32 samples (0 of 518 unclear) after adding deletion nouns, Korean/Chinese, negation and marketing scoping; a false NOT_APPLICABLE was fixed.
- Graph: `DISABLE_DATA_FLOW`/`BLOCK_RESTORE`/`CHECK_*` activities were being read as risks (116 flow + 58 restore edges) and 303 plain search/export records as flows; fixed.
- Known gap: records with no identifier (anonymized analytics, 404 lookups, attachments) cannot be attributed to a person from the data, so absent/anonymized verification steps are under-reported.
