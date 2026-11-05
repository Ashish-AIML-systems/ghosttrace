"""Normalize parser facts into contract ``Observation`` objects.

This is the one place where source vocabulary becomes shared vocabulary. It
never merges systems, resources, times, replicas or contradictory states: each
fact becomes its own observation keyed by system and resource, with the
original record kept verbatim under ``fields["source"]``.

Every judgement it makes is recorded next to the result: ``state_basis`` says
how the state was derived, ``evidence_nature`` separates direct observations
from claims, and identifiers keep their original spelling alongside a
normalized lookup key. No deletion status, step or policy decision is produced.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from slam.contracts import ExtractionProvenance, Observation, SourceKind

from .issues import Issue
from .parsers.base import ParseOutput, RawFact, SourceContext
from .vocab import (
    COLLECTIONS,
    EMAIL_HASH_RE,
    EMAIL_RE,
    IDENTIFIER_FIELDS,
    PHONE_RE,
    SUBJECT_KEY_FIELDS,
    USER_ID_RE,
    category_for_resource,
)

NORMALIZER_VERSION = "1.0.0"

_VOLATILE_EXTRACTION = ("request_id", "latency_ms", "input_tokens", "output_tokens")
_EMPTY_TOKENS = frozenset({"", "null", "none", "n/a", "[redacted]", "no direct identifier"})
_NESTED_RECORDS = ("profile", "document")
_TEXT_FIELDS = ("message_text", "message_excerpt", "note")
_RESULT_TOKENS = {
    "found": "PRESENT",
    "hit": "PRESENT",
    "present": "PRESENT",
    "not_found": "NOT_FOUND",
    "miss": "NOT_FOUND",
}
_TRUE = frozenset({"true", "1", "yes", "y"})
_FALSE = frozenset({"false", "0", "no", "n"})


def as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value) if value in (0, 1) else None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
    return None


def _usable(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value.strip().lower() not in _EMPTY_TOKENS else None


def normalize_phone(value: str) -> str:
    return re.sub(r"[^\d+]", "", value)


def classify(value: str) -> str | None:
    """Identifier type of a free-standing value by its shape, or ``None`` if opaque."""
    candidate = value.strip()
    if EMAIL_RE.fullmatch(candidate):
        return "email"
    if USER_ID_RE.fullmatch(candidate):
        return "user_id"
    if EMAIL_HASH_RE.fullmatch(candidate):
        return "email_hash"
    if PHONE_RE.fullmatch(candidate):
        return "phone"
    return None


def json_safe(value: Any) -> Any:
    """Make a source value JSON-serialisable without losing information."""
    if isinstance(value, bytes):
        return {"hex": value.hex()}
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


class _Identifiers:
    """Collects identifiers, keeping the first value of each type and every other one."""

    def __init__(self) -> None:
        self.primary: dict[str, str] = {}
        self.extra: dict[str, list[str]] = {}
        self.from_text: list[str] = []

    def add(self, kind: str, value: str) -> None:
        if kind not in self.primary:
            self.primary[kind] = value
        elif value != self.primary[kind] and value not in self.extra.setdefault(kind, []):
            self.extra[kind].append(value)


def _collect_identifiers(fact: RawFact) -> _Identifiers:
    ids = _Identifiers()
    data = fact.data
    flat: dict[str, Any] = dict(data)
    for key in _NESTED_RECORDS:
        nested = data.get(key)
        if isinstance(nested, Mapping):
            flat.update({str(k): v for k, v in nested.items()})
    for key, raw in flat.items():
        value = _usable(raw)
        if value is None:
            continue
        if key in IDENTIFIER_FIELDS:
            ids.add(IDENTIFIER_FIELDS[key], value)
        elif key in SUBJECT_KEY_FIELDS:
            kind = classify(value)
            if kind:
                ids.add(kind, value)
    for value in fact.subject_keys:
        usable = _usable(value)
        kind = classify(usable) if usable else None
        if usable and kind:
            ids.add(kind, usable)
    for key in ("emails", "phones", "user_ids"):
        listed = data.get(key)
        if isinstance(listed, list):
            kind = {"emails": "email", "phones": "phone", "user_ids": "user_id"}[key]
            for item in listed:
                if isinstance(item, str):
                    ids.add(kind, item)
    for key in _TEXT_FIELDS:
        text = data.get(key)
        if isinstance(text, str):
            for email in EMAIL_RE.findall(text):
                ids.add("email", email)
                if email not in ids.from_text:
                    ids.from_text.append(email)
    return ids


def _identifier_view(ids: _Identifiers) -> tuple[dict[str, str], tuple[str, ...]]:
    out = dict(ids.primary)
    hints: set[str] = set()
    if "email" in out:
        out["email_normalized"] = out["email"].strip().lower()
        hints.add(out["email_normalized"])
    if "phone" in out:
        out["phone_normalized"] = normalize_phone(out["phone"])
        hints.add(out["phone_normalized"])
    for kind in ("user_id", "customer_reference", "email_hash"):
        if kind in out:
            hints.add(out[kind].strip().lower() if kind == "email_hash" else out[kind].strip())
    for kind, values in ids.extra.items():
        for value in values:
            if kind == "email":
                hints.add(value.strip().lower())
            elif kind in ("user_id", "customer_reference"):
                hints.add(value.strip())
    return out, tuple(sorted(hints))


def derive_state(fact: RawFact) -> tuple[str, str]:
    """(state, basis). The basis names the rule so a reader can audit the choice."""
    layout = fact.layout
    data = fact.data
    if layout.endswith(".anchor") or layout.endswith(".document"):
        return "PRESENT", "document_listing"
    if layout == "sql.scope":
        return "SCOPED", "snapshot_scope"

    token = fact.state or _usable(data.get("result"))
    if token:
        mapped = _RESULT_TOKENS.get(token.strip().lower())
        return (mapped or token.strip().upper()), "reported_result"
    for key in ("http_status", "status_code"):
        code = data.get(key)
        if code is not None:
            text = str(code).strip()
            if text == "404":
                return "NOT_FOUND", key
            if text.startswith("2"):
                return "PRESENT", key
    hits = data.get("hits")
    if isinstance(hits, Mapping) and str(hits.get("total", "")).strip().isdigit():
        return ("PRESENT" if int(str(hits["total"]).strip()) > 0 else "NOT_FOUND"), "hits_total"
    for key in ("rows", "total_hits"):
        count = data.get(key)
        if count is not None and str(count).strip().isdigit():
            return ("PRESENT" if int(str(count).strip()) > 0 else "NOT_FOUND"), key
    enabled = as_bool(data.get("enabled"))
    if enabled is not None:
        return ("ACTIVE" if enabled else "DISABLED"), "enabled"
    for key in ("restore_allowed", "eligible"):
        allowed = as_bool(data.get(key))
        if allowed is not None:
            return ("RESTORABLE" if allowed else "BLOCKED"), key
    decision = _usable(data.get("decision"))
    if decision and decision.lower() in ("allow", "deny"):
        return ("RESTORABLE" if decision.lower() == "allow" else "BLOCKED"), "decision"
    for key in ("available", "download_available"):
        available = as_bool(data.get(key))
        if available is not None:
            return ("PRESENT" if available else "UNAVAILABLE"), key
    if isinstance(data.get("message_text"), str) and data["message_text"].strip() == "[REDACTED]":
        return "REDACTED", "message_text"
    return "PRESENT", "row_present" if layout.startswith(("sql.", "json.")) else "default_read"


def _category(fact: RawFact, resource: str) -> tuple[str, str]:
    """(category, basis)."""
    if fact.category:
        return fact.category, "explicit"
    if fact.layout == "sql.scope":
        return "SNAPSHOT_SCOPE", "snapshot_scope"
    record_type = fact.data.get("record_type")
    if isinstance(record_type, str) and record_type:
        return record_type, "record_type"
    if fact.collection and fact.collection in COLLECTIONS:
        return COLLECTIONS[fact.collection][0], "collection"
    implied = category_for_resource(resource)
    if implied is not None:
        return implied[0], "resource_prefix"
    if resource.startswith("ORD-"):
        return "ORDER_REFERENCE", "order_reference"
    if fact.layout.endswith(".document"):
        return "DOCUMENT", "document"
    if fact.collection:
        return fact.collection.upper(), "native_collection"
    return "UNCLASSIFIED", "none"


def _system(fact: RawFact, resource: str, ctx: SourceContext) -> tuple[str, str]:
    if fact.system_id:
        return fact.system_id, "explicit"
    if fact.collection and fact.collection in COLLECTIONS and COLLECTIONS[fact.collection][1]:
        return str(COLLECTIONS[fact.collection][1]), "collection"
    implied = category_for_resource(resource)
    if implied is not None:
        return implied[1], "resource_prefix"
    return ctx.origin, "manifest_origin"


def _resource(fact: RawFact, ctx: SourceContext) -> str | None:
    if fact.resource_id:
        return fact.resource_id
    if fact.layout == "sql.scope" and fact.system_id:
        return f"snapshot_scope:{fact.system_id}"
    if fact.layout.endswith(".document"):
        return ctx.source_id  # the document itself, citable by its file id
    return None


def observation_id(payload: Mapping[str, Any]) -> str:
    """SHA-256 of canonical sorted-key JSON of the payload, without volatile run metadata."""
    material = json.loads(json.dumps(payload, default=str))
    extraction = material.get("extraction")
    if isinstance(extraction, dict):
        for key in _VOLATILE_EXTRACTION:
            extraction.pop(key, None)
    material.pop("observation_id", None)
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize(
    ctx: SourceContext, kind: SourceKind, output: ParseOutput
) -> tuple[list[Observation], list[Issue]]:
    issues: list[Issue] = []
    observations: list[Observation] = []
    seen: set[str] = set()
    unmapped: set[str] = set()
    no_resource = 0
    duplicates = 0

    for fact in output.facts:
        resource = _resource(fact, ctx)
        if resource is None:
            no_resource += 1
            continue
        category, category_basis = _category(fact, resource)
        system, system_basis = _system(fact, resource, ctx)
        state, state_basis = derive_state(fact)
        if category_basis == "native_collection" or category == "UNCLASSIFIED":
            unmapped.add(fact.collection or "(none)")

        ids = _collect_identifiers(fact)
        identifiers, hints = _identifier_view(ids)
        fields: dict[str, Any] = {
            "layout": fact.layout,
            "evidence_nature": fact.nature,
            "state_basis": state_basis,
            "category_basis": category_basis,
            "system_basis": system_basis,
            "source": json_safe(fact.data),
        }
        if fact.collection:
            fields["native_collection"] = fact.collection
        if fact.container:
            fields["container"] = fact.container
        if fact.provenance.get("topology"):
            fields["snapshot_topology"] = fact.provenance["topology"]
        if ids.extra:
            fields["identifiers_all"] = {k: [ids.primary[k], *v] for k, v in ids.extra.items()}
        if ids.from_text:
            fields["identifiers_from_text"] = ids.from_text
        reported = fact.state or _usable(fact.data.get("result"))
        if reported:
            fields["reported_result"] = reported
        if fact.provenance.get("uncertain"):
            fields["uncertain"] = True

        provenance = fact.provenance
        extraction = ExtractionProvenance(
            parser_name=output.parser_name,
            parser_version=output.parser_version,
            source_sha256=ctx.sha256,
            model_provider=provenance.get("model_provider"),
            model=provenance.get("model"),
            request_id=provenance.get("request_id"),
            prompt_version=provenance.get("prompt_version"),
            input_tokens=provenance.get("input_tokens"),
            output_tokens=provenance.get("output_tokens"),
            latency_ms=provenance.get("latency_ms"),
        )
        draft = Observation(
            observation_id="0" * 64,
            subject_hints=hints,
            system_id=system,
            resource_id=resource,
            category=category,
            observed_state=state,
            effective_time=fact.effective_time,
            source_kind=kind,
            identifiers=identifiers,
            fields=fields,
            spans=(fact.span, *fact.more_spans),
            extraction=extraction,
        )
        digest = observation_id(draft.model_dump(mode="json"))
        if digest in seen:
            duplicates += 1
            continue
        seen.add(digest)
        observations.append(draft.model_copy(update={"observation_id": digest}))

    if no_resource:
        issues.append(
            Issue(
                "NORMALIZE_NO_RESOURCE",
                "warning",
                f"{no_resource} fact(s) named no resource and were not turned into observations",
                ctx.source_id,
            )
        )
    for name in sorted(unmapped):
        issues.append(
            Issue(
                "CATEGORY_UNMAPPED",
                "info",
                f"collection '{name}' has no category mapping; native name kept as the category",
                ctx.source_id,
            )
        )
    if duplicates:
        issues.append(
            Issue(
                "OBSERVATION_DUPLICATE",
                "info",
                f"{duplicates} identical observation(s) collapsed",
                ctx.source_id,
            )
        )
    return observations, issues
