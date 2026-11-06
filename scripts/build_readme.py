# ruff: noqa: E501
"""Regenerate the data-driven parts of README.md from the repository's own result files.

Every number and chart the README shows comes from files this repository already writes
(`results/*.json`, `dataset/*.csv`, `tests/`). Nothing is typed in by hand, so the README cannot
drift away from the code.

    python scripts/build_readme.py           rewrite docs/img/*.svg and the AUTO blocks in README.md
    python scripts/build_readme.py --check   change nothing; exit 1 if the README is stale (CI)

Standard library only and deterministic (no timestamps), so a rerun on the same results writes the
same bytes. The animations are plain SVG (CSS keyframes and SMIL), which GitHub renders inside
README images without JavaScript.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "img"
README = ROOT / "README.md"

# ---------------------------------------------------------------- palette
BG0, BG1, CARD, LINE = "#0b1020", "#151b33", "#0f1630", "#2a3558"
INK, MUTE = "#e6edf7", "#93a1bd"
TEAL, VIOLET, AMBER, RED, GREEN, GRAY, ORANGE = (
    "#2dd4bf",
    "#a78bfa",
    "#fbbf24",
    "#fb7185",
    "#4ade80",
    "#94a3b8",
    "#fb923c",
)
SANS = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
BASE_CSS = (
    f"text{{font-family:{SANS}}}.m{{font-family:{MONO}}}"
    "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
)


# ---------------------------------------------------------------- facts
@dataclass(frozen=True)
class Facts:
    requests: int
    identities: int
    audit_log: int
    activities: int
    evidence_files: int
    rules: int
    statuses: dict[str, int]
    output_rows: int
    output_sha: str
    scores: dict[str, Any]
    reported_vs_audit: list[dict[str, Any]]
    failure_types: dict[str, int]
    patterns: list[dict[str, Any]]
    predictor: dict[str, Any]
    test_functions: int

    @property
    def claimed_complete(self) -> int:
        return sum(r["n"] for r in self.reported_vs_audit if r["reported"] == "COMPLETE")

    @property
    def claimed_but_leaking(self) -> int:
        return sum(
            r["n"]
            for r in self.reported_vs_audit
            if r["reported"] == "COMPLETE" and r["audit"] == "INCOMPLETE"
        )


def _rows(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load() -> Facts:
    run = _json(ROOT / "results" / "run_summary.json")
    scores = _json(ROOT / "results" / "sample_scores.json")
    insight = _json(ROOT / "results" / "insight_summary.json")
    data = ROOT / "dataset"
    tests = sum(
        len(re.findall(r"^\s*(?:async\s+)?def test_", p.read_text(encoding="utf-8"), re.M))
        for p in (ROOT / "tests").rglob("*.py")
    )
    return Facts(
        requests=_rows(data / "deletion_requests.csv"),
        identities=_rows(data / "user_identities.csv"),
        audit_log=_rows(data / "user_audit_log.csv"),
        activities=_rows(data / "system_activity.csv"),
        evidence_files=_rows(data / "evidence_files.csv"),
        rules=_rows(data / "deletion_rules.csv"),
        statuses=run["statuses"],
        output_rows=run["output_rows"],
        output_sha=run["output_sha256"],
        scores=scores,
        reported_vs_audit=insight["audit"]["reported_vs_audit"],
        failure_types=insight["audit"]["failure_types"],
        patterns=insight["patterns"],
        predictor=insight["predictor"],
        test_functions=tests,
    )


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def esc(s: str) -> str:
    return escape(s, quote=True)


# ---------------------------------------------------------------- svg helpers
def svg(w: int, h: int, body: str, css: str, title: str, desc: str, defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-labelledby="t d">\n<title id="t">{esc(title)}</title>'
        f'<desc id="d">{esc(desc)}</desc>\n<defs>{defs}</defs>\n<style>{BASE_CSS}{css}</style>\n'
        f"{body}\n</svg>\n"
    )


def bg(w: int, h: int) -> str:
    return (
        f'<rect width="{w}" height="{h}" rx="22" fill="url(#bgg)"/>'
        f'<rect x=".75" y=".75" width="{w - 1.5}" height="{h - 1.5}" rx="21.5" fill="none" stroke="{LINE}" stroke-width="1.5"/>'
    )


DEFS_COMMON = (
    f'<linearGradient id="bgg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG0}"/><stop offset="1" stop-color="{BG1}"/></linearGradient>'
    '<filter id="glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
)

GROW_CSS = (
    ".seg{transform-box:fill-box;transform-origin:left center;animation:grow 8s ease-out infinite backwards;animation-delay:var(--d)}"
    "@keyframes grow{0%{transform:scaleX(0);opacity:1}22%{transform:scaleX(1)}88%{transform:scaleX(1);opacity:1}100%{transform:scaleX(1);opacity:0}}"
    ".lbl{animation:lbl 8s ease-out infinite backwards;animation-delay:var(--d)}"
    "@keyframes lbl{0%,16%{opacity:0}30%{opacity:1}88%{opacity:1}100%{opacity:0}}"
    ".pulse{animation:pulse 2.2s ease-in-out infinite}"
    "@keyframes pulse{0%,100%{opacity:.15}50%{opacity:.95}}"
)


# ---------------------------------------------------------------- hero
def hero(f: Facts) -> str:
    w, h = 1200, 440
    leak, claimed = f.claimed_but_leaking, f.claimed_complete
    incomplete = f.statuses.get("INCOMPLETE", 0)
    lines = [
        "> workflow says COMPLETE ... checking the evidence",
        f"> {leak} of {claimed} 'Complete' deletions still held data ({pct(leak / claimed, 0)})",
        "> evidence in, verdict out. deterministic. no guessing.",
    ]
    cycle = 15.0
    typed = []
    cw = 10.2
    for i, text in enumerate(lines):
        width = round(len(text) * cw, 1)
        s = i * 5.0
        kt = ";".join(f"{v:.4f}" for v in (0, s / cycle, (s + 1.9) / cycle, (s + 4.3) / cycle, (s + 4.6) / cycle, 1))
        vals_w = f"0;0;{width};{width};0;0"
        vals_x = f"84;84;{84 + width};{84 + width};84;84"
        typed.append(
            f'<clipPath id="ty{i}"><rect x="84" y="276" height="30" width="0"><animate attributeName="width" dur="{cycle}s" repeatCount="indefinite" values="{vals_w}" keyTimes="{kt}"/></rect></clipPath>'
            f'<text class="m" x="84" y="298" font-size="17" fill="{TEAL}" textLength="{width}" lengthAdjust="spacing" clip-path="url(#ty{i})">{esc(text)}</text>'
            f'<rect x="84" y="281" width="9" height="20" fill="{TEAL}" class="caret"><animate attributeName="x" dur="{cycle}s" repeatCount="indefinite" values="{vals_x}" keyTimes="{kt}"/></rect>'
        )
    tokens = [("@mail", 770, 0.0), ("+91 98", 860, 1.4), ("#a9f3c", 960, 2.6), ("name", 1050, 0.8), ("addr", 800, 3.6), ("sha256", 1000, 4.6), ("dob", 920, 5.4)]
    tok = "".join(
        f'<text class="tok m" x="{x}" y="340" style="animation-delay:{d}s">{esc(t)}</text>'
        for t, x, d in tokens
    )
    chips_data = [
        (str(f.requests), "requests audited", TEAL),
        (str(f.evidence_files), "evidence files read", VIOLET),
        (str(incomplete), "deletions still leaking", RED),
        (str(f.scores.get("false_complete_count", 0)), "false COMPLETE", GREEN),
    ]
    chips = ""
    for i, (num, label, color) in enumerate(chips_data):
        x = 64 + i * 268
        dot = (
            f'<circle cx="{x + 236}" cy="364" r="5" fill="{color}" class="pulse"/>' if color == RED else ""
        )
        chips += (
            f'<g><rect x="{x}" y="350" width="250" height="62" rx="14" fill="{CARD}" stroke="{LINE}"/>'
            f'<text x="{x + 18}" y="388" font-size="30" font-weight="800" fill="{color}">{num}</text>'
            f'<text x="{x + 28 + 18 * len(num)}" y="388" font-size="12.5" fill="{MUTE}">{esc(label)}</text>{dot}</g>'
        )
    ghost = (
        '<g transform="translate(900 92) scale(1.75)"><g class="bob">'
        '<ellipse cx="50" cy="134" rx="36" ry="5" fill="#000" opacity=".3"/>'
        '<path d="M0 50C0 22 22 0 50 0s50 22 50 50v70l-17-15-16 15-17-15-17 15-16-15-17 15z" fill="url(#gg)" filter="url(#glow)"/>'
        f'<ellipse cx="34" cy="50" rx="7" ry="9" fill="{BG0}"><animate attributeName="ry" dur="4s" repeatCount="indefinite" values="9;9;1;9" keyTimes="0;0.92;0.96;1"/></ellipse>'
        f'<ellipse cx="66" cy="50" rx="7" ry="9" fill="{BG0}"><animate attributeName="ry" dur="4s" repeatCount="indefinite" values="9;9;1;9" keyTimes="0;0.92;0.96;1"/></ellipse>'
        f'<ellipse cx="50" cy="76" rx="6" ry="8" fill="{BG0}"><animate attributeName="ry" dur="3s" repeatCount="indefinite" values="8;5;8"/></ellipse>'
        "</g></g>"
    )
    lens = (
        '<g transform="translate(812 222)"><g>'
        '<animateTransform attributeName="transform" type="translate" values="0 0;46 -14;92 0;46 16;0 0" dur="7s" repeatCount="indefinite"/>'
        f'<circle r="30" fill="{TEAL}" fill-opacity=".12" stroke="{TEAL}" stroke-width="5"/>'
        f'<line x1="22" y1="22" x2="48" y2="48" stroke="{TEAL}" stroke-width="8" stroke-linecap="round"/>'
        f'<path d="M-16 -8a20 20 0 0 1 14 -12" fill="none" stroke="{INK}" stroke-opacity=".7" stroke-width="3" stroke-linecap="round"/>'
        "</g></g>"
    )
    body = (
        bg(w, h)
        + f'<rect x="0" y="-90" width="{w}" height="90" fill="url(#beam)" opacity=".55"><animate attributeName="y" values="-90;{h};-90" dur="9s" repeatCount="indefinite"/></rect>'
        + f'<text class="m" x="64" y="84" font-size="13" letter-spacing="3" fill="{TEAL}">HACKERRANK ORCHESTRATE · OCTOBER 2026</text>'
        + '<text x="62" y="170" font-size="88" font-weight="800" fill="url(#tg)">GhostTrace</text>'
        + f'<text x="64" y="212" font-size="26" font-weight="600" fill="{INK}">Deletion said Complete. Did the data actually leave?</text>'
        + f'<text x="64" y="244" font-size="16" fill="{MUTE}">A deterministic deletion-audit agent for “Ghost Data Still Exists”.</text>'
        + f'<rect x="64" y="266" width="660" height="50" rx="12" fill="#0a0f1f" stroke="{LINE}"/>'
        + "".join(typed)
        + tok
        + ghost
        + lens
        + chips
    )
    defs = (
        DEFS_COMMON
        + '<linearGradient id="gg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f8fafc"/><stop offset="1" stop-color="#a5b4fc"/></linearGradient>'
        + f'<linearGradient id="tg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{VIOLET}"/></linearGradient>'
        + f'<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{TEAL}" stop-opacity="0"/><stop offset="1" stop-color="{TEAL}" stop-opacity=".10"/></linearGradient>'
    )
    css = (
        ".bob{animation:bob 4.2s ease-in-out infinite}@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-14px)}}"
        f".tok{{font-size:14px;font-weight:700;fill:{RED};opacity:0;animation:rise 7s linear infinite}}"
        "@keyframes rise{0%{transform:translateY(0);opacity:0}15%{opacity:.9}80%{opacity:.45}100%{transform:translateY(-250px);opacity:0}}"
        ".caret{animation:blink 1s steps(2) infinite}@keyframes blink{50%{opacity:0}}"
        ".pulse{animation:pulse 2s ease-in-out infinite}@keyframes pulse{0%,100%{opacity:.25}50%{opacity:1}}"
    )
    return svg(w, h, body, css, "GhostTrace", "An animated ghost with a magnifying glass above the project name and live audit figures.", defs)


# ---------------------------------------------------------------- pipeline
def _icon(kind: str, x: float, y: float, color: str) -> str:
    g = f'<g transform="translate({x} {y}) scale(.75)" fill="none" stroke="{color}" stroke-width="2.4">'
    if kind == "inputs":
        g += "".join(
            f'<rect class="slide" style="animation-delay:{i * 0.35}s" x="0" y="{i * 8}" width="22" height="5" rx="2" fill="{color}" stroke="none"/>'
            for i in range(3)
        )
    elif kind == "ingest":
        g += f'<rect x="2" y="0" width="18" height="26" rx="3"/><rect x="2" y="0" width="18" height="3" fill="{color}" stroke="none"><animate attributeName="y" values="0;23;0" dur="2.4s" repeatCount="indefinite"/></rect>'
    elif kind == "reconstruct":
        g += '<circle cx="13" cy="13" r="12"/><line x1="13" y1="13" x2="13" y2="5" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 13 13" to="360 13 13" dur="6s" repeatCount="indefinite"/></line>'
    elif kind == "plan":
        g += '<path class="shield" d="M13 0l12 5v9c0 7-5 11-12 14C6 25 1 21 1 14V5z"/><path d="M7 14l4 4 8-8" stroke-linecap="round" stroke-linejoin="round"/>'
    else:
        g += '<rect x="0" y="0" width="26" height="26" rx="4"/><line x1="0" y1="9" x2="26" y2="9"/><line x1="9" y1="9" x2="9" y2="26"/>'
    return g + "</g>"


def _box(x: int, n: int, title: str, lines: list[str], metric: str, color: str, icon: str) -> str:
    y, bw, bh = 160, 180, 172  # the lane track (y=240) runs through the channel at y+72..y+88
    out = (
        f'<g><rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="16" fill="{CARD}" stroke="{color}" stroke-opacity=".7" stroke-width="1.5"/>'
        f'<rect x="{x + 14}" y="{y}" width="{bw - 28}" height="4" rx="2" fill="{color}"/>'
        f'<circle cx="{x + 24}" cy="{y + 30}" r="12" fill="{color}"/><text x="{x + 24}" y="{y + 35}" font-size="14" font-weight="800" text-anchor="middle" fill="{BG0}">{n}</text>'
        f'<text x="{x + 44}" y="{y + 36}" font-size="17" font-weight="700" fill="{INK}">{esc(title)}</text>'
        f'<rect x="{x + 10}" y="{y + 72}" width="{bw - 20}" height="16" rx="8" fill="#0a0f1f" stroke="{color}" stroke-opacity=".35"/>'
        f'<line class="belt" x1="{x + 20}" y1="{y + 80}" x2="{x + bw - 20}" y2="{y + 80}" stroke="{color}" stroke-opacity=".45" stroke-width="2"/>'
    )
    for i, line in enumerate(lines):
        out += f'<text x="{x + 16}" y="{y + 110 + i * 16}" font-size="12" fill="{MUTE}">{esc(line)}</text>'
    out += f'<text class="m" x="{x + 16}" y="{y + 164}" font-size="11" fill="{color}">{esc(metric)}</text>'
    out += _icon(icon, x + bw - 32, y + 142, color)
    return out + "</g>"


def _chip(cy: int, label: str, count: int, sub: str, color: str) -> str:
    x, y, w = 950, cy - 28, 174
    return (
        f'<g><rect x="{x}" y="{y}" width="{w}" height="56" rx="12" fill="{CARD}" stroke="{color}" stroke-opacity=".8"/>'
        f'<text x="{x + 14}" y="{y + 23}" font-size="13.5" font-weight="700" fill="{color}">{esc(label)}</text>'
        f'<text x="{x + w - 12}" y="{y + 24}" font-size="18" font-weight="800" text-anchor="end" fill="{INK}">{count}</text>'
        f'<text x="{x + 14}" y="{y + 43}" font-size="11" fill="{MUTE}">{esc(sub)}</text></g>'
    )


def _lane_packets(counts: dict[str, int], total: int) -> list[str]:
    """Interleave packets across lanes in proportion to the verdict counts (every lane >= 1)."""
    s = sum(counts.values()) or 1
    n = {k: max(1, round(total * v / s)) if v else 0 for k, v in counts.items()}
    slots: list[tuple[float, str]] = []
    for lane, c in n.items():
        slots += [((j + 0.5) / c, lane) for j in range(c)]
    return [lane for _, lane in sorted(slots)]


def pipeline(f: Facts) -> str:
    w, h, dur = 1300, 580, 10.0
    st = f.statuses
    lanes = {
        "C": ("COMPLETE", st.get("COMPLETE", 0), "every copy compliant", GREEN, 120),
        "I": ("INCOMPLETE", st.get("INCOMPLETE", 0), "findings · fixes · checks", RED, 240),
        "N": ("NOT_APPLICABLE", st.get("NOT_APPLICABLE", 0), "not a deletion request", GRAY, 360),
    }
    path = {
        "I": "M20 240H1215",
        "C": "M20 240H885C915 240 915 120 950 120H1124C1142 120 1142 240 1160 240H1215",
        "N": "M20 240H885C915 240 915 360 950 360H1124C1142 360 1142 240 1160 240H1215",
    }
    defs = DEFS_COMMON + "".join(f'<path id="lane-{k}" d="{d}"/>' for k, d in path.items())
    tracks = "".join(
        f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="2" stroke-dasharray="3 7"/>' for d in path.values()
    )
    boxes = (
        _box(30, 1, "Inputs", [f"{f.requests} deletion requests", f"{f.activities:,} activity claims", f"{f.evidence_files} evidence files"], "participant data only", TEAL, "inputs")
        + _box(250, 2, "Ingest", ["parse each file once", "JSON·log·PDF·SQL·OCR", "→ EvidenceBundle"], "facts, never verdicts", VIOLET, "ingest")
        + _box(470, 3, "Reconstruct", ["resolve who is who", "state at audit_at", "recreation graph"], "history beats claims", "#60a5fa", "reconstruct")
        + _box(690, 4, "Plan & judge", ["apply deletion_rules", "ordered remediation", "no model calls"], "rules decide", AMBER, "plan")
    )
    chips = "".join(_chip(cy, lab, cnt, sub, col) for lab, cnt, sub, col, cy in lanes.values())
    out_box = (
        f'<g><rect x="1160" y="160" width="120" height="172" rx="16" fill="{CARD}" stroke="{GREEN}" stroke-opacity=".7" stroke-width="1.5"/>'
        f'<text x="1174" y="198" font-size="16" font-weight="800" fill="{INK}">output.csv</text>'
        f'<text x="1174" y="236" font-size="12" fill="{MUTE}">{f.output_rows} rows</text>'
        f'<text x="1174" y="256" font-size="12" fill="{MUTE}">sorted by case</text>'
        f'<text x="1174" y="276" font-size="12" fill="{MUTE}">valid JSON</text>'
        f'<text class="m" x="1174" y="316" font-size="11" fill="{GREEN}">sha {f.output_sha[:8]}</text></g>'
    )
    order = _lane_packets({k: v[1] for k, v in lanes.items()}, 12)
    flen = {"I": 1180.0, "C": 1350.0, "N": 1350.0}
    packets = ""
    for k, lane in enumerate(order):
        begin = f"-{k * dur / len(order):.2f}s" if k else "0s"
        a = 870 / flen[lane]
        b = a + 0.055
        col = lanes[lane][3]
        packets += (
            f'<circle r="6.5" fill="#e2e8f0" filter="url(#glow)">'
            f'<animateMotion dur="{dur}s" begin="{begin}" repeatCount="indefinite"><mpath href="#lane-{lane}"/></animateMotion>'
            f'<animate attributeName="fill" dur="{dur}s" begin="{begin}" repeatCount="indefinite" values="#e2e8f0;#e2e8f0;{col};{col}" keyTimes="0;{a:.3f};{b:.3f};1"/></circle>'
        )
    guard = (
        f'<rect class="dash" x="30" y="424" width="1240" height="60" rx="12" fill="none" stroke="{AMBER}" stroke-width="1.5" stroke-dasharray="6 6"/>'
        f'<text x="52" y="449" font-size="14" font-weight="700" fill="{AMBER}">GUARDED MODEL ADAPTER · proposes, never decides</text>'
        f'<text x="52" y="470" font-size="12.5" fill="{MUTE}">Only for an unreadable screenshot or an ambiguous request: schema-checked, cached, budget-capped, no tools. A normal run makes 0 model calls.</text>'
        f'<path class="flow" d="M340 424V334" stroke="{AMBER}" stroke-width="2" fill="none"/><path class="flow" d="M560 424V334" stroke="{AMBER}" stroke-width="2" fill="none"/>'
    )
    measure = (
        f'<rect x="30" y="496" width="1240" height="56" rx="12" fill="none" stroke="{TEAL}" stroke-opacity=".8" stroke-width="1.5"/>'
        f'<text x="52" y="520" font-size="14" font-weight="700" fill="{TEAL}">VALIDATE &amp; MEASURE</text>'
        f'<text x="52" y="540" font-size="12.5" fill="{MUTE}">An independent validator re-reads output.csv ({f.output_rows} rows, sorted, allowed operation/state pairs). The scorer checks the {f.scores.get("cases", 0)} public answers: false COMPLETE = {f.scores.get("false_complete_count", 0)}.</text>'
    )
    body = (
        bg(w, h)
        + f'<text class="m" x="40" y="44" font-size="14" letter-spacing="2" fill="{TEAL}">ONE REQUEST, END TO END</text>'
        + f'<text x="40" y="68" font-size="13" fill="{MUTE}">Each moving dot is a deletion request. Its colour is the verdict it ends with; counts come from the latest full run.</text>'
        + tracks
        + boxes
        + packets
        + chips
        + out_box
        + guard
        + measure
    )
    css = (
        ".slide{animation:slide 1.8s ease-in-out infinite alternate}@keyframes slide{to{transform:translateX(6px)}}"
        ".shield{transform-box:fill-box;transform-origin:center;animation:beat 2.4s ease-in-out infinite}@keyframes beat{50%{transform:scale(1.12)}}"
        ".dash{animation:dash 1.4s linear infinite}@keyframes dash{to{stroke-dashoffset:-12}}"
        ".flow{stroke-dasharray:4 8;animation:flow 1s linear infinite}@keyframes flow{to{stroke-dashoffset:12}}"
        ".belt{stroke-dasharray:2 8;animation:belt 1s linear infinite}@keyframes belt{to{stroke-dashoffset:-10}}"
    )
    return svg(w, h, body, css, "GhostTrace pipeline", "Deletion requests flow through ingest, reconstruct and plan, then split into COMPLETE, INCOMPLETE and NOT_APPLICABLE verdicts that merge into output.csv.", defs)


# ---------------------------------------------------------------- reality gap
def reality(f: Facts) -> str:
    w, h = 1200, 430
    order = ["COMPLETE", "PARTIALLY_COMPLETE", "NOT_STARTED"]
    segs = [("COMPLETE", GREEN, "really complete"), ("INCOMPLETE", RED, "still holds data"), ("NOT_APPLICABLE", GRAY, "not a deletion request")]
    totals = {r: sum(x["n"] for x in f.reported_vs_audit if x["reported"] == r) for r in order}
    scale = 640 / max(totals.values())
    body = bg(w, h) + f'<text x="40" y="46" font-size="22" font-weight="800" fill="{INK}">What the workflow reported vs. what the audit found</text>'
    body += f'<text x="40" y="72" font-size="13" fill="{MUTE}">Each row is the status the deletion workflow claimed. Each colour is the state the evidence shows at audit_at.</text>'
    for i, rep in enumerate(order):
        y = 118 + i * 90
        body += f'<text x="40" y="{y + 20}" font-size="15" font-weight="700" fill="{INK}">reported {esc(rep)}</text>'
        body += f'<text x="40" y="{y + 40}" font-size="12.5" fill="{MUTE}">{totals[rep]} cases</text>'
        x = 300.0
        for j, (aud, color, _) in enumerate(segs):
            n = next((r["n"] for r in f.reported_vs_audit if r["reported"] == rep and r["audit"] == aud), 0)
            if not n:
                continue
            sw = n * scale
            d = f"{i * 0.3 + j * 0.15:.2f}s"
            body += f'<rect class="seg" style="--d:{d}" x="{x:.1f}" y="{y}" width="{sw:.1f}" height="46" fill="{color}" fill-opacity=".9"/>'
            if sw >= 34:
                body += f'<text class="lbl" style="--d:{d}" x="{x + sw / 2:.1f}" y="{y + 30}" font-size="16" font-weight="800" text-anchor="middle" fill="{BG0}">{n}</text>'
            if aud == "INCOMPLETE" and rep == "COMPLETE":
                body += f'<rect class="pulse" x="{x - 2:.1f}" y="{y - 2}" width="{sw + 4:.1f}" height="50" rx="4" fill="none" stroke="{RED}" stroke-width="2.5"/>'
            x += sw
        leak = sum(r["n"] for r in f.reported_vs_audit if r["reported"] == rep and r["audit"] == "INCOMPLETE")
        if totals[rep]:
            body += f'<text class="lbl" style="--d:{i * 0.3 + 0.6:.2f}s" x="{x + 16:.1f}" y="{y + 31}" font-size="20" font-weight="800" fill="{RED if leak else GRAY}">{pct(leak / totals[rep], 0)} held data</text>'
    lx = 40.0
    for _, color, label in segs:
        body += f'<rect x="{lx}" y="{h - 52}" width="14" height="14" rx="3" fill="{color}"/><text x="{lx + 22}" y="{h - 40}" font-size="12.5" fill="{MUTE}">{esc(label)}</text>'
        lx += 40 + len(label) * 7.2
    body += f'<text x="40" y="{h - 14}" font-size="11.5" fill="{MUTE}">{sum(totals.values())} requests · source: results/insight_summary.json · a workflow status is a claim, not proof</text>'
    return svg(w, h, body, GROW_CSS, "Reported status versus audited state", f"{f.claimed_but_leaking} of {f.claimed_complete} deletions the workflow reported as COMPLETE still held data.", DEFS_COMMON)


# ---------------------------------------------------------------- scorecard
def scorecard(f: Facts) -> str:
    w, h, r = 1200, 330, 52
    c = 2 * 3.14159265 * r
    s = f.scores
    items = [
        (s["status_accuracy"], "status accuracy", "deletion status right", TEAL),
        (s["field_accuracy"], "field accuracy", "step fields right", VIOLET),
        (s["step_f1"], "step F1", f"precision {pct(s['step_precision'])} · recall {pct(s['step_recall'])}", AMBER),
        (s["exact_case_accuracy"], "exact case match", "whole row identical", ORANGE),
    ]
    body = bg(w, h) + f'<text x="40" y="46" font-size="22" font-weight="800" fill="{INK}">Scored on the {s["cases"]} public answers HackerRank publishes</text>'
    body += f'<text x="40" y="72" font-size="13" fill="{MUTE}">Offline, no model call. The {f.requests} evaluation answers are not published, so no hidden-set accuracy is claimed.</text>'
    for i, (v, label, sub, color) in enumerate(items):
        cx, cy = 120 + i * 240, 170
        body += (
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1c2548" stroke-width="12"/>'
            f'<circle class="ring" style="--to:{c * (1 - v):.2f};--d:{i * 0.25:.2f}s" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="12" stroke-linecap="round" transform="rotate(-90 {cx} {cy})"/>'
            f'<text class="lbl" style="--d:{i * 0.25:.2f}s" x="{cx}" y="{cy + 8}" font-size="24" font-weight="800" text-anchor="middle" fill="{INK}">{pct(v)}</text>'
            f'<text x="{cx}" y="{cy + 86}" font-size="14" font-weight="700" text-anchor="middle" fill="{INK}">{esc(label)}</text>'
            f'<text x="{cx}" y="{cy + 106}" font-size="11.5" text-anchor="middle" fill="{MUTE}">{esc(sub)}</text>'
        )
    cx, cy = 1080, 170
    fc = s.get("false_complete_count", 0)
    col = GREEN if fc == 0 else RED
    body += (
        f'<g transform="translate({cx} {cy})"><path class="shield" d="M0 -54L46 -34V6C46 34 23 50 0 60C-23 50 -46 34 -46 6V-34Z" fill="{col}" fill-opacity=".14" stroke="{col}" stroke-width="4"/>'
        f'<text y="12" font-size="40" font-weight="800" text-anchor="middle" fill="{INK}">{fc}</text></g>'
        f'<text x="{cx}" y="{cy + 86}" font-size="14" font-weight="700" text-anchor="middle" fill="{INK}">false COMPLETE</text>'
        f'<text x="{cx}" y="{cy + 106}" font-size="11.5" text-anchor="middle" fill="{MUTE}">the worst error: “done” when it is not</text>'
    )
    css = (
        GROW_CSS
        + f".ring{{stroke-dasharray:{c:.2f};animation:fill 8s ease-out infinite backwards;animation-delay:var(--d)}}"
        + f"@keyframes fill{{0%{{stroke-dashoffset:{c:.2f};opacity:1}}24%{{stroke-dashoffset:var(--to)}}88%{{stroke-dashoffset:var(--to);opacity:1}}100%{{stroke-dashoffset:var(--to);opacity:0}}}}"
        + ".shield{transform-box:fill-box;transform-origin:center;animation:beat 2.6s ease-in-out infinite}@keyframes beat{50%{transform:scale(1.07)}}"
    )
    return svg(w, h, body, css, "Score card on the public samples", f"Status accuracy {pct(s['status_accuracy'])}, field accuracy {pct(s['field_accuracy'])}, step F1 {pct(s['step_f1'])}, false COMPLETE {fc}.", DEFS_COMMON)


# ---------------------------------------------------------------- failures
FAILURE_TEXT = {
    "REMAINING_RECORD": ("a record that should be gone still exists", RED),
    "EXPOSED_PII": ("kept on purpose, but identifiers are still readable", AMBER),
    "ACTIVE_DATA_FLOW": ("a sync or import job can copy the data back", VIOLET),
    "RESTORE_RISK": ("a backup can restore what was deleted", TEAL),
}


def failures(f: Facts) -> str:
    w, h = 1200, 372
    incomplete = f.statuses.get("INCOMPLETE", 0)
    rows = sorted(f.failure_types.items(), key=lambda kv: (-kv[1], kv[0]))
    scale = 640 / max(v for _, v in rows)
    body = bg(w, h) + f'<text x="40" y="46" font-size="22" font-weight="800" fill="{INK}">What the {incomplete} incomplete deletions left behind</text>'
    body += f'<text x="40" y="72" font-size="13" fill="{MUTE}">One case can leave several kinds of finding, so the bars add up to more than {incomplete}.</text>'
    for i, (name, n) in enumerate(rows):
        meaning, color = FAILURE_TEXT.get(name, (name.lower().replace("_", " "), GRAY))
        y = 106 + i * 58
        d = f"{i * 0.2:.2f}s"
        body += (
            f'<text class="m" x="40" y="{y + 13}" font-size="14" font-weight="700" fill="{color}">{esc(name)}</text>'
            f'<text x="40" y="{y + 32}" font-size="12" fill="{MUTE}">{esc(meaning)}</text>'
            f'<rect class="seg" style="--d:{d}" x="360" y="{y}" width="{n * scale:.1f}" height="32" rx="6" fill="{color}" fill-opacity=".9"/>'
            f'<text class="lbl" style="--d:{d}" x="{360 + n * scale + 12:.1f}" y="{y + 23}" font-size="17" font-weight="800" fill="{INK}">{n}</text>'
        )
    body += f'<text x="40" y="{h - 16}" font-size="11.5" fill="{MUTE}">source: results/insight_summary.json · findings are the four allowed REPORT_* operations</text>'
    return svg(w, h, body, GROW_CSS, "Findings left behind by incomplete deletions", "Bar chart of finding types across all incomplete deletions.", DEFS_COMMON)


# ---------------------------------------------------------------- markdown blocks
def badge(label: str, message: str, color: str) -> str:
    def enc(s: str) -> str:
        return quote(s.replace("-", "--").replace("_", "__").replace(" ", "_"), safe="_-")

    url = f"https://img.shields.io/badge/{enc(label)}-{enc(message)}-{color}?style=flat-square&labelColor=0b1020"
    return f"![{label}: {message}]({url})"


def block_badges(f: Facts) -> str:
    s = f.scores
    return " ".join(
        [
            badge("python", "3.11", "3776ab"),
            badge("runs in", "docker", "2496ed"),
            badge("cases audited", str(f.output_rows), "2dd4bf"),
            badge("status accuracy (public samples)", pct(s["status_accuracy"]), "a78bfa"),
            badge("false COMPLETE", str(s.get("false_complete_count", 0)), "4ade80"),
            badge("model calls in a normal run", "0", "fbbf24"),
        ]
    )


def block_status_pie(f: Facts) -> str:
    st = f.statuses
    init = "%%{init: {'theme':'base','themeVariables':{'pie1':'#fb7185','pie2':'#4ade80','pie3':'#94a3b8','pieTitleTextSize':'18px'}}}%%"
    rows = "\n".join(f'    "{k}" : {st[k]}' for k in ("INCOMPLETE", "COMPLETE", "NOT_APPLICABLE") if k in st)
    return f"```mermaid\n{init}\npie showData title Verdicts on all {f.output_rows} requests\n{rows}\n```"


def block_patterns(f: Facts) -> str:
    pats = [p for p in f.patterns if p["id"] != "NOISE"]
    top = pats[:8]
    ymax = max(10, -(-int(max(p["cases"] for p in top) * 1.15) // 10) * 10)
    chart = (
        "```mermaid\n%%{init: {'theme':'base','themeVariables':{'xyChart':{'plotColorPalette':'#fb7185'}}}}%%\nxychart-beta\n"
        '    title "Cases per failure pattern (DBSCAN clusters)"\n'
        f"    x-axis [{', '.join(p['id'] for p in top)}]\n"
        f'    y-axis "cases" 0 --> {ymax}\n'
        f"    bar [{', '.join(str(p['cases']) for p in top)}]\n```"
    )
    table = "| Pattern | Cases | What it looks like |\n|---|---:|---|\n" + "\n".join(
        f"| {p['id']} | {p['cases']} | {p['label'].replace('|', '/')} |" for p in top
    )
    return chart + "\n\n" + table


def block_numbers(f: Facts) -> str:
    s, st, pr = f.scores, f.statuses, f.predictor
    base = pr["baselines"]
    cv = pr["cross_validated"]
    rows = [
        ("Deletion requests audited", f"{f.output_rows} (failed: 0)"),
        ("Verdicts", f"{st.get('INCOMPLETE', 0)} INCOMPLETE · {st.get('COMPLETE', 0)} COMPLETE · {st.get('NOT_APPLICABLE', 0)} NOT_APPLICABLE"),
        ("Workflow said COMPLETE, evidence disagrees", f"{f.claimed_but_leaking} of {f.claimed_complete} ({pct(f.claimed_but_leaking / f.claimed_complete)})"),
        ("Input size", f"{f.identities} identities · {f.audit_log} identity changes · {f.activities:,} activity events · {f.evidence_files} evidence files · {f.rules} policy rules"),
        ("Status accuracy on the public samples", f"{pct(s['status_accuracy'])} ({s['cases']} cases)"),
        ("Step precision / recall / F1", f"{pct(s['step_precision'])} / {pct(s['step_recall'])} / {pct(s['step_f1'])}"),
        ("Field / sequence / exact-row accuracy", f"{pct(s['field_accuracy'])} / {pct(s['sequence_accuracy'])} / {pct(s['exact_case_accuracy'])}"),
        ("Failure-risk model (LightGBM, cross-validated)", f"accuracy {pct(cv['accuracy'])} · AUC {cv['auc']:.3f} — vs {pct(base['trust_reported_status']['accuracy'])} for trusting the reported status and {pct(base['majority_class']['accuracy'])} for always guessing INCOMPLETE"),
        ("Test functions (offline)", str(f.test_functions)),
    ]
    return "| Measure | Value |\n|---|---|\n" + "\n".join(f"| {a} | {b} |" for a, b in rows)


def block_run_id(f: Facts) -> str:
    return (
        f"<sub>Generated by <code>scripts/build_readme.py</code> from <code>results/</code> and <code>dataset/</code> "
        f"(output.csv sha256 <code>{f.output_sha[:12]}…</code>, {f.output_rows} rows). "
        "Edit the text outside the AUTO markers; everything between them is rewritten.</sub>"
    )


BLOCKS = {
    "BADGES": block_badges,
    "STATUS_PIE": block_status_pie,
    "PATTERNS": block_patterns,
    "NUMBERS": block_numbers,
    "RUN_ID": block_run_id,
}


def apply_blocks(text: str, f: Facts) -> str:
    for name, fn in BLOCKS.items():
        pat = re.compile(rf"(<!-- AUTO:{name}:START -->)(.*?)(<!-- AUTO:{name}:END -->)", re.S)
        if not pat.search(text):
            raise SystemExit(f"README.md is missing the AUTO:{name} markers")
        text = pat.sub(lambda m, fn=fn: f"{m.group(1)}\n{fn(f)}\n{m.group(3)}", text, count=1)
    return text


def main(argv: list[str]) -> int:
    check = "--check" in argv
    f = load()
    outputs: dict[Path, str] = {
        IMG / "hero.svg": hero(f),
        IMG / "pipeline.svg": pipeline(f),
        IMG / "reality-gap.svg": reality(f),
        IMG / "scorecard.svg": scorecard(f),
        IMG / "failures.svg": failures(f),
        README: apply_blocks(README.read_text(encoding="utf-8"), f),
    }
    stale = [p for p, t in outputs.items() if not p.exists() or p.read_bytes().decode("utf-8") != t]
    if check:
        if stale:
            print("README is stale; run `python scripts/build_readme.py`:")
            for p in stale:
                print(f"  {p.relative_to(ROOT).as_posix()}")
            return 1
        print("README is up to date.")
        return 0
    IMG.mkdir(parents=True, exist_ok=True)
    for p in stale:
        p.write_bytes(outputs[p].encode("utf-8"))
        print(f"wrote {p.relative_to(ROOT).as_posix()}")
    if not stale:
        print("nothing to change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
