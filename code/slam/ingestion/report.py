"""Corpus inventory report: what was ingested, what failed, and which parser covered what.

Built only from an ``EvidenceBundle``. It contains counts, codes, source ids and
relative paths, never participant values (names, e-mails, phones) and never
environment details or credentials, so it is safe to commit and share.

    python -m slam.ingestion.report --dataset dataset --out CORPUS_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from slam.contracts import CONTRACT_VERSION, EvidenceBundle, ParseStatus

from .api import INGESTION_VERSION, ingest


def build_report(bundle: EvidenceBundle) -> dict[str, Any]:
    sources = bundle.sources
    by_kind: dict[str, Counter[str]] = {}
    by_parser: dict[str, Counter[str]] = {}
    for source in sources:
        by_kind.setdefault(source.kind.value, Counter())[source.parse_status.value] += 1
        parser = source.extraction.parser_name if source.extraction else "none"
        by_parser.setdefault(parser, Counter())[source.parse_status.value] += 1

    observations = bundle.observations
    per_parser: Counter[str] = Counter()
    model_extracted = uncertain = without_identifiers = 0
    for obs in observations:
        if obs.extraction:
            per_parser[obs.extraction.parser_name] += 1
            if obs.extraction.model:
                model_extracted += 1
        if obs.fields.get("uncertain"):
            uncertain += 1
        if not obs.identifiers:
            without_identifiers += 1
    times = sorted(o.effective_time for o in observations)
    captured = sorted(s.captured_at for s in sources)

    issue_counts: Counter[tuple[str, str]] = Counter(
        (i.severity.value, i.code) for i in bundle.issues
    )
    first_message: dict[str, str] = {}
    for issue in bundle.issues:
        first_message.setdefault(issue.code, issue.message)

    problems = []
    codes_by_source: dict[str, list[str]] = {}
    for issue in bundle.issues:
        if issue.source_id and issue.severity.value in ("warning", "error"):
            codes_by_source.setdefault(issue.source_id, []).append(issue.code)
    for source in sources:
        if source.parse_status is not ParseStatus.PARSED:
            problems.append(
                {
                    "source_id": source.source_id,
                    "kind": source.kind.value,
                    "path": source.path,
                    "parse_status": source.parse_status.value,
                    "issue_codes": sorted(set(codes_by_source.get(source.source_id, []))),
                }
            )

    return {
        "contract_version": CONTRACT_VERSION,
        "ingestion_version": INGESTION_VERSION,
        "sources": {
            "total": len(sources),
            "by_kind": {k: dict(sorted(v.items())) for k, v in sorted(by_kind.items())},
            "by_origin": dict(sorted(Counter(s.origin for s in sources).items())),
            "captured_range": [
                captured[0].isoformat() if captured else None,
                captured[-1].isoformat() if captured else None,
            ],
        },
        "parser_coverage": {k: dict(sorted(v.items())) for k, v in sorted(by_parser.items())},
        "observations": {
            "total": len(observations),
            "by_category": dict(sorted(Counter(o.category for o in observations).items())),
            "by_system": dict(sorted(Counter(o.system_id for o in observations).items())),
            "by_state": dict(sorted(Counter(o.observed_state for o in observations).items())),
            "by_source_kind": dict(
                sorted(Counter(o.source_kind.value for o in observations).items())
            ),
            "by_parser": dict(sorted(per_parser.items())),
            "without_identifiers": without_identifiers,
            "model_extracted": model_extracted,
            "uncertain": uncertain,
            "effective_time_range": [
                times[0].isoformat() if times else None,
                times[-1].isoformat() if times else None,
            ],
        },
        "tables": {
            "current_identities": len(bundle.current_identities),
            "identity_changes": len(bundle.identity_changes),
            "activities": len(bundle.activities),
            "policy_rules": len(bundle.policy_rules),
        },
        "issues": {
            "total": len(bundle.issues),
            "by_code": [
                {"severity": sev, "code": code, "count": n, "example": first_message[code]}
                for (sev, code), n in sorted(issue_counts.items())
            ],
        },
        "unresolved_sources": problems,
    }


def _table(rows: Sequence[Sequence[object]], header: Sequence[str]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out.extend("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return out


def render_markdown(report: dict[str, Any]) -> str:
    src, obs, issues = report["sources"], report["observations"], report["issues"]
    lines = [
        "# Corpus inventory report",
        "",
        f"Contract {report['contract_version']}, ingestion {report['ingestion_version']}. "
        "Generated from an `EvidenceBundle`; counts and codes only, no participant values.",
        "",
        "## Sources",
        "",
        f"{src['total']} manifest entries ingested.",
        "",
    ]
    statuses = ("parsed", "partial", "failed")
    rows = [
        [kind, *(counts.get(s, 0) for s in statuses), sum(counts.values())]
        for kind, counts in src["by_kind"].items()
    ]
    lines += _table(rows, ["format", *statuses, "total"])
    lines += ["", "## Parser coverage", ""]
    rows = [
        [name, *(counts.get(s, 0) for s in statuses), obs["by_parser"].get(name, 0)]
        for name, counts in report["parser_coverage"].items()
    ]
    lines += _table(rows, ["parser", *statuses, "observations"])
    lines += ["", "## Observations", "", f"{obs['total']} observations."]
    lines.append(
        f"{obs['without_identifiers']} carry no identifier, {obs['model_extracted']} came from a "
        f"model, {obs['uncertain']} are flagged uncertain."
    )
    for title, key in (
        ("By category", "by_category"),
        ("By system", "by_system"),
        ("By state", "by_state"),
    ):
        lines += ["", f"### {title}", ""]
        lines += _table(list(obs[key].items()), [title.split()[-1], "count"])
    lines += ["", "## Tabular inputs", ""]
    lines += _table(list(report["tables"].items()), ["table", "rows"])
    lines += ["", "## Issues", "", f"{issues['total']} issues."]
    rows = [[i["severity"], i["code"], i["count"], i["example"]] for i in issues["by_code"]]
    lines += ["", *_table(rows, ["severity", "code", "count", "example message"])]
    lines += ["", "## Sources not fully parsed", ""]
    if report["unresolved_sources"]:
        rows = [
            [s["source_id"], s["kind"], s["parse_status"], s["path"], ", ".join(s["issue_codes"])]
            for s in report["unresolved_sources"]
        ]
        lines += _table(rows, ["source", "format", "status", "path", "issue codes"])
        lines += [
            "",
            "A source that is not fully parsed is a gap in coverage. It is never evidence "
            "that the records it may contain are absent.",
        ]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the corpus inventory report.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="Markdown output path")
    parser.add_argument("--json-out", type=Path, default=None, help="JSON output path")
    args = parser.parse_args(argv)

    report = build_report(ingest(args.dataset, cache_dir=args.cache_dir))
    markdown = render_markdown(report)
    if args.out:
        args.out.write_text(markdown, encoding="utf-8")
    else:
        sys.stdout.write(markdown)
    if args.json_out:
        args.json_out.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
