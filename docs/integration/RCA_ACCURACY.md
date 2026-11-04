# RCA: why step-level accuracy is low (public samples: status 0.906, step F1 0.335)

Method: ran the real pipeline on the 32 public samples, diffed every case against
`sample_output.csv`, traced each missing step back to the files, and did not tune anything to the
key (AGENTS.md forbids case-family shortcuts). Reproduce: `python scripts/smoke_test.py --seed N`.

## Summary

| # | Root cause | Evidence | Effect | Status |
|---|---|---|---|---|
| 1 | **Records with no identifier cannot be attributed to a person.** 404 lookups, anonymized analytics and attachments carry null identifiers; the activity stream names only resource ids, never a subject (only 12 `LINK_RESOURCE_IDENTITY` rows do). | `analytics_9406` appears in exactly two places: an all-null log line and an `ANONYMIZE_RECORD` activity. `account_001` appears only in one `DELETE_RECORD` activity; the key cites `evidence_54`, a SQL snapshot that does not contain it. | 25 missing `VERIFY_RECORD_ABSENT`, 7 `VERIFY_RECORD_ANONYMIZED`, 4 `DELETE_RECORD`; 3 safe-side status misses | **Open - needs a team decision**, not a code fix |
| 2 | Timestamps are too loose to substitute for an identity link. | Worker activities sit -114..+74 min around `reported_at`, and bursts interleave several people. | Using time would invent false attributions | Rejected on purpose |
| 3 | Replica copies are not aliased to their primary (`support_replica` vs `support_platform`). | `case_10`: key reports `support_platform/support_002`, we hold `support_replica/support_002`. | 1/32 cases | Open, 3 resources corpus-wide |
| 4 | The right action for a support record (DELETE vs REDACT) depends on content ("shared context", rule 05), which ingestion does not expose as a field. | `case_07` (PDF record) key=DELETE, we REDACT. | 1-2/32 cases | Open |

## Defects found and FIXED on the way (they were hiding in the same numbers)

| Defect | Evidence | Fix |
|---|---|---|
| Intent classifier missed most deletion wording | 20/32 samples, 248/518 `UNCLEAR`, one false `NOT_APPLICABLE` | 32/32, 0/518 unclear; the 10 non-deletion requests match the 10 `CLASSIFY_REQUEST` claims |
| `DISABLE_DATA_FLOW` / `CHECK_*` / `BLOCK_RESTORE` read as risks | 116 flow + 58 restore edges | token-based activity classes |
| Plain search/export records counted as data flows | 303 of 417 flow edges | exact `DATA_FLOW` category |
| Info-level ingestion notes blocked certification | 204/518 contexts | only error/relevant-warning issues block |
| Injection guard missed plurals ("ignore all previous instructions") | found by a new test | `instructions?` |
| Contract 1.1.0 fields not populated | Lalith's `fa6076a` | reconstruction fills `policy_rules`, `evidence_captured_at`; `plan(context)` now works |

## Safety property that held throughout

0 false COMPLETE on the samples. All 3 status misses are the safe side (key COMPLETE, we INCOMPLETE).
Every uncertain or unattributable case degrades to INCOMPLETE, never to COMPLETE.

## What would close cause 1 (decision needed from Manya, Ashish, Satvika)

Either (a) a grounded owner link for account ids (e.g. an additional file the organizers can confirm),
or (b) accept that those verification steps cannot be produced, and score status only. A heuristic
based on `account_N` numbering or time proximity would be fitted to the samples and is not proposed.
