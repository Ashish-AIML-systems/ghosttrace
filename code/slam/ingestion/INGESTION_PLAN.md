# Evidence ingestion: design, status and hand-off

Owner: Ashish. Contract `1.0.0`. Reviewer: Satvika. Integrator: Lalith.
Corpus facts are in [FORMAT_INVENTORY.md](FORMAT_INVENTORY.md); measured coverage is in
[CORPUS_REPORT.md](CORPUS_REPORT.md) (generated, counts only, no participant values).

## 1. What it delivers

`ingest(dataset_dir, *, cache_dir=None, provider=None) -> EvidenceBundle` and
`load_requests(dataset_dir) -> tuple[AuditRequest, ...]`, both with the frozen signatures.

The bundle states what each source says, when, and exactly where. It never says whether a
deletion is complete: no status, step or policy decision is produced here.

Guarantees:

- every manifest row becomes exactly one `SourceRecord` per source version, `parsed`, `partial`
  or `failed`; a manifest row that cannot become a record is an error issue;
- every `Observation` has at least one valid `SourceSpan` (page/position, line range, table row,
  JSON path or image region) and parser provenance including the source SHA-256;
- failures are explicit issues. A parser error, unreadable file, empty page or OCR failure is
  never reported as "nothing found";
- distinct systems, replicas, times and contradictory states are never merged;
- identical input gives byte-identical output; unchanged sources are not re-processed.

## 2. Pipeline

```text
manifest ──► read bytes once, SHA-256 ──► detect kind from CONTENT (extension is a hint)
   │                                          │
   │          json │ log │ text │ pdf │ sql │ image
   │           └──────────┬──────────────────┘
   │                 RawFact  (verbatim data + span + container)
   │                      │
   │                 normalizer  (the only place vocabulary is applied)
   │                      │
   │             Observation (+ state_basis, evidence_nature, identifiers, subject_hints)
   ▼                      ▼
tables ─► identities, audit events, activities, rules ──► EvidenceBundle
                            ledger (SQLite + FTS5) keyed (source_id, sha256, fingerprint)
```

| Module | Job | Main tests |
|---|---|---|
| `manifest.py`, `paths.py`, `csvio.py`, `tables.py` | safe, line-aware loading; every row accepted or explicitly rejected | `test_ingestion_manifest/paths/tables` |
| `parsers/registry.py` | choose parser by verified content | `test_ingestion_registry` |
| `parsers/json_parser.py` | four container shapes, exact JSON paths, duplicate keys flagged | `test_ingestion_json_parser` |
| `parsers/log_parser.py` | six line layouts, trace join of subjects, noise counted | `test_ingestion_log_parser` |
| `parsers/text_parser.py`, `doctext.py` | pipe rows, prose; entity-anchor extraction shared with PDF/OCR | `test_ingestion_text_and_doctext` |
| `parsers/pdf_parser.py` | text layer through pypdf, page + position per line, nothing executed | `test_ingestion_pdf_parser` |
| `parsers/image_parser.py` | OCR first (rows, pane split), bounded model help only if unresolved | `test_ingestion_image_parser` |
| `parsers/sql_sandbox.py`, `sql_facts.py` | deny-by-default SQLite replay, row + line provenance | `test_ingestion_sql_sandbox`, `_sql_facts` |
| `normalizer.py`, `vocab.py` | RawFact to Observation; the only vocabulary | `test_ingestion_normalizer` |
| `ledger.py` | SQLite/FTS5 store, numbered migrations, idempotent writes | `test_ingestion_ledger` |
| `extraction_cache.py` | integrity-checked cache of validated model payloads | `test_ingestion_extraction_cache` |
| `api.py`, `report.py` | orchestration, crash isolation, corpus report | `test_ingestion_api/report`, `_real_dataset` |

## 3. Decisions that downstream code must know

1. **Effective time is when the evidence saw the state, not when the data last changed.** A row's
   `updated_at` or `created_at` stays in `fields.source`. SQL rows use their system's snapshot
   capture time, lookups use their own timestamp. This is the conservative choice for cutoffs.
2. **Evidence after a cutoff is kept** with its real time. Filtering by `audit_at` is the
   reconstruction stage's job.
3. **`observed_state` is a small vocabulary with an audit trail.** `fields.state_basis` names the
   rule (`http_status`, `rows`, `hits_total`, `enabled`, `restore_allowed`, `decision`,
   `reported_result`, `row_present`, `document_listing`, ...). States: `PRESENT`, `NOT_FOUND`,
   `ACTIVE`, `DISABLED`, `BLOCKED`, `RESTORABLE`, `ANONYMIZED`, `IDENTIFIABLE`, `REDACTED`,
   `UNAVAILABLE`, `SCOPED`. `NOT_FOUND` is a lookup result, not proof of deletion.
4. **`SNAPSHOT_SCOPE` observations are coverage evidence**: system X was captured at time T. They
   are what makes absence from a snapshot meaningful.
5. **Identifiers keep their original text** plus `email_normalized` / `phone_normalized`. The
   contract model trims surrounding whitespace; the exact original is in `fields.source`.
   `identifiers_all` holds any second value of the same type; `identifiers_from_text` marks
   addresses found inside free text.
6. **Document/OCR facts say "this id appears with these identifiers"**, nothing more.
   `fields.identifier_scope = "block"` means identifiers were inferred from the same block, and
   `uncertain = true` marks low OCR confidence, an id that looks like a truncation of another
   (`possible_truncation_of`), or model output that OCR text could not confirm.
7. **The model has no authority.** It is only consulted for unresolved images, through
   `ModelProvider`. Output is checked against strict id/email/phone formats and against OCR text;
   at most two repair attempts; refusal, truncation, timeout, budget, auth and quota become
   issues. Provenance (provider, model, request id, prompt/schema version, usage) is recorded.
8. **Systems are kept exactly as logged.** `profile_service` and `support_replica` are not
   folded into `account_service` / `support_platform`; whether they are the same is for
   reconstruction to decide.
9. **`observation_id`** is SHA-256 of canonical sorted-key JSON of the observation, excluding the
   id and volatile run data (request id, latency, token counts). The model name is included.

## 4. Verification

Run in Docker (`docker compose run --rm slam-dev ...`), Tesseract 5.3.0, real dataset mounted:

| Check | Result |
|---|---|
| `ruff check code tests` | all checks passed |
| `mypy code/slam` (strict) | no issues in 38 source files |
| `pytest -q` | 380 passed (ingestion ~340, shared contract/runtime tests unchanged) |
| Real corpus | 94/94 sources `parsed`, 3,020 observations, no error issues |
| Re-run | byte-identical bundle; unchanged sources read from the ledger |

The same suite runs offline on Windows without Tesseract: the 11 images then fail explicitly with
`OCR_ENGINE_UNAVAILABLE` + `IMAGE_UNRESOLVED`, which a test asserts.

Property-based fuzzing found one real defect (a NUL byte crashed the SQL sandbox); it is fixed and
has a regression test. A mutation check, where the sandbox authorizer is made to allow everything,
fails 15 attack tests, so those tests do detect a weakened sandbox.

### Handoff acceptance criteria

| Criterion | Status |
|---|---|
| All manifest entries attempted once per source version, accounted for | met |
| Every accepted observation has a valid span | met (contract-enforced, tested on real data) |
| Byte-stable re-run | met (tested on synthetic and real data) |
| No decision status or `Step` | met (asserted) |
| Contract and ingestion tests pass in Docker, no API key | met |
| Corpus inventory report without secrets | met (`CORPUS_REPORT.md`) |
| Fake-provider tests: valid, malformed, refusal, timeout, retry | met |
| Hash/cache changes with source, schema, prompt, parser, provider, model, settings | met (ledger fingerprint and extraction cache key) |

## 5. Known limits (honest)

- **No real model call has been made.** The vision fallback is verified only against the fake
  provider. Its accuracy on these screenshots, and its cost, are unmeasured. On this corpus OCR
  resolves every image, so the model path is not exercised by real data at all.
- **OCR association is heuristic.** Row grouping and pane splitting worked on all 11 screenshots
  (checked by eye against three of them), but a different console layout could mis-associate an
  identifier; such cases are flagged `uncertain` or `IMAGE_ASSOCIATION_UNRESOLVED`, not hidden.
- **Scanned PDFs are not OCR'd.** A page with no text layer is reported (`PDF_PAGE_NO_TEXT`).
- **Vocabulary is derived from this corpus** (`vocab.py`). An unknown collection keeps its native
  name and raises `CATEGORY_UNMAPPED`; an unknown log event with no resource id is counted, not
  interpreted. A hidden dataset with new collections will need vocabulary additions.
- **Rejected manifest rows have no `SourceRecord`**, because the contract cannot represent a
  missing hash or time. They are error issues instead (see requests).
- PDF position boxes are estimated from font size; fine for locating a line, not for cropping.

## 6. Changes outside ingestion, and requests

| Item | Detail |
|---|---|
| Edited `tests/contracts/test_owned_boundaries.py` | the test expecting `ingest` to raise `NotImplementedError` described the old stub. Replaced by a test that a dataset with no manifest returns an error issue instead of a silent empty bundle. **Lalith to confirm.** |
| `ingest_with_ocr(...)` | extra helper so OCR can be injected; `ingest` keeps the exact frozen signature, which a shared test checks |
| Contract request | allow a `failed` `SourceRecord` for a manifest row whose hash or time is unusable, so such rows are accounted for as sources and not only as issues |
| CLI note | `python -m slam.ingestion.report` needs `PYTHONPATH=code` (pytest already gets it from `pyproject.toml`) |
| CI secret scan | tests build their fake API key at runtime so the `sk-...` scan does not flag them |

## 7. Next steps

1. Satvika reviews against sections 3 and 5.
2. Lalith integrates and runs the shared suite; Manya reads section 3 before using states.
3. A separately authorised API smoke test to measure the vision fallback on a deliberately
   degraded screenshot, since real data never triggers it.
4. When the hidden dataset or new scenarios appear, extend `vocab.py` through a reviewed change,
   not inside parsers.
