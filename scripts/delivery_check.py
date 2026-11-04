#!/usr/bin/env python3
"""Delivery-note gate and read-only merge preflight for the SLAM team.

Standard library only, so it runs on a bare CI runner and on any teammate's machine.

  ci         PR gate. Fails unless the PR carries the documentation the integrator needs:
             the author's delivery note is updated and well formed, files outside the author's
             ownership are declared, the contract hash in the note matches the tree, and
             contract / dependency changes are announced.
  preflight  Integrator view of "what would merging <branch> into <target> do?". Read-only: it
             never touches your working tree or refs.
  status     One row per workstream, built from the delivery notes and the branch positions.

Rules live in docs/integration/ownership.toml; the human-readable version is
docs/integration/README.md. Output is ASCII on purpose (Windows consoles).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache
from itertools import takewhile
from pathlib import Path

OWNERSHIP_PATH = "docs/integration/ownership.toml"
STATUSES = ("NOT_STARTED", "IN_PROGRESS", "READY_FOR_INTEGRATION", "INTEGRATED")
ACTIVE_STATUSES = ("IN_PROGRESS", "READY_FOR_INTEGRATION", "INTEGRATED")
FRONT_KEYS = (
    "owner",
    "workstream",
    "status",
    "contract_version",
    "contract_sha256",
    "built_on",
    "merge_after",
    "last_updated",
)
SECTIONS_MINIMUM = ("Requires from others", "Provides to others")
SECTIONS_ACTIVE = (
    "Delivers",
    "Cross-owner edits",
    "Requires from others",
    "Provides to others",
    "Contract and dependency requests",
    "Verification",
    "Known limits",
    "Integration notes",
)
CROSS_OWNER = "Cross-owner edits"
DEPENDENCY_SECTION = "Contract and dependency requests"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{7,40}")
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b|<fill", re.IGNORECASE)
HEADING = re.compile(r"^##\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(?:```|~~~)")
BACKTICKED = re.compile(r"`([^`\n]+)`")
MAX_LISTED = 10


class GitError(RuntimeError):
    """A git command failed in a way the caller did not expect."""


class ConfigError(RuntimeError):
    """ownership.toml is missing or malformed."""


@dataclass(frozen=True)
class Finding:
    level: str  # "error" or "warning"
    message: str
    path: str | None = None


def error(message: str, path: str | None = None) -> Finding:
    return Finding("error", message, path)


def warning(message: str, path: str | None = None) -> Finding:
    return Finding("warning", message, path)


@dataclass(frozen=True)
class Owner:
    key: str
    name: str
    branch: str
    workstream: str
    owns: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    owners: dict[str, Owner]
    integrator: str
    contract_approver: str
    notes_dir: str
    changelog: str
    order: tuple[str, ...]
    exempt: tuple[str, ...]
    always_checked: tuple[str, ...]
    contract_paths: tuple[str, ...]
    contract_hash_file: str
    contract_version_file: str
    dependency_paths: tuple[str, ...]
    hotspots: tuple[str, ...]

    def note_path(self, key: str) -> str:
        return f"{self.notes_dir}/{key}.md"


@dataclass(frozen=True)
class Note:
    front: dict[str, str]
    sections: dict[str, str]

    @property
    def status(self) -> str:
        return self.front.get("status", "")


# --------------------------------------------------------------------------- git helpers


def git(repo: Path, *args: str, ok: Sequence[int] = (0,)) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode not in ok:
        raise GitError(f"git {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()}")
    return proc


def resolve(repo: Path, ref: str) -> str | None:
    proc = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", ok=(0, 1, 128))
    return proc.stdout.strip() or None


def show(repo: Path, ref: str, path: str) -> str | None:
    proc = git(repo, "show", f"{ref}:{path}", ok=(0, 128))
    return proc.stdout if proc.returncode == 0 else None


def changed_files(repo: Path, base: str, head: str) -> list[str]:
    """Files the head adds relative to the merge-base with base (what a PR page shows)."""
    out = git(repo, "diff", "--name-only", "-z", "--no-renames", f"{base}...{head}").stdout
    return sorted(path for path in out.split("\0") if path)


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return git(repo, "merge-base", "--is-ancestor", ancestor, descendant, ok=(0, 1)).returncode == 0


def count_commits(repo: Path, rev_range: str) -> int:
    return int(git(repo, "rev-list", "--count", rev_range).stdout.strip() or 0)


def contract_hash(repo: Path, cfg: Config, ref: str) -> str | None:
    text = show(repo, ref, cfg.contract_hash_file)
    words = text.split() if text else []
    return words[0] if words else None


def contract_version(repo: Path, cfg: Config, ref: str) -> str | None:
    text = show(repo, ref, cfg.contract_version_file)
    return text.strip() if text else None


# --------------------------------------------------------------------------- patterns


@cache
def glob_regex(pattern: str) -> re.Pattern[str]:
    """'*' stays inside one path segment, '**' crosses segments."""
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(parts) + r"\Z")


def matches(path: str, patterns: Iterable[str]) -> bool:
    return any(glob_regex(pattern).match(path) for pattern in patterns)


# --------------------------------------------------------------------------- configuration


def parse_config(text: str) -> Config:
    try:
        data = tomllib.loads(text)
        owners = {
            key: Owner(
                key=key,
                name=str(body["name"]),
                branch=str(body["branch"]),
                workstream=str(body["workstream"]),
                owns=tuple(str(item) for item in body["owns"]),
            )
            for key, body in data["owners"].items()
        }
        checks, notes, roles = data["checks"], data["notes"], data["roles"]
        return Config(
            owners=owners,
            integrator=str(roles["integrator"]),
            contract_approver=str(roles["contract_approver"]),
            notes_dir=str(notes["dir"]),
            changelog=str(notes["changelog"]),
            order=tuple(notes["order"]),
            exempt=tuple(checks["exempt"]),
            always_checked=tuple(checks["always_checked"]),
            contract_paths=tuple(checks["contract_paths"]),
            contract_hash_file=str(checks["contract_hash_file"]),
            contract_version_file=str(checks["contract_version_file"]),
            dependency_paths=tuple(checks["dependency_paths"]),
            hotspots=tuple(checks["hotspots"]),
        )
    except (KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{OWNERSHIP_PATH} is invalid: {exc!r}") from exc


def load_config(repo: Path, ref: str | None) -> tuple[Config, str]:
    """Read ownership.toml at `ref`; fall back to the working tree when the ref lacks it."""
    text = show(repo, ref, OWNERSHIP_PATH) if ref else None
    source = f"{ref}:{OWNERSHIP_PATH}"
    if text is None:
        local = repo / OWNERSHIP_PATH
        if not local.is_file():
            raise ConfigError(f"{OWNERSHIP_PATH} was not found on {ref or 'disk'}")
        text = local.read_text(encoding="utf-8")
        source = f"working-tree copy of {OWNERSHIP_PATH}"
    return parse_config(text), source


def owner_for_branch(cfg: Config, branch: str | None) -> str | None:
    if not branch:
        return None
    name = branch.removeprefix("refs/heads/").removeprefix("origin/")
    for owner in cfg.owners.values():
        if name == owner.branch or name.startswith(owner.branch + "/"):
            return owner.key
    return None


def owner_of_path(cfg: Config, path: str) -> str | None:
    for key in cfg.order:
        owner = cfg.owners.get(key)
        if owner and matches(path, owner.owns):
            return key
    return None


# --------------------------------------------------------------------------- delivery notes


def parse_note(text: str) -> tuple[Note, list[str]]:
    problems: list[str] = []
    lines = text.lstrip("﻿").splitlines()
    front: dict[str, str] = {}
    body_start = 0
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            problems.append("the front matter block opens with --- but is never closed")
            body_start = len(lines)
        else:
            for raw in lines[1:end]:
                if not raw.strip():
                    continue
                key, sep, value = raw.partition(":")
                if not sep:
                    problems.append(f"front matter line {raw!r} is not 'key: value'")
                    continue
                key = key.strip()
                if key in front:
                    problems.append(f"front matter key {key!r} appears twice")
                front[key] = value.strip()
            body_start = end + 1
    else:
        problems.append("the note must start with a --- front matter block")

    body = re.sub(r"<!--.*?-->", "", "\n".join(lines[body_start:]), flags=re.DOTALL)
    sections: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False
    for line in body.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else HEADING.match(line)
        if heading:
            current = heading.group(1)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return Note(front, {name: "\n".join(body).strip() for name, body in sections.items()}), problems


def validate_note(
    cfg: Config, key: str, path: str, note: Note, problems: list[str]
) -> list[Finding]:
    """Shape rules only; whether the content is true is the reviewer's job."""
    out = [error(problem, path) for problem in problems]
    front = note.front
    missing = [name for name in FRONT_KEYS if not front.get(name)]
    if missing:
        out.append(error(f"front matter is missing: {', '.join(missing)}", path))
    if front.get("owner") and front["owner"] != key:
        out.append(
            error(f"front matter owner is {front['owner']!r} but the file is {key}.md", path)
        )
    if note.status and note.status not in STATUSES:
        out.append(error(f"status {note.status!r} must be one of {', '.join(STATUSES)}", path))
    sha = front.get("contract_sha256")
    if sha and not SHA256.fullmatch(sha):
        out.append(
            error("contract_sha256 must be the 64 hex characters of contracts/SCHEMA_SHA256", path)
        )
    built_on = front.get("built_on")
    if built_on and built_on != "none" and not COMMIT.fullmatch(built_on):
        out.append(error("built_on must be 'none' or a commit hash (7-40 hex characters)", path))
    merge_after = front.get("merge_after")
    if merge_after and merge_after != "none":
        for item in (part.strip() for part in merge_after.split(",")):
            if item not in cfg.owners or item == key:
                out.append(
                    error(f"merge_after names {item!r}, which is not another workstream", path)
                )
    updated = front.get("last_updated")
    if updated:
        try:
            date.fromisoformat(updated)
        except ValueError:
            out.append(error("last_updated must be an ISO date, e.g. 2026-11-04", path))

    required = SECTIONS_ACTIVE if note.status in ACTIVE_STATUSES else SECTIONS_MINIMUM
    for name in required:
        body = note.sections.get(name)
        if body is None:
            out.append(error(f"missing section '## {name}'", path))
        elif not body:
            out.append(
                error(f"section '## {name}' is empty (write 'None' if it truly has nothing)", path)
            )
        elif PLACEHOLDER.search(body):
            out.append(
                error(f"section '## {name}' still contains a TODO/TBD/<fill> placeholder", path)
            )
    return out


def read_note(repo: Path, cfg: Config, ref: str, key: str) -> tuple[Note | None, list[Finding]]:
    path = cfg.note_path(key)
    text = show(repo, ref, path)
    if text is None:
        return None, [error(f"{path} does not exist at {ref}", path)]
    note, problems = parse_note(text)
    return note, validate_note(cfg, key, path, note, problems)


def declared_cross_edits(notes: Iterable[Note]) -> list[str]:
    tokens: list[str] = []
    for note in notes:
        tokens.extend(BACKTICKED.findall(note.sections.get(CROSS_OWNER, "")))
    return tokens


# --------------------------------------------------------------------------- the PR gate


def _listed(paths: Sequence[str]) -> str:
    shown = ", ".join(paths[:MAX_LISTED])
    extra = len(paths) - MAX_LISTED
    return shown + (f" ... and {extra} more" if extra > 0 else "")


def check_change(
    repo: Path, cfg: Config, base: str, head: str, branch: str | None
) -> list[Finding]:
    """Documentation rules for the change `head` brings relative to `base`."""
    files = changed_files(repo, base, head)
    findings: list[Finding] = []
    notes_changed = [key for key in cfg.owners if cfg.note_path(key) in files]
    relevant = [
        path for path in files if not matches(path, cfg.exempt) or matches(path, cfg.always_checked)
    ]
    if not relevant and not notes_changed:
        return findings  # documentation-only change: nothing to declare

    author = owner_for_branch(cfg, branch)
    authors = [author] if author else sorted(notes_changed)
    if not authors:
        names = ", ".join(f"{o.branch}[/...]" for o in cfg.owners.values())
        return [
            error(
                f"cannot tell whose work this is: branch {branch!r} is not one of {names} and "
                "no delivery note changed. Update docs/integration/deliveries/<you>.md."
            )
        ]

    author_notes: dict[str, Note] = {}
    for key in authors:
        path = cfg.note_path(key)
        if path not in files:
            if relevant:
                findings.append(
                    error(
                        f"this change touches {len(relevant)} non-documentation file(s) "
                        f"({_listed(relevant)}) but {path} was not updated. Say what you deliver, "
                        "what you need from others, and what they need from you.",
                        path,
                    )
                )
            continue
        note, note_findings = read_note(repo, cfg, head, key)
        findings += note_findings
        if note is not None:
            author_notes[key] = note
            if relevant and note.status == "NOT_STARTED":
                findings.append(
                    error(
                        "status is NOT_STARTED but this change touches code; "
                        "set IN_PROGRESS (or READY_FOR_INTEGRATION).",
                        path,
                    )
                )

    for key in notes_changed:  # format-check notes edited by someone else, e.g. status flips
        if key in authors:
            continue
        path = cfg.note_path(key)
        if not any(matches(path, cfg.owners[a].owns) for a in authors):
            findings.append(warning(f"{path} belongs to {key}, not to this change's author", path))
        findings += read_note(repo, cfg, head, key)[1]

    allowed = [pattern for key in authors for pattern in cfg.owners[key].owns]
    declared = declared_cross_edits(author_notes.values())
    undeclared = [
        path
        for path in relevant
        if not matches(path, allowed) and not any(path == t or matches(path, [t]) for t in declared)
    ]
    if undeclared:
        owners = sorted({owner_of_path(cfg, p) or "nobody" for p in undeclared})
        findings.append(
            error(
                f"{len(undeclared)} file(s) outside your ownership are not declared "
                f"(belonging to: {', '.join(owners)}): {_listed(undeclared)}. List each in "
                f"'## {CROSS_OWNER}' of your note, in backticks, with the reason, and tell "
                "the owner."
            )
        )

    touched_contract = [path for path in files if matches(path, cfg.contract_paths)]
    if touched_contract and cfg.changelog not in files:
        findings.append(
            error(
                f"contract files changed ({_listed(touched_contract)}) but {cfg.changelog} was "
                f"not updated. {cfg.contract_approver} must approve and all four owners be told.",
                cfg.changelog,
            )
        )

    tree_hash = contract_hash(repo, cfg, head)
    tree_version = contract_version(repo, cfg, head)
    for key, note in author_notes.items():
        path = cfg.note_path(key)
        if note.status == "NOT_STARTED":
            continue
        declared_hash = note.front.get("contract_sha256")
        if tree_hash and declared_hash and declared_hash != tree_hash:
            if touched_contract:
                hint = "you changed the contract: run scripts/export_contracts.py and copy the hash"
            else:
                hint = (
                    "the contract moved since you wrote the note: read "
                    f"{cfg.changelog}, adapt your code, re-run the tests, then update the hash"
                )
            findings.append(
                error(
                    f"note says contract_sha256 {declared_hash[:12]} but the tree has "
                    f"{tree_hash[:12]}; {hint}.",
                    path,
                )
            )
        declared_version = note.front.get("contract_version")
        if tree_version and declared_version and declared_version != tree_version:
            findings.append(
                error(
                    f"note says contract_version {declared_version}, tree has {tree_version}.", path
                )
            )
        built_on = note.front.get("built_on", "")
        if built_on == "none":
            findings.append(error("built_on cannot be 'none' once work has started.", path))
        elif built_on:
            commit = resolve(repo, built_on)
            if commit is None:
                findings.append(error(f"built_on {built_on} is not a known commit.", path))
            elif not is_ancestor(repo, commit, head):
                findings.append(
                    error(f"built_on {built_on} is not an ancestor of this branch.", path)
                )

    touched_deps = [path for path in files if matches(path, cfg.dependency_paths)]
    if touched_deps:
        for key, note in author_notes.items():
            body = note.sections.get(DEPENDENCY_SECTION, "").strip().lower().rstrip(".")
            if body in {"none", "n/a", "-"}:
                findings.append(
                    error(
                        f"dependency/build files changed ({_listed(touched_deps)}) but "
                        f"'## {DEPENDENCY_SECTION}' says {body!r}. Name the package, version "
                        "and who needs it.",
                        cfg.note_path(key),
                    )
                )
    return findings


# --------------------------------------------------------------------------- preflight


def dry_run_merge(repo: Path, target: str, branch: str) -> tuple[str, list[str]]:
    proc = git(
        repo,
        "merge-tree",
        "--write-tree",
        "--name-only",
        "--no-messages",
        target,
        branch,
        ok=(0, 1, 128, 129),
    )
    if proc.returncode == 0:
        return "clean", []
    if proc.returncode == 1:
        lines = takewhile(bool, proc.stdout.splitlines()[1:])
        return "conflicts", sorted(set(lines))
    return "unavailable", [
        proc.stderr.strip() or "git merge-tree is not available (needs git 2.38)"
    ]


def preflight(
    repo: Path, cfg: Config, branch: str, target: str, *, allow_out_of_order: bool
) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    info: list[str] = []
    head = resolve(repo, branch)
    tip = resolve(repo, target)
    if head is None or tip is None:
        missing = branch if head is None else target
        return [
            error(f"{missing} does not resolve to a commit; run 'git fetch --all --prune'.")
        ], info

    name = branch.removeprefix("origin/")
    key = owner_for_branch(cfg, branch)
    ahead, behind = (
        count_commits(repo, f"{target}..{branch}"),
        count_commits(repo, f"{branch}..{target}"),
    )
    info.append(f"branch   {branch} @ {head[:8]}  ({ahead} ahead / {behind} behind {target})")
    info.append(f"target   {target} @ {tip[:8]}")
    info.append(f"owner    {key or 'unknown (not an owner branch)'}")

    findings += check_change(repo, cfg, target, branch, name)

    note: Note | None = None
    if key:
        note, _ = read_note(repo, cfg, branch, key)

    # 1. Does the target contain the baseline this branch was built on?
    built_on = note.front.get("built_on", "none") if note else "none"
    commit = resolve(repo, built_on) if built_on != "none" else None
    if commit and not is_ancestor(repo, commit, target):
        findings.append(
            error(
                f"{target} does not contain {built_on}, the baseline this branch is built on. "
                "Land the baseline on the target first (playbook step 0); until then the PR diff "
                "also contains files that belong to other workstreams."
            )
        )

    # 2. Contract position: same, branch changed it, or branch is behind.
    base = git(repo, "merge-base", target, branch, ok=(0, 1)).stdout.strip()
    branch_hash, target_hash = contract_hash(repo, cfg, branch), contract_hash(repo, cfg, target)
    base_hash = contract_hash(repo, cfg, base) if base else None
    if branch_hash and target_hash:
        if branch_hash == target_hash:
            info.append(f"contract {branch_hash[:12]} (branch and target agree)")
        elif base_hash and branch_hash != base_hash:
            findings.append(
                warning(
                    f"branch CHANGES the contract ({base_hash[:12]} -> {branch_hash[:12]}). "
                    f"{cfg.contract_approver} must approve, {cfg.changelog} must record it, and "
                    "all four owners must be told before merging."
                )
            )
        else:
            findings.append(
                error(
                    f"branch is on contract {branch_hash[:12]} but {target} has "
                    f"{target_hash[:12]}. Merge {target} into the branch, re-run its tests, "
                    "update the note, then retry."
                )
            )
    elif target_hash is None:
        info.append(f"contract {target} has no {cfg.contract_hash_file} yet (baseline missing)")

    # 3. Merge order.
    after = note.front.get("merge_after", "none") if note else "none"
    for dep in [] if after == "none" else [part.strip() for part in after.split(",")]:
        dep_text = show(repo, target, cfg.note_path(dep))
        dep_note = parse_note(dep_text)[0] if dep_text else None
        dep_status = dep_note.status if dep_note else "MISSING"
        if dep_status != "INTEGRATED":
            finding = f"merge_after {dep}: its note on {target} says {dep_status}, not INTEGRATED."
            findings.append(warning(finding) if allow_out_of_order else error(finding))

    # 4. Textual conflicts and known collision files.
    verdict, conflicted = dry_run_merge(repo, target, branch)
    info.append(f"merge    {verdict}" + (f": {_listed(conflicted)}" if conflicted else ""))
    if verdict == "conflicts":
        findings.append(error(f"merging would conflict in: {_listed(conflicted)}."))
    elif verdict == "unavailable":
        findings.append(warning(f"merge dry-run unavailable: {conflicted[0]}"))
    touched_hotspots = [p for p in changed_files(repo, target, branch) if matches(p, cfg.hotspots)]
    if touched_hotspots:
        findings.append(
            warning(
                f"branch touches known collision files: {_listed(touched_hotspots)}. "
                "Resolve in merge order; see the playbook's conflict table."
            )
        )

    # 5. What the author told us.
    if note:
        info.append(f"status   {note.status or '?'}  merge_after: {after}")
        for heading in ("Requires from others", "Integration notes"):
            body = note.sections.get(heading, "")
            if body:
                info.append(f"\n--- {heading} (from {cfg.note_path(key or '')}) ---\n{body}")
    return findings, info


# --------------------------------------------------------------------------- status board


def status_rows(repo: Path, cfg: Config, target: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for key in cfg.order:
        owner = cfg.owners[key]
        source = next(
            (ref for ref in (f"origin/{owner.branch}", owner.branch) if resolve(repo, ref)), None
        )
        note = None
        if source:
            text = show(repo, source, cfg.note_path(key))
            note = parse_note(text)[0] if text else None
        on_target = show(repo, target, cfg.note_path(key)) if resolve(repo, target) else None
        target_status = parse_note(on_target)[0].status if on_target else "-"
        position = "-"
        if source and resolve(repo, target):
            position = (
                f"+{count_commits(repo, f'{target}..{source}')}"
                f"/-{count_commits(repo, f'{source}..{target}')}"
            )
        front = note.front if note else {}
        rows.append(
            [
                owner.name,
                source or "no branch",
                front.get("status", "no note"),
                target_status,
                position,
                front.get("contract_sha256", "-")[:8],
                front.get("built_on", "-"),
                front.get("merge_after", "-"),
                front.get("last_updated", "-"),
            ]
        )
    return rows


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    widths = [max(len(str(r[i])) for r in [headers, *rows]) for i in range(len(headers))]
    line = "  ".join(f"{{:<{w}}}" for w in widths)
    return "\n".join(
        [line.format(*headers), line.format(*("-" * w for w in widths))]
        + [line.format(*r) for r in rows]
    )


# --------------------------------------------------------------------------- output / CLI


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def emit(findings: Sequence[Finding]) -> int:
    on_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for finding in findings:
        if on_actions:
            location = f" file={finding.path}" if finding.path else ""
            print(f"::{finding.level}{location}::{_escape(finding.message)}")
        else:
            where = f" [{finding.path}]" if finding.path else ""
            print(f"{finding.level.upper():7}{where} {finding.message}")
    errors = sum(f.level == "error" for f in findings)
    warnings = len(findings) - errors
    print(f"\n{errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def repo_root(explicit: str | None) -> Path:
    start = Path(explicit) if explicit else Path.cwd()
    return Path(git(start, "rev-parse", "--show-toplevel").stdout.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--repo", help="repository path (default: current directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    ci = sub.add_parser("ci", help="PR documentation gate")
    ci.add_argument("--base", required=True, help="target branch ref, e.g. origin/dev")
    ci.add_argument("--head", default="HEAD", help="PR head or merge commit (default HEAD)")
    ci.add_argument("--branch", default="", help="PR source branch name (decides the author)")

    pre = sub.add_parser("preflight", help="what would merging BRANCH into the target do?")
    pre.add_argument("branch", help="e.g. origin/manya")
    pre.add_argument("--target", default="origin/dev")
    pre.add_argument("--allow-out-of-order", action="store_true", help="downgrade merge_after")

    stat = sub.add_parser("status", help="one row per workstream")
    stat.add_argument("--target", default="origin/dev")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        repo = repo_root(args.repo)
        if args.command == "ci":
            cfg, _ = load_config(repo, args.head)
            return emit(check_change(repo, cfg, args.base, args.head, args.branch or None))
        if args.command == "preflight":
            cfg, source = load_config(repo, args.target)
            print(f"rules    {source}")
            findings, info = preflight(
                repo, cfg, args.branch, args.target, allow_out_of_order=args.allow_out_of_order
            )
            print("\n".join(info))
            print()
            return emit(findings)
        cfg, source = load_config(repo, args.target)
        integrator = cfg.owners.get(cfg.integrator)
        print(f"rules {source}; integrator {integrator.name if integrator else cfg.integrator}\n")
        headers = [
            "owner",
            "source",
            "note",
            "on target",
            "vs target",
            "contract",
            "built_on",
            "merge_after",
            "updated",
        ]
        print(render_table(headers, status_rows(repo, cfg, args.target)))
        return 0
    except (GitError, ConfigError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
