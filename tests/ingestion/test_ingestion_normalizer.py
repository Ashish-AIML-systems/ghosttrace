from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from ingestion_helpers import CAPTURED, SHA, ctx
from slam.contracts import SourceKind
from slam.ingestion.normalizer import (
    as_bool,
    classify,
    derive_state,
    normalize,
    normalize_phone,
    observation_id,
)
from slam.ingestion.parsers.base import ParseOutput, RawFact, json_span, line_span

WHEN = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


def fact(data: dict[str, Any] | None = None, **kw: Any) -> RawFact:
    base: dict[str, Any] = {
        "layout": "json.snapshot",
        "effective_time": WHEN,
        "span": json_span("evidence_01", "$.records[0]"),
        "data": {"resource_id": "account_1", **(data or {})},
        "system_id": "account_service",
        "resource_id": "account_1",
        "collection": "customer_profiles",
    }
    base.update(kw)
    return RawFact(**base)


def run(*facts: RawFact, kind: SourceKind = SourceKind.JSON):  # type: ignore[no-untyped-def]
    return normalize(ctx(), kind, ParseOutput("p", "1", tuple(facts), (), "parsed"))


# --- state derivation: every rule, with the basis that justified it --------------------


@pytest.mark.parametrize(
    ("data", "state", "basis"),
    [
        ({"http_status": "404"}, "NOT_FOUND", "http_status"),
        ({"status_code": 200}, "PRESENT", "status_code"),
        ({"rows": "0"}, "NOT_FOUND", "rows"),
        ({"rows": 3}, "PRESENT", "rows"),
        ({"hits": {"total": 0}}, "NOT_FOUND", "hits_total"),
        ({"hits": {"total": 2}}, "PRESENT", "hits_total"),
        ({"total_hits": "0"}, "NOT_FOUND", "total_hits"),
        ({"enabled": "false"}, "DISABLED", "enabled"),
        ({"enabled": True}, "ACTIVE", "enabled"),
        ({"enabled": 1}, "ACTIVE", "enabled"),
        ({"restore_allowed": False}, "BLOCKED", "restore_allowed"),
        ({"restore_allowed": 1}, "RESTORABLE", "restore_allowed"),
        ({"eligible": "true"}, "RESTORABLE", "eligible"),
        ({"decision": "deny"}, "BLOCKED", "decision"),
        ({"decision": "allow"}, "RESTORABLE", "decision"),
        ({"available": "false"}, "UNAVAILABLE", "available"),
        ({"download_available": True}, "PRESENT", "download_available"),
        ({"message_text": "[REDACTED]"}, "REDACTED", "message_text"),
        ({"result": "hit"}, "PRESENT", "reported_result"),
        ({"result": "miss"}, "NOT_FOUND", "reported_result"),
        ({"result": "IDENTIFIABLE"}, "IDENTIFIABLE", "reported_result"),
        ({"result": "anonymized"}, "ANONYMIZED", "reported_result"),
        ({}, "PRESENT", "row_present"),
    ],
)
def test_state_rules_and_their_basis(data: dict[str, Any], state: str, basis: str) -> None:
    assert derive_state(fact(data)) == (state, basis)


def test_explicit_state_beats_other_signals_and_log_default_is_labelled() -> None:
    assert derive_state(fact({"http_status": "404"}, state="FOUND")) == (
        "PRESENT",
        "reported_result",
    )
    assert derive_state(fact({}, layout="log.kv")) == ("PRESENT", "default_read")


def test_document_and_scope_layouts_have_their_own_states() -> None:
    assert derive_state(fact(layout="pdf.anchor")) == ("PRESENT", "document_listing")
    assert derive_state(fact(layout="sql.scope")) == ("SCOPED", "snapshot_scope")


def test_unknown_status_code_is_not_guessed() -> None:
    assert derive_state(fact({"http_status": "500"}))[1] == "row_present"


# --- helpers ----------------------------------------------------------------------------


def test_helpers() -> None:
    assert as_bool("TRUE") is True and as_bool(0) is False and as_bool("maybe") is None
    assert as_bool(2) is None and as_bool(None) is None
    assert normalize_phone("+971 (50) 482-7316") == "+971504827316"
    assert classify("Jane@Example.com") == "email" and classify("user_12") == "user_id"
    assert classify("a" * 64) == "email_hash" and classify("+34 612 847 593") == "phone"
    assert classify("no direct identifier") is None


# --- category / system / resource -------------------------------------------------------


def test_category_and_system_sources_are_recorded() -> None:
    (obs,), issues = run(fact())
    assert (obs.category, obs.system_id) == ("USER_PROFILE", "account_service")
    assert obs.fields["category_basis"] == "collection" and obs.fields["system_basis"] == "explicit"
    assert not issues


@pytest.mark.parametrize(
    ("kw", "category", "basis"),
    [
        (
            {"data": {"record_type": "SEARCH_INDEX_ENTRY"}, "collection": None},
            "SEARCH_INDEX_ENTRY",
            "record_type",
        ),
        ({"collection": None, "resource_id": "backup_9"}, "BACKUP_ARCHIVE", "resource_prefix"),
        (
            {"collection": None, "resource_id": "customer_export_5"},
            "USER_EXPORT",
            "resource_prefix",
        ),
        ({"collection": None, "resource_id": "ORD-2026"}, "ORDER_REFERENCE", "order_reference"),
        (
            {"collection": "mystery_table", "resource_id": "thing_1"},
            "MYSTERY_TABLE",
            "native_collection",
        ),
    ],
)
def test_category_fallback_chain(kw: dict[str, Any], category: str, basis: str) -> None:
    kw.setdefault("data", {})
    (obs,), issues = run(fact(**kw))
    assert obs.category == category and obs.fields["category_basis"] == basis
    if basis == "native_collection":
        assert [i.code for i in issues] == ["CATEGORY_UNMAPPED"]


def test_system_falls_back_to_prefix_then_manifest_origin() -> None:
    (by_prefix,), _ = run(fact(system_id=None, collection=None, resource_id="search_5"))
    assert (
        by_prefix.system_id == "search_service"
        and by_prefix.fields["system_basis"] == "resource_prefix"
    )
    (by_origin,), _ = run(fact(system_id=None, collection=None, resource_id="ORD-5"))
    assert (
        by_origin.system_id == "test_origin"
        and by_origin.fields["system_basis"] == "manifest_origin"
    )


def test_document_level_fact_is_keyed_by_the_documents_own_file_id() -> None:
    doc = fact(
        {"emails": ["a@x.com"]},
        layout="pdf.document",
        resource_id=None,
        system_id=None,
        collection=None,
    )
    (obs,), _ = run(doc, kind=SourceKind.PDF)
    assert (obs.resource_id, obs.category) == ("evidence_01", "DOCUMENT")


def test_scope_fact_gets_a_synthetic_resource_id() -> None:
    scope = fact(
        {},
        layout="sql.scope",
        resource_id=None,
        system_id="search_service",
        collection="snapshot_scope",
    )
    (obs,), _ = run(scope, kind=SourceKind.SQL)
    assert obs.resource_id == "snapshot_scope:search_service" and obs.category == "SNAPSHOT_SCOPE"


def test_fact_without_a_resource_is_reported_not_dropped_silently() -> None:
    observations, issues = run(fact(resource_id=None, data={}))
    assert observations == []
    assert [(i.code, i.severity) for i in issues] == [("NORMALIZE_NO_RESOURCE", "warning")]


# --- identifiers ------------------------------------------------------------------------


def test_identifiers_keep_original_spelling_and_add_normalized_keys() -> None:
    data = {
        "email": " Jane.Doe@Example.COM ",
        "phone": "+971 50 482 7316",
        "customer_reference": "user_7",
    }
    (obs,), _ = run(fact(data))
    # Case is never changed. The contract model trims surrounding whitespace on identifier
    # strings, so the exact original text lives in the verbatim source record.
    assert obs.identifiers["email"] == "Jane.Doe@Example.COM"
    assert obs.fields["source"]["email"] == " Jane.Doe@Example.COM "
    assert obs.identifiers["email_normalized"] == "jane.doe@example.com"
    assert obs.identifiers["phone_normalized"] == "+971504827316"
    assert set(obs.subject_hints) == {"jane.doe@example.com", "+971504827316", "user_7"}


def test_placeholder_values_are_not_identifiers() -> None:
    data = {"email": "null", "phone": "[REDACTED]", "name": "N/A", "email_hash": ""}
    (obs,), _ = run(fact(data))
    assert obs.identifiers == {} and obs.subject_hints == ()


def test_subject_keys_are_classified_by_shape() -> None:
    data = {
        "correlation_key": "user_211",
        "lookup_key": "Jane@Example.com",
        "subject_ref": "opaque",
    }
    (obs,), _ = run(fact(data, subject_keys=("a" * 64,)))
    assert obs.identifiers["user_id"] == "user_211"
    assert obs.identifiers["email"] == "Jane@Example.com"
    assert obs.identifiers["email_hash"] == "a" * 64
    assert "opaque" not in obs.identifiers.values()


def test_second_value_of_a_type_is_kept_not_lost() -> None:
    data = {"email": "first@x.com", "owner_email": "second@x.com"}
    (obs,), _ = run(fact(data))
    assert obs.identifiers["email"] == "first@x.com"
    assert obs.fields["identifiers_all"] == {"email": ["first@x.com", "second@x.com"]}
    assert "second@x.com" in obs.subject_hints


def test_nested_profile_identifiers_are_found() -> None:
    data = {"profile": {"email": "n@x.com", "full_name": "Nia"}, "status_code": 200}
    (obs,), _ = run(fact(data))
    assert obs.identifiers["email"] == "n@x.com" and obs.identifiers["name"] == "Nia"


def test_email_inside_free_text_is_exposed_and_marked() -> None:
    data = {"message_text": "Please call me, I am pat@example.com thanks"}
    (obs,), _ = run(fact(data, collection="support_conversations"))
    assert obs.identifiers["email"] == "pat@example.com"
    assert obs.fields["identifiers_from_text"] == ["pat@example.com"]


def test_document_identifier_lists_are_read() -> None:
    data = {"emails": ["a@x.com"], "phones": ["+34 612 847 593"], "user_ids": ["user_5", "user_6"]}
    (obs,), _ = run(fact(data, layout="pdf.anchor", collection=None, resource_id="support_5"))
    assert obs.identifiers["user_id"] == "user_5"
    assert obs.fields["identifiers_all"]["user_id"] == ["user_5", "user_6"]


# --- no merging, provenance, determinism -------------------------------------------------


def test_nothing_is_merged_across_systems_replicas_times_or_states() -> None:
    a = fact({"account_status": "ACTIVE"}, container="primary", span=json_span("e", "$.a"))
    b = fact({"account_status": "DELETED"}, container="replica", span=json_span("e", "$.b"))
    c = fact({"account_status": "ACTIVE"}, system_id="search_service", span=json_span("e", "$.c"))
    d = fact(
        {"account_status": "ACTIVE"},
        effective_time=datetime(2026, 9, 1, tzinfo=UTC),
        span=json_span("e", "$.d"),
    )
    observations, _ = run(a, b, c, d)
    assert len(observations) == 4 and len({o.observation_id for o in observations}) == 4
    assert {(o.system_id, o.resource_id) for o in observations} == {
        ("account_service", "account_1"),
        ("search_service", "account_1"),
    }
    assert [o.fields["source"]["account_status"] for o in observations[:2]] == ["ACTIVE", "DELETED"]


def test_original_record_is_kept_verbatim_and_flagged_as_observation() -> None:
    (obs,), _ = run(fact({"note": "keep me", "n": 3}))
    assert (
        obs.fields["source"]["note"] == "keep me" and obs.fields["evidence_nature"] == "observation"
    )
    assert (
        obs.fields["layout"] == "json.snapshot"
        and obs.fields["native_collection"] == "customer_profiles"
    )


def test_multiple_spans_are_carried() -> None:
    f = fact(more_spans=(line_span("evidence_01", 5, 6),))
    (obs,), _ = run(f)
    assert len(obs.spans) == 2 and obs.spans[1].line_range is not None


def test_identical_facts_collapse_with_a_note() -> None:
    observations, issues = run(fact(), fact())
    assert len(observations) == 1
    assert [(i.code, i.severity) for i in issues] == [("OBSERVATION_DUPLICATE", "info")]


def test_observation_id_is_deterministic_and_input_order_independent() -> None:
    first, _ = run(fact({"a": 1, "b": 2}))
    second, _ = run(fact({"b": 2, "a": 1}))
    assert first[0].observation_id == second[0].observation_id
    assert len(first[0].observation_id) == 64
    assert first[0].observation_id == observation_id(first[0].model_dump(mode="json"))


def test_observation_id_changes_when_content_changes() -> None:
    base, _ = run(fact({"x": 1}))
    for changed in (
        fact({"x": 2}),
        fact({"x": 1}, effective_time=datetime(2026, 8, 2, tzinfo=UTC)),
        fact({"x": 1}, span=json_span("evidence_01", "$.records[9]")),
        fact({"x": 1}, system_id="other_service"),
    ):
        other, _ = run(changed)
        assert other[0].observation_id != base[0].observation_id


def test_volatile_model_run_data_does_not_change_the_id_but_identity_does() -> None:
    def with_prov(**p: Any) -> str:
        (obs,), _ = run(fact(provenance={"model": "m1", "model_provider": "fake", **p}))
        return obs.observation_id

    base = with_prov(request_id="r1", latency_ms=5, input_tokens=1, output_tokens=2)
    assert with_prov(request_id="r2", latency_ms=900, input_tokens=9, output_tokens=9) == base
    assert with_prov(request_id="r1", model="m2") != base  # a different model is a different result


def test_extraction_provenance_names_parser_and_source_hash() -> None:
    (obs,), _ = run(fact())
    assert obs.extraction is not None
    assert (obs.extraction.parser_name, obs.extraction.source_sha256) == ("p", SHA)
    assert obs.effective_time == WHEN and WHEN != CAPTURED
