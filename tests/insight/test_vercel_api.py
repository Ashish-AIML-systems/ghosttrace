"""The Vercel explain function must behave like the local pipeline, not merely resemble it.

``dashboard/vercel/api/explain.py`` cannot import ``slam`` (that would ship the whole audit to a
serverless function), so it carries small copies of the prompt filler and the grounding check.
These tests pin the copies to the real code: same prompt bytes, same verdict on every stored model
reply and on corrupted ones, and an HTTP layer that never spends a token for a bad request.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from http.server import HTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from slam.insight import explain

ROOT = Path(__file__).resolve().parents[2]
VERCEL = ROOT / "dashboard" / "vercel"
INSIGHT = json.loads((ROOT / "dashboard" / "insight_data.json").read_text(encoding="utf-8"))


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load("vercel_build", VERCEL / "build.py")
api = _load("vercel_explain", VERCEL / "api" / "explain.py")
DATA = build.build_cases(ROOT / "dashboard", ROOT / "dataset" / "deletion_rules.csv")
LLM_CASES = [c for c in INSIGHT["cases"] if c.get("explain") and c["explain"]["source"] == "llm"]


@pytest.fixture(autouse=True)
def _fresh_window() -> Iterator[None]:
    api._RECENT.clear()
    yield
    api._RECENT.clear()


def test_template_and_system_message_are_the_ones_the_pipeline_uses() -> None:
    assert DATA["template"] == explain.USER_PROMPT
    assert DATA["prompt_version"] == explain.PROMPT_VERSION
    assert DATA["model"] == INSIGHT["llm"]["usage"]["model"]


@pytest.mark.parametrize(
    "example", INSIGHT["llm"]["prompt"]["examples"], ids=lambda e: e["case_id"]
)
def test_rebuilt_prompt_is_byte_identical_to_what_the_pipeline_sent(
    example: dict[str, Any],
) -> None:
    payload = DATA["cases"][example["case_id"]]["payload"]
    assert api.build_prompt(DATA["template"], payload) == example["prompt"]


def test_every_incomplete_case_has_a_payload_and_nothing_personal() -> None:
    incomplete = {c["id"] for c in INSIGHT["cases"] if c["status"] == "INCOMPLETE"}
    assert set(DATA["cases"]) == incomplete
    blob = json.dumps(DATA).lower()
    assert "request_text" not in blob and "@" not in blob


def test_stored_model_replies_pass_both_checkers_alike() -> None:
    assert len(LLM_CASES) == 80
    for case in LLM_CASES:
        payload = DATA["cases"][case["id"]]["payload"]
        stored = case["explain"]["explanation"]
        reply = api.clean_reply(stored)
        assert reply == stored  # the cleaner keeps a valid reply exactly as it is
        real = explain.check_grounding(
            explain.CaseExplanation.model_validate(stored), payload, DATA["systems"]
        )
        assert api.check_grounding(reply, payload, DATA["systems"]) == real


def _corruptions(reply: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    bad = copy.deepcopy(reply)
    bad["runbook"] = list(reversed(bad["runbook"])) if len(bad["runbook"]) > 1 else []
    out.append(bad)
    bad = copy.deepcopy(reply)
    bad["why_failed"] += " See also evidence_9999."
    out.append(bad)
    bad = copy.deepcopy(reply)
    bad["recreation_risk"] += " Check object_store as well."
    out.append(bad)
    bad = copy.deepcopy(reply)
    bad["runbook"].append(
        {"step_no": 99, "action": "x", "precondition": "y", "risk_if_skipped": "z"}
    )
    out.append(bad)
    return out


def test_corrupted_replies_get_the_same_verdict_as_the_real_checker() -> None:
    seen_rejection = 0
    for case in LLM_CASES[:40]:
        payload = DATA["cases"][case["id"]]["payload"]
        for bad in _corruptions(case["explain"]["explanation"]):
            real = explain.check_grounding(
                explain.CaseExplanation.model_validate(bad), payload, DATA["systems"]
            )
            mine = api.check_grounding(bad, payload, DATA["systems"])
            assert (mine is None) == (real is None), (case["id"], real, mine)
            seen_rejection += real is not None
    assert seen_rejection > 100  # the corruptions really are caught


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {"why_failed": "x"},
        {
            "why_failed": "x" * 901,
            "risk_drivers": [],
            "recreation_risk": "r",
            "runbook": [],
            "verification_note": "v",
        },
        {
            "why_failed": "w",
            "risk_drivers": [1],
            "recreation_risk": "r",
            "runbook": [],
            "verification_note": "v",
        },
        {
            "why_failed": "w",
            "risk_drivers": [],
            "recreation_risk": "r",
            "runbook": [
                {"step_no": True, "action": "a", "precondition": "p", "risk_if_skipped": "r"}
            ],
            "verification_note": "v",
        },
    ],
)
def test_clean_reply_refuses_shapes_the_schema_would_refuse(bad: Any) -> None:
    assert api.clean_reply(bad) is None


def test_parse_reply_tolerates_reasoning_blocks_and_code_fences() -> None:
    assert api.parse_reply('<think>hmm</think>```json\n{"a": 1}\n```') == {"a": 1}
    assert api.parse_reply("not json") is None


# ---- the endpoint ---------------------------------------------------------------------------

CASE = next(iter(DATA["cases"]))


def _good_reply(case_id: str) -> str:
    stored = next(c for c in LLM_CASES if c["id"] == case_id)["explain"]["explanation"]
    return json.dumps(stored)


@pytest.fixture
def server(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[str], tuple[int, dict[str, Any], str]]]:
    monkeypatch.setattr(api, "_DATA", DATA)
    httpd = HTTPServer(("127.0.0.1", 0), api.handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]

    def get(query: str) -> tuple[int, dict[str, Any], str]:
        url = f"http://127.0.0.1:{port}/api/explain{query}"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return (
                    response.status,
                    json.loads(response.read()),
                    response.headers["Cache-Control"],
                )
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read()), exc.headers["Cache-Control"]

    yield get
    httpd.shutdown()
    httpd.server_close()


def test_ping_reports_configuration_without_calling_the_model(
    server: Callable[[str], tuple[int, dict[str, Any], str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(api, "call_groq", lambda *a: calls.append("x"))
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    status, body, cache = server("?ping=1")
    assert (status, body["live"], body["configured"], cache) == (200, True, False, "no-store")
    monkeypatch.setenv("GROQ_API_KEYS", "k1, k2")
    assert server("?ping=1")[1]["configured"] is True
    assert calls == []


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?case=",
        "?case=../x",
        "?case=case_1&case=case_2",
        "?case=case_100&x=1",
        "?ping=1&case=case_100",
    ],
)
def test_malformed_requests_are_refused_before_any_model_call(
    server: Callable[[str], tuple[int, dict[str, Any], str]],
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    monkeypatch.setenv("GROQ_API_KEYS", "k1")
    monkeypatch.setattr(api, "call_groq", lambda *a: pytest.fail("the model was called"))
    status, body, cache = server(query)
    assert status == 400 and "error" in body and cache == "no-store"


def test_unknown_case_and_missing_key(
    server: Callable[[str], tuple[int, dict[str, Any], str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api, "call_groq", lambda *a: pytest.fail("the model was called"))
    monkeypatch.setenv("GROQ_API_KEYS", "k1")
    assert server("?case=case_999999")[0] == 404
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    assert server(f"?case={CASE}")[0] == 503


def test_good_reply_is_returned_in_the_page_shape_and_is_cacheable(
    server: Callable[[str], tuple[int, dict[str, Any], str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = LLM_CASES[0]["id"]
    seen: dict[str, Any] = {}

    def fake(keys: Any, model: str, system: str, prompt: str) -> tuple[str, dict[str, int]]:
        seen.update(keys=list(keys), model=model, system=system, prompt=prompt)
        return _good_reply(case_id), {"input": 1000, "output": 300}

    monkeypatch.setattr(api, "call_groq", fake)
    monkeypatch.setenv("GROQ_API_KEYS", "k1,k2")
    status, body, cache = server(f"?case={case_id}")
    assert status == 200 and cache == api.CACHE_OK
    record = body["explain"]
    assert (record["source"], record["model"], record["note"]) == ("llm", DATA["model"], "")
    assert (record["input_tokens"], record["output_tokens"]) == (1000, 300)
    assert record["explanation"] == LLM_CASES[0]["explain"]["explanation"]
    assert seen["keys"] == ["k1", "k2"] and seen["system"] == DATA["system_message"]
    assert seen["prompt"] == api.build_prompt(DATA["template"], DATA["cases"][case_id]["payload"])


def test_reply_that_is_not_grounded_is_dropped_not_shown(
    server: Callable[[str], tuple[int, dict[str, Any], str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = LLM_CASES[0]["id"]
    bad = json.loads(_good_reply(case_id))
    bad["why_failed"] += " It also touched evidence_9999."
    monkeypatch.setattr(api, "call_groq", lambda *a: (json.dumps(bad), {"input": 1, "output": 1}))
    monkeypatch.setenv("GROQ_API_KEYS", "k1")
    status, body, cache = server(f"?case={case_id}")
    assert status == 502 and "rejected" in body["error"] and cache == "no-store"
    assert "explain" not in body


def test_upstream_failure_message_never_contains_a_key(
    server: Callable[[str], tuple[int, dict[str, Any], str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "gsk_TESTSECRET0123456789"

    def boom(keys: Any, *rest: Any) -> Any:
        raise api.ExplainError(502, "the model API is unavailable: key#1 was refused or busy")

    monkeypatch.setattr(api, "call_groq", boom)
    monkeypatch.setenv("GROQ_API_KEYS", secret)
    status, body, _ = server(f"?case={CASE}")
    assert status == 502 and secret not in json.dumps(body)


def test_call_groq_fails_over_between_keys_and_hides_them(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    class Response:
        def __init__(self, text: str) -> None:
            self._text = text

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

        def read(self) -> bytes:
            return self._text.encode()

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        auth = request.get_header("Authorization") or ""
        sent.append(auth)
        if auth.endswith("bad"):
            raise urllib.error.HTTPError(request.full_url, 401, "no", {}, None)  # type: ignore[arg-type]
        reply = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }
        return Response(json.dumps(reply))

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    content, usage = api.call_groq(["bad", "good"], "m", "sys", "user")
    assert (content, usage) == ("{}", {"input": 7, "output": 3})
    assert sent == ["Bearer bad", "Bearer good"]
    with pytest.raises(api.ExplainError) as caught:
        api.call_groq(["bad"], "m", "sys", "user")
    assert "bad" not in caught.value.message.replace("bad request", "")


def test_instance_call_cap_stops_a_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    case_id = LLM_CASES[0]["id"]
    monkeypatch.setattr(
        api, "call_groq", lambda *a: (_good_reply(case_id), {"input": 1, "output": 1})
    )
    for _ in range(api.MAX_CALLS_PER_WINDOW):
        api.explain_case(case_id, DATA, ["k"])
    with pytest.raises(api.ExplainError) as caught:
        api.explain_case(case_id, DATA, ["k"])
    assert caught.value.status == 429
