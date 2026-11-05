#!/usr/bin/env python3
"""Build what Vercel serves: ``public/index.html`` and the case data for ``api/explain.py``.

Standard library only, so it runs on Vercel's build image with no install step.

  python3 build.py                  in place: public/index.html and api/_cases.json
  python3 build.py --bundle DIR     also write a self-contained folder for ``vercel deploy``

The page is the same single file the local console serves, built from the committed
``dashboard/dashboard_data.json`` and ``dashboard/insight_data.json``. ``api/_cases.json`` holds,
for every case the audit found incomplete, the exact JSON the explanation prompt is filled with.
It is rebuilt from the stored audit and the policy table; the request text, emails, names and
phone numbers are not in it. ``tests/insight/test_vercel_api.py`` proves it reproduces the
prompts the local pipeline sent to the model.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DASHBOARD = HERE.parent
ROOT = DASHBOARD.parent
PAGE = DASHBOARD / "ghost-data-console.html"


def policy_table(rules_csv: Path) -> dict[str, str]:
    """``category -> "DELETE (rule_03)"``, the text the pipeline puts in every finding."""

    with rules_csv.open(encoding="utf-8", newline="") as handle:
        return {
            row["data_category"]: f"{row['required_action'].upper()} ({row['rule_id']})"
            for row in csv.DictReader(handle)
        }


def _drivers(case: dict[str, Any], meaning: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "feature": name,
            "meaning": meaning[name],
            "direction": "raises" if value > 0 else "lowers",
            "strength": round(abs(value), 2),
        }
        for name, value in case["drivers"]
    ]


def case_payload(
    case: dict[str, Any],
    *,
    policy: dict[str, str],
    patterns: dict[str, dict[str, Any]],
    meaning: dict[str, str],
) -> dict[str, Any]:
    """The audited case as the model sees it (same fields as ``explain.case_payload``)."""

    pattern = patterns.get(case["pattern"]) if case.get("pattern") else None
    return {
        "case_id": case["id"],
        "reported_status": case["reported"],
        "audit_status": case["status"],
        "audit_date": case["audit"],
        "findings": [
            {
                "step_no": step_no,
                "operation": operation,
                "system_id": system,
                "resource_id": resource,
                "category": category,
                "policy": policy.get(category, "not established"),
                "evidence_id": evidence,
            }
            for step_no, operation, system, resource, category, evidence in case["findings"]
        ],
        "plan": [
            {
                "step_no": step_no,
                "phase": phase,
                "operation": operation,
                "system_id": system,
                "resource_id": resource,
            }
            for step_no, phase, operation, system, resource, _evidence in case["steps"]
            if phase != "FINDING"
        ],
        "risk_model": {"p_failure": round(case["p"], 3), "drivers": _drivers(case, meaning)}
        if case.get("p") is not None
        else {"p_failure": None, "drivers": []},
        "pattern": {
            "id": pattern["pattern_id"],
            "label": pattern["label"],
            "cases": pattern["size"],
            "novel_at_audit": bool(case.get("novel")),
        }
        if pattern
        else None,
        "recreation_paths": [list(path) for path in case["paths"]],
    }


def build_cases(dashboard: Path, rules_csv: Path) -> dict[str, Any]:
    insight = json.loads((dashboard / "insight_data.json").read_text(encoding="utf-8"))
    page_data = json.loads((dashboard / "dashboard_data.json").read_text(encoding="utf-8"))
    policy = policy_table(rules_csv)
    patterns = {item["pattern_id"]: item for item in insight["patterns"]["items"]}
    meaning = insight["model"]["feature_meaning"]
    prompt = insight["llm"]["prompt"]
    cases = {
        case["id"]: {
            "payload": case_payload(case, policy=policy, patterns=patterns, meaning=meaning)
        }
        for case in insight["cases"]
        if case["status"] == "INCOMPLETE"
    }
    return {
        "model": insight["llm"]["usage"]["model"],
        "prompt_version": "insight-explain-v1",
        "system_message": prompt["system_message"],
        "template": prompt["template"],
        "systems": sorted(node["id"] for node in page_data["graph"]["nodes"]),
        "cases": cases,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def build_in_place() -> None:
    subprocess.run([sys.executable, str(DASHBOARD / "build_page.py")], check=True)
    (HERE / "public").mkdir(exist_ok=True)
    shutil.copyfile(PAGE, HERE / "public" / "index.html")
    cases = build_cases(DASHBOARD, ROOT / "dataset" / "deletion_rules.csv")
    write_json(HERE / "api" / "_cases.json", cases)
    print(f"wrote public/index.html and api/_cases.json ({len(cases['cases'])} cases)")


def write_bundle(target: Path) -> None:
    """A folder holding only what is served, so nothing else in the repository is uploaded."""

    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} is not empty; pass a new folder")
    (target / "api").mkdir(parents=True, exist_ok=True)
    (target / "public").mkdir(exist_ok=True)
    shutil.copyfile(HERE / "public" / "index.html", target / "public" / "index.html")
    shutil.copyfile(HERE / "api" / "explain.py", target / "api" / "explain.py")
    shutil.copyfile(HERE / "api" / "_cases.json", target / "api" / "_cases.json")
    config = json.loads((HERE / "vercel.json").read_text(encoding="utf-8"))
    config.pop("buildCommand", None)  # already built
    (target / "vercel.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"bundle written to {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, help="also write a folder for `vercel deploy`")
    args = parser.parse_args()
    build_in_place()
    if args.bundle is not None:
        write_bundle(args.bundle)


if __name__ == "__main__":
    main()
