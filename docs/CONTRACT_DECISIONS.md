# Contract decisions (current contract 1.1.0)

This file resolves the ingestion questions raised on 2026-11-04. The Python definitions in
`code/slam/contracts.py` are authoritative.

## Evidence and provenance

- Ingestion computes SHA-256 from the raw source bytes. The supplied manifest has no hash column.
- `SourceRecord.source_id` is the manifest `file_id`; `path` is the safe repository-relative path.
- Every manifest item produces one `SourceRecord`, including failures. `parse_status` is exactly
  `parsed`, `partial`, or `failed`.
- `SourceSpan` contains exactly one structured locator: table row, line range, JSON path, PDF page
  and optional coordinates, or image rectangle. Quotes are optional and limited to 500 characters.
- `Observation.observation_id` is the lowercase SHA-256 of a canonical, sorted-key JSON payload
  excluding the ID itself. This makes duplicates deterministic across runs.
- Parser/model provenance is stored in `ExtractionProvenance` and may be attached to both the
  source record and each observation. It includes source hash, parser/version, provider/model/request
  ID, prompt/schema version, token usage, and latency. Model fields are null for deterministic parsers.
- `SourceKind` is a closed enum: `csv`, `json`, `log`, `text`, `pdf`, `image`, `sql`.
  `category` and `observed_state` are non-empty free strings because they are supplied by policy and
  heterogeneous evidence. Planning, not ingestion, maps them to the challenge's closed output states.

## Identity and request loading

- Preserve the original email text and add `email_normalized=email.strip().lower()` for matching.
  Never overwrite the original value; normalization is a lookup key, not display evidence.
- `EvidenceBundle` intentionally contains evidence and the four normalized CSV row types but no
  deletion requests. Ashish owns `load_requests(dataset_dir) -> tuple[AuditRequest, ...]` separately
  from `ingest(...)` so ingestion can run once and be reused across all cases.
- The normalized row types are `CurrentIdentity`, `IdentityChangeEvent`, `Activity`, and `PolicyRule`.
  They retain participant-visible row IDs as `source_id`, `audit_id`, `activity_id`, and `rule_id`.

## Cache ownership

Lalith's runtime owns extraction cache key construction; Ashish owns when ingestion reads/writes its
cached extraction payloads. The required helper is:

```python
build_model_cache_key(
    *,
    source_sha256: str,
    prompt_version: str,
    schema_version: str,
    provider: str,
    model: str,
    settings: Mapping[str, Any],
) -> str
```

Settings must include every extraction-affecting option, not credentials, filesystem locations, or
budget counters. Cache hits still receive usage metadata with `cache_hit=True` and are not counted as
provider calls.

## OCR and document dependencies

The approved non-AGPL stack is pypdf, Pillow, pytesseract, and the Debian `tesseract-ocr` package.
Ordinary contract tests make no network or model API calls. OCR quality and language coverage must be
measured on the supplied screenshots; OCR failure or low-confidence output becomes an ingestion issue
and never proof of absence.

## Reconstruction and planning interface (1.1.0)

- `CaseContext.policy_rules` carries the exact `EvidenceBundle.policy_rules` rows into `plan(context)`;
  planning remains a pure function and does not open dataset files.
- Identity, resource, and graph evidence IDs are participant-visible `file_id`, `activity_id`, or
  `audit_id` values. Observation SHA-256 IDs are internal fact identifiers and must not appear as output
  citations.
- `CaseContext.evidence_captured_at` maps participant-visible evidence IDs to timezone-aware capture or
  event times. It includes future-dated evidence so planning can explicitly exclude anything after
  `request.audit_at`.
- The output exporter contract is
  `export_output_csv(answers, required_case_ids, path) -> None`. It rejects defects; Lalith's validator
  independently re-reads the resulting CSV and checks case-specific evidence cutoffs.
