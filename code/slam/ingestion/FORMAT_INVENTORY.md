# Ingestion format inventory and status

Interim report from inspecting the public participant dataset (`dataset/`, 94 evidence files).
Counts below describe this corpus only and must not be hard-coded in production code.
No participant values (emails, names, phones) are reproduced here.

## Corpus

| Item | Finding |
|---|---|
| Manifest `evidence_files.csv` | 94 rows; columns `file_id, file_path, origin, captured_at`; **no hash column** (SHA-256 must be computed) |
| Manifest integrity | unique IDs and paths, all paths safe and present, all times `...Z`, no unlisted files, no duplicate content |
| Formats (by extension, confirmed by content) | 24 SQL, 28 JSON, 26 log, 11 PNG, 4 PDF, 1 TXT. No extension/content mismatches |
| Origins | 30 distinct (e.g. `service_readback_logs`, `customer_data_read_replica_capture`, `support_platform`) |
| Encoding | every text-like file is UTF-8 without BOM and LF only; 14 contain non-ASCII |
| Tabular files | `deletion_requests` 518, `sample_deletion_requests` 32, `user_identities` 850, `user_audit_log` 306, `system_activity` 4011, `deletion_rules` 15. No blanks, duplicate IDs, malformed rows or non-`Z` times |

## Per-format findings and parser consequences

**SQL (24).** Two shapes: (a) generic `customer_data_*` tables with `record_json TEXT CHECK (json_valid(...))`,
so a second JSON pass is needed for the nested record; (b) typed `inventory_*` snapshots with one table per
data category plus `snapshot_scope(origin_system, captured_at)`. Header comments come as `Key: value` and
`key=value`. Statements used: `PRAGMA foreign_keys=ON`, `BEGIN/COMMIT`, `CREATE TABLE`, `CREATE INDEX`, `INSERT`.
`ATTACH` never occurs as a statement (the word appears inside `ticket_attachments` data).
Replica files compare a primary with replicas, so conflicting copies must be kept side by side.

**JSON (28).** Four top-level shapes: `{exported_at, snapshots[{captured_at, data_store, collection, records}]}`,
`{exported_at, origin, record_count, records[{recorded_at, system, resource_id, record_type, result, subject_reference}]}`,
`{captured_at, collection, records, source}`, and `{exported_at, region, service_exports{service: {lookup arrays}}}`.
`exported_at` equals the manifest `captured_at` in every file. No duplicate keys. Parser must keep JSON paths.

**Logs (26).** Six line layouts across 16 filename families (all 2,211 lines parse), all starting with an ISO-Z timestamp: `key=value`, ` | ` delimited,
JSON object after the timestamp, RFC5424-style syslog, bracketed `[LEVEL] [component]`, and `requestId=... message="..."`
with escaped inner quotes. Parser must be chosen by content, fall back to raw lines, and keep line ranges.

**TXT (1).** Header block plus pipe-delimited rows `time | system | resource | category | state | value`.
Emails appear in mixed case.

**PDF (4).** ReportLab output, 1-2 pages, real text layer (ASCII85+Flate streams, `Tj` strings placed by
absolute coordinates in table-like cells). No encryption, JavaScript, Launch or URI markers. Deterministic
extraction with page and position provenance is feasible; no OCR needed.

**PNG (11).** 1500-1800 px RGB admin-console screenshots, no metadata chunks, no text layer. They are table
views with a detail pane. Dates in tables omit the year, so the year must come from the detail pane or the
manifest capture time. OCR or the vision adapter is required.

## Facts that matter downstream

- 20 request emails are mixed-case and the evidence text also mixes case: keep originals, add a normalized key.
- 518 requests map to 517 distinct emails (case-insensitive), so one subject appears in two cases.
- SQL comment lines include directive-like prose ("Compare the primary and any replica tables...").
  They are stored as comment evidence and never acted on. A regex scan of the text evidence found no
  override-style instructions; PDFs and images were not scanned for them.

## Status

All components are implemented and tested; see [INGESTION_PLAN.md](INGESTION_PLAN.md) for the
design, the vocabulary downstream code must know, verification results and known limits, and
[CORPUS_REPORT.md](CORPUS_REPORT.md) for measured coverage (94/94 sources parsed).

What this inventory predicted held up on real data: all 2,211 log lines parse across six layouts,
the four PDFs have a usable text layer, SQL replays cleanly in the sandbox (after allowing SQLite's
own catalog update and `REINDEX`, which a naive deny-by-default sandbox refuses), and the 11
screenshots are readable by Tesseract (mean confidence 84 to 92).
