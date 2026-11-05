"""Vercel function: ask the language model to explain one audited case, on demand.

The deployed dashboard is a static page. The audit, the LightGBM scores and the DBSCAN patterns are
computed before deployment and shipped inside the page. This function adds one thing a static page
cannot do: a live model call for the case the visitor has open.

    GET /api/explain?ping=1          is the model configured? (no tokens are spent)
    GET /api/explain?case=case_100   explain that case now

It follows the same rules as ``code/slam/insight/explain.py``, which stays the source of truth:

* the prompt is the same template filled with the same case JSON (built by ``build.py`` from the
  stored audit, never from ``request_text``, an email, a name or a phone number);
* the model explains and never decides: the reply must contain exactly the audit's remediation step
  numbers, in order, and may only mention ids and systems that are in the case facts;
* a reply that fails either check is refused, not shown. Nothing here writes a status or a step.

Only the standard library is used, so the function needs no dependency install. The Groq keys come
from the ``GROQ_API_KEYS`` environment variable (comma separated) and never leave this process.
``tests/insight/test_vercel_api.py`` checks the prompt and the grounding rule against the real code.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

DATA_FILE = Path(__file__).with_name("_cases.json")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_KEYS = 4
MAX_OUTPUT_TOKENS = 2048
CALL_TIMEOUT_SECONDS = 25
# Best-effort cap per warm instance. The real cost bound is that only 355 valid URLs exist and
# successful replies are cached by the CDN for a day.
MAX_CALLS_PER_WINDOW = 30
WINDOW_SECONDS = 600
CACHE_OK = "public, s-maxage=86400, stale-while-revalidate=86400"

_CASE_ID = re.compile(r"^case_\d{1,6}$")
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_ID_TOKEN = re.compile(r"\b[a-z][a-z_]*_\d+\b")

_RECENT: deque[float] = deque()
_RECENT_LOCK = threading.Lock()
_DATA: dict[str, Any] | None = None


class ExplainError(Exception):
    """A failure whose message is safe to show to the visitor (it never carries a key)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


ModelCall = Callable[[Sequence[str], str, str, str], tuple[str, dict[str, int]]]


def load_data() -> dict[str, Any]:
    global _DATA
    if _DATA is None:
        _DATA = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return _DATA


# ---------------------------------------------------------------------------------------------
# prompt, reply checks (mirrors code/slam/insight/explain.py)
# ---------------------------------------------------------------------------------------------


def build_prompt(template: str, payload: Mapping[str, Any]) -> str:
    return template.format(case_json=json.dumps(payload, separators=(",", ":"), sort_keys=True))


def parse_reply(content: str) -> Any:
    text = _THINK_BLOCK.sub("", content).strip()
    fenced = _CODE_FENCE.match(text)
    if fenced is not None:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except ValueError:
        return None


def _text(value: Any, limit: int) -> str | None:
    return value if isinstance(value, str) and len(value) <= limit else None


def clean_reply(raw: Any) -> dict[str, Any] | None:
    """The reply as the ``CaseExplanation`` schema defines it, or ``None`` if it does not fit."""

    if not isinstance(raw, dict):
        return None
    why = _text(raw.get("why_failed"), 900)
    recreation = _text(raw.get("recreation_risk"), 600)
    verification = _text(raw.get("verification_note"), 400)
    drivers = raw.get("risk_drivers")
    runbook = raw.get("runbook")
    if why is None or recreation is None or verification is None:
        return None
    if not isinstance(drivers, list) or len(drivers) > 6:
        return None
    if not all(isinstance(item, str) for item in drivers):
        return None
    if not isinstance(runbook, list) or len(runbook) > 30:
        return None
    entries = []
    for item in runbook:
        if not isinstance(item, dict):
            return None
        step = item.get("step_no")
        action = _text(item.get("action"), 400)
        precondition = _text(item.get("precondition"), 300)
        risk = _text(item.get("risk_if_skipped"), 300)
        if isinstance(step, bool) or not isinstance(step, int):
            return None
        if action is None or precondition is None or risk is None:
            return None
        entries.append(
            {
                "step_no": step,
                "action": action,
                "precondition": precondition,
                "risk_if_skipped": risk,
            }
        )
    return {
        "why_failed": why,
        "risk_drivers": list(drivers),
        "recreation_risk": recreation,
        "runbook": entries,
        "verification_note": verification,
    }


def _allowed(payload: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    ids = {str(payload["case_id"])}
    systems: set[str] = set()
    for finding in payload["findings"]:
        ids.update(re.findall(r"\brule_\d+\b", str(finding.get("policy", ""))))
    for item in (*payload["findings"], *payload["plan"]):
        ids.add(str(item["resource_id"]))
        systems.add(str(item["system_id"]))
        if item.get("evidence_id"):
            ids.add(str(item["evidence_id"]))
    for path in payload["recreation_paths"]:
        systems.update(path)
    return ids, systems


def check_grounding(
    reply: Mapping[str, Any], payload: Mapping[str, Any], all_systems: Sequence[str]
) -> str | None:
    """Why the reply is unusable, or ``None`` when it is grounded in the case facts."""

    wanted = [item["step_no"] for item in payload["plan"] if item["phase"] == "REMEDIATION"]
    if [entry["step_no"] for entry in reply["runbook"]] != wanted:
        return "runbook steps do not match the audit's remediation steps"
    text = " ".join(
        [
            reply["why_failed"],
            reply["recreation_risk"],
            reply["verification_note"],
            *reply["risk_drivers"],
            *(
                f"{e['action']} {e['precondition']} {e['risk_if_skipped']}"
                for e in reply["runbook"]
            ),
        ]
    )
    ids, systems = _allowed(payload)
    stray = sorted(set(_ID_TOKEN.findall(text)) - ids)
    if stray:
        return f"mentions ids that are not in the case facts: {', '.join(stray[:3])}"
    foreign = sorted(
        s
        for s in all_systems
        if s not in systems and re.search(rf"(?<![a-z_]){re.escape(s)}(?![a-z_])", text)
    )
    if foreign:
        return f"mentions systems that are not in the case facts: {', '.join(foreign[:3])}"
    return None


# ---------------------------------------------------------------------------------------------
# the model call
# ---------------------------------------------------------------------------------------------


def keys_from_env() -> list[str]:
    raw = os.environ.get("GROQ_API_KEYS", "")
    return [key.strip() for key in raw.split(",") if key.strip()][:MAX_KEYS]


def call_groq(
    keys: Sequence[str], model: str, system: str, prompt: str
) -> tuple[str, dict[str, int]]:
    """One chat completion. Keys are tried in order; the error text never contains a key."""

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
        }
    ).encode("utf-8")
    last = "no key was usable"
    for index, key in enumerate(keys, start=1):
        request = urllib.request.Request(
            GROQ_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "ghost-data-console/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=CALL_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403, 429} or exc.code >= 500:
                last = f"key#{index} was refused or busy (HTTP {exc.code})"
                continue
            raise ExplainError(
                502, f"the model API rejected the request (HTTP {exc.code})"
            ) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ExplainError(504, "the model API timed out") from None
            last = f"key#{index} could not reach the model API"
            continue
        except TimeoutError:
            raise ExplainError(504, "the model API timed out") from None
        except (ValueError, OSError):
            last = f"key#{index} sent an unreadable reply"
            continue
        try:
            content = str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise ExplainError(502, "the model API sent an unexpected reply") from None
        usage = payload.get("usage") if isinstance(payload, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        return content, {
            "input": int(usage.get("prompt_tokens", 0) or 0),
            "output": int(usage.get("completion_tokens", 0) or 0),
        }
    raise ExplainError(502, f"the model API is unavailable: {last}")


def _take_slot(now: float) -> bool:
    with _RECENT_LOCK:
        while _RECENT and now - _RECENT[0] > WINDOW_SECONDS:
            _RECENT.popleft()
        if len(_RECENT) >= MAX_CALLS_PER_WINDOW:
            return False
        _RECENT.append(now)
        return True


def explain_case(
    case_id: str,
    data: Mapping[str, Any],
    keys: Sequence[str],
    call: ModelCall | None = None,
    now: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """The same record shape the page stores per case: source, model, tokens, explanation."""

    entry = data["cases"].get(case_id)
    if entry is None:
        raise ExplainError(404, "unknown case, or the audit found nothing to explain")
    if not keys:
        raise ExplainError(503, "no model key is configured on this deployment")
    if not _take_slot(now()):
        raise ExplainError(429, "too many live model calls just now, try again in a few minutes")
    payload = entry["payload"]
    prompt = build_prompt(data["template"], payload)
    ask = call or call_groq  # looked up now, so a replacement of call_groq is honoured
    content, usage = ask(keys, data["model"], data["system_message"], prompt)
    reply = clean_reply(parse_reply(content))
    if reply is None:
        raise ExplainError(502, "the model reply did not match the expected shape and was dropped")
    problem = check_grounding(reply, payload, data["systems"])
    if problem is not None:
        raise ExplainError(502, f"model reply rejected: {problem}")
    return {
        "source": "llm",
        "note": "",
        "model": data["model"],
        "cache_hit": False,
        "input_tokens": usage.get("input"),
        "output_tokens": usage.get("output"),
        "explanation": reply,
    }


# ---------------------------------------------------------------------------------------------
# HTTP entry point (Vercel's Python runtime looks for a class named ``handler``)
# ---------------------------------------------------------------------------------------------


def route(query: Mapping[str, list[str]]) -> tuple[int, dict[str, Any], str]:
    """(status, body, cache-control) for a GET. Only the two documented parameters are accepted,
    so the number of distinct cacheable URLs, and so the worst-case spend, stays fixed."""

    try:
        data = load_data()
    except (OSError, ValueError):
        return 500, {"error": "the case data is missing from this deployment"}, "no-store"
    names = set(query)
    if names == {"ping"}:
        body = {"live": True, "model": data["model"], "configured": bool(keys_from_env())}
        return 200, body, "no-store"
    if names != {"case"} or len(query["case"]) != 1:
        return 400, {"error": "use ?case=<case id> or ?ping=1"}, "no-store"
    case_id = query["case"][0]
    if not _CASE_ID.match(case_id):
        return 400, {"error": "that is not a case id"}, "no-store"
    try:
        record = explain_case(case_id, data, keys_from_env())
    except ExplainError as exc:
        return exc.status, {"error": exc.message}, "no-store"
    except Exception:  # never let a stack trace or a key reach the visitor
        return 500, {"error": "the explanation failed"}, "no-store"
    return 200, {"case_id": case_id, "explain": record}, CACHE_OK


class handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        status, body, cache = route(parse_qs(urlsplit(self.path).query, keep_blank_values=True))
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)
