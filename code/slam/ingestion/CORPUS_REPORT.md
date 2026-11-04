# Corpus inventory report

Contract 1.0.0, ingestion 1.0.0. Generated from an `EvidenceBundle`; counts and codes only, no participant values.

## Sources

94 manifest entries ingested.

| format | parsed | partial | failed | total |
|---|---|---|---|---|
| image | 11 | 0 | 0 | 11 |
| json | 28 | 0 | 0 | 28 |
| log | 26 | 0 | 0 | 26 |
| pdf | 4 | 0 | 0 | 4 |
| sql | 24 | 0 | 0 | 24 |
| text | 1 | 0 | 0 | 1 |

## Parser coverage

| parser | parsed | partial | failed | observations |
|---|---|---|---|---|
| image | 11 | 0 | 0 | 37 |
| json | 28 | 0 | 0 | 890 |
| log | 26 | 0 | 0 | 1072 |
| pdf | 4 | 0 | 0 | 11 |
| sql | 24 | 0 | 0 | 969 |
| text | 1 | 0 | 0 | 41 |

## Observations

3020 observations.
369 carry no identifier, 0 came from a model, 1 are flagged uncertain.

### By category

| category | count |
|---|---|
| ACCOUNT_TOMBSTONE | 18 |
| ANALYTICS_PROFILE | 338 |
| BACKUP_ARCHIVE | 112 |
| DATA_FLOW | 245 |
| DOCUMENT | 3 |
| EMAIL_DELIVERY_LOG | 2 |
| LEGAL_HOLD_RECORD | 2 |
| MARKETING_PROFILE | 1 |
| ORDER_REFERENCE | 13 |
| RETAINED_ORDER_RECORD | 10 |
| SEARCH_INDEX_ENTRY | 488 |
| SECURITY_AUDIT_LOG | 669 |
| SNAPSHOT_SCOPE | 78 |
| SUPPORT_ATTACHMENT | 22 |
| SUPPORT_MESSAGE | 295 |
| USER_EXPORT | 60 |
| USER_PROFILE | 664 |

### By system

| system | count |
|---|---|
| account_admin_portal | 2 |
| account_history_service | 2 |
| account_service | 375 |
| analytics_platform | 348 |
| attachment_preview | 1 |
| backup_service | 121 |
| downstream_delivery_service | 2 |
| export_service | 68 |
| identity_service | 20 |
| integration_service | 255 |
| legal_retention_service | 6 |
| legal_service | 12 |
| marketing_platform | 1 |
| profile_service | 300 |
| search_index_admin | 1 |
| search_service | 498 |
| security_service | 680 |
| support_platform | 324 |
| support_replica | 4 |

### By state

| state | count |
|---|---|
| ACTIVE | 182 |
| ANONYMIZED | 10 |
| BLOCKED | 61 |
| DISABLED | 61 |
| IDENTIFIABLE | 37 |
| NOT_FOUND | 235 |
| PRESENT | 2281 |
| REDACTED | 34 |
| RESTORABLE | 40 |
| SCOPED | 78 |
| UNAVAILABLE | 1 |

## Tabular inputs

| table | rows |
|---|---|
| current_identities | 850 |
| identity_changes | 306 |
| activities | 4011 |
| policy_rules | 15 |

## Issues

24 issues.

| severity | code | count | example message |
|---|---|---|---|
| info | LOG_EVENTS_NOT_INTERPRETED | 24 | 68 entr(ies) named no resource or were lookup starts; not turned into observations (operational noise carries no record state) |

## Sources not fully parsed

None.
