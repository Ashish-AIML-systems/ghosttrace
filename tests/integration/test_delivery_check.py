"""Tests for scripts/delivery_check.py, run against throwaway git repositories.

The real docs/integration/ownership.toml is used on purpose: if the rules file and the checker
drift apart, these tests fail. The last group validates the notes committed in this repository.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "delivery_check.py"
_spec = importlib.util.spec_from_file_location("delivery_check", SCRIPT)
assert _spec is not None and _spec.loader is not None
dc = importlib.util.module_from_spec(_spec)
sys.modules["delivery_check"] = dc
_spec.loader.exec_module(dc)

OWNERSHIP_TEXT = (ROOT / "docs" / "integration" / "ownership.toml").read_text(encoding="utf-8")
HASH_A = "a" * 64
HASH_B = "b" * 64

ACTIVE_BODY = {
    "Delivers": "A thing.",
    "Cross-owner edits": "None",
    "Requires from others": "Nothing.",
    "Provides to others": "Something.",
    "Contract and dependency requests": "None",
    "Verification": "pytest passed.",
    "Known limits": "Some.",
    "Integration notes": "Merge first.",
}


def run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return proc.stdout.strip()


def write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def note_text(
    owner: str = "ashish",
    *,
    status: str = "IN_PROGRESS",
    sha: str = HASH_A,
    built_on: str = "none",
    merge_after: str = "none",
    body: dict[str, str] | None = None,
) -> str:
    sections = {**ACTIVE_BODY, **(body or {})}
    front = (
        f"---\nowner: {owner}\nworkstream: Test\nstatus: {status}\ncontract_version: 1.0.0\n"
        f"contract_sha256: {sha}\nbuilt_on: {built_on}\nmerge_after: {merge_after}\n"
        "last_updated: 2026-11-04\n---\n"
    )
    return front + "".join(f"\n## {name}\n\n{text}\n" for name, text in sections.items())


@dataclass
class Repo:
    path: Path
    baseline: str

    def branch(self, name: str, files: dict[str, str], *, start: str = "dev") -> None:
        run_git(self.path, "switch", "-q", "-c", name, start)
        self.commit(files, name)

    def commit(self, files: dict[str, str], message: str) -> None:
        for rel, text in files.items():
            write(self.path, rel, text)
        run_git(self.path, "add", "-A")
        run_git(self.path, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    # The Docker image is debian-slim with no git, so every test that needs a real repository
    # skips there. They still run in the host/CI gates (git is present on the runner); the
    # "-rs" in the CI pytest command prints this reason, so the skip is visible, not silent.
    if shutil.which("git") is None:
        pytest.skip("git is not installed here (the Docker image has none); covered by the CI gate")
    root = tmp_path / "repo"
    root.mkdir()
    run_git(root, "init", "-q", "-b", "dev")
    write(root, "docs/integration/ownership.toml", OWNERSHIP_TEXT)
    write(root, "contracts/SCHEMA_SHA256", f"{HASH_A}  slam-contract-v1.schema.json\n")
    write(root, "contracts/CONTRACT_VERSION", "1.0.0\n")
    write(root, "code/slam/contracts.py", "# contract\n")
    write(root, "pyproject.toml", "[project]\n")
    write(root, "tests/contracts/test_owned_boundaries.py", "x = 1\n")
    run_git(root, "add", "-A")
    run_git(root, "commit", "-q", "-m", "baseline")
    return Repo(root, run_git(root, "rev-parse", "--short", "HEAD"))


@pytest.fixture
def cfg(repo: Repo) -> object:
    return dc.load_config(repo.path, "dev")[0]


@pytest.fixture
def file_cfg() -> object:
    """The real rules parsed straight from disk: for tests that need no git repository."""
    return dc.parse_config(OWNERSHIP_TEXT)


def check(repo: Repo, cfg: object, branch: str) -> list[object]:
    return dc.check_change(repo.path, cfg, "dev", branch, branch)


def messages(findings: list[object], level: str = "error") -> str:
    return "\n".join(f.message for f in findings if f.level == level)  # type: ignore[attr-defined]


# ------------------------------------------------------------------ patterns


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("code/slam/ingestion/**", "code/slam/ingestion/parsers/pdf_parser.py", True),
        ("code/slam/ingestion/**", "code/slam/reconstruction/api.py", False),
        ("*.md", "README.md", True),
        ("*.md", "code/slam/ingestion/INGESTION_PLAN.md", False),
        ("tests/**/conftest.py", "tests/ingestion/conftest.py", True),
        ("tests/**/conftest.py", "tests/conftest.py", True),
        ("docs/integration/deliveries/ashish.md", "docs/integration/deliveries/manya.md", False),
        ("contracts/**", "contracts/SCHEMA_SHA256", True),
    ],
)
def test_glob_semantics(pattern: str, path: str, expected: bool) -> None:
    assert dc.matches(path, [pattern]) is expected


# ------------------------------------------------------------------ note parsing and shape


def test_parse_note_reads_front_matter_sections_and_ignores_comments_and_fences() -> None:
    text = note_text() + "\n<!-- ## Hidden\n hidden -->\n```\n## Not a heading\n```\n"
    note, problems = dc.parse_note(text)
    assert problems == []
    assert note.front["owner"] == "ashish"
    assert "Hidden" not in note.sections and "Not a heading" not in note.sections
    assert note.sections["Delivers"] == "A thing."


def test_note_without_front_matter_is_rejected() -> None:
    _, problems = dc.parse_note("# no front matter\n")
    assert any("front matter" in problem for problem in problems)


def test_valid_active_note_has_no_findings(file_cfg: object) -> None:
    note, problems = dc.parse_note(note_text())
    assert dc.validate_note(file_cfg, "ashish", "p", note, problems) == []


@pytest.mark.parametrize(
    ("kwargs", "needle"),
    [
        ({"status": "DONE"}, "status 'DONE'"),
        ({"sha": "xyz"}, "contract_sha256"),
        ({"built_on": "not-a-hash"}, "built_on"),
        ({"merge_after": "ashish"}, "merge_after"),
        ({"merge_after": "nobody"}, "merge_after"),
        ({"body": {"Verification": "TODO run tests"}}, "placeholder"),
        ({"body": {"Known limits": ""}}, "is empty"),
    ],
)
def test_note_shape_violations(file_cfg: object, kwargs: dict[str, object], needle: str) -> None:
    note, problems = dc.parse_note(note_text(**kwargs))  # type: ignore[arg-type]
    out = dc.validate_note(file_cfg, "ashish", "p", note, problems)
    assert needle in messages(out)


def test_owner_must_match_file_name(file_cfg: object) -> None:
    note, problems = dc.parse_note(note_text(owner="manya"))
    assert "owner is 'manya'" in messages(dc.validate_note(file_cfg, "ashish", "p", note, problems))


def test_not_started_note_only_needs_requires_and_provides(file_cfg: object) -> None:
    text = (
        note_text(status="NOT_STARTED")
        .split("\n## Delivers")[0]
        .replace("IN_PROGRESS", "NOT_STARTED")
        + "\n## Requires from others\n\nx\n\n## Provides to others\n\ny\n"
    )
    note, problems = dc.parse_note(text)
    assert dc.validate_note(file_cfg, "ashish", "p", note, problems) == []


# ------------------------------------------------------------------ the PR gate


def test_documentation_only_change_needs_no_note(repo: Repo, cfg: object) -> None:
    repo.branch("ashish", {"docs/integration/extra.md": "hello\n", "NOTES.md": "x\n"})
    assert check(repo, cfg, "ashish") == []


def test_code_change_without_note_is_rejected_and_names_the_file(repo: Repo, cfg: object) -> None:
    repo.branch("ashish", {"code/slam/ingestion/x.py": "x = 1\n"})
    out = messages(check(repo, cfg, "ashish"))
    assert "docs/integration/deliveries/ashish.md was not updated" in out


def test_code_change_with_valid_note_passes(repo: Repo, cfg: object) -> None:
    repo.branch(
        "ashish",
        {
            "code/slam/ingestion/x.py": "x = 1\n",
            "docs/integration/deliveries/ashish.md": note_text(built_on=repo.baseline),
        },
    )
    assert messages(check(repo, cfg, "ashish")) == ""


def test_editing_another_owners_file_must_be_declared(repo: Repo, cfg: object) -> None:
    files = {
        "code/slam/ingestion/x.py": "x = 1\n",
        "tests/contracts/test_owned_boundaries.py": "x = 2\n",
    }
    repo.branch(
        "ashish",
        {**files, "docs/integration/deliveries/ashish.md": note_text(built_on=repo.baseline)},
    )
    out = messages(check(repo, cfg, "ashish"))
    assert "tests/contracts/test_owned_boundaries.py" in out and "lalith" in out

    declared = note_text(
        built_on=repo.baseline,
        body={
            "Cross-owner edits": "`tests/contracts/test_owned_boundaries.py` - stub test replaced."
        },
    )
    repo.commit({"docs/integration/deliveries/ashish.md": declared}, "declare")
    assert messages(check(repo, cfg, "ashish")) == ""


def test_not_started_status_is_rejected_when_code_changes(repo: Repo, cfg: object) -> None:
    repo.branch(
        "ashish",
        {
            "code/slam/ingestion/x.py": "x = 1\n",
            "docs/integration/deliveries/ashish.md": note_text(status="NOT_STARTED"),
        },
    )
    assert "NOT_STARTED but this change touches code" in messages(check(repo, cfg, "ashish"))


def test_branch_that_is_not_an_owner_branch_needs_a_note_to_be_attributed(
    repo: Repo, cfg: object
) -> None:
    repo.branch("codex/stray", {"code/slam/ingestion/x.py": "x = 1\n"})
    assert "cannot tell whose work" in messages(check(repo, cfg, "codex/stray"))


def test_owner_sub_branches_are_attributed(repo: Repo, cfg: object) -> None:
    repo.branch("manya/graph", {"code/slam/reconstruction/g.py": "x = 1\n"})
    out = messages(check(repo, cfg, "manya/graph"))
    assert "deliveries/manya.md was not updated" in out


def test_contract_change_requires_changelog_and_matching_hash(repo: Repo, cfg: object) -> None:
    files = {
        "code/slam/contracts.py": "# changed\n",
        "contracts/SCHEMA_SHA256": f"{HASH_B}  slam-contract-v1.schema.json\n",
        "docs/integration/deliveries/lalith.md": note_text("lalith", built_on=repo.baseline),
        "tests/contracts/t.py": "x = 1\n",
    }
    repo.branch("lalith", files)
    out = messages(check(repo, cfg, "lalith"))
    assert "CONTRACT_CHANGELOG.md was not updated" in out
    assert "you changed the contract" in out  # note still carries the old hash

    repo.commit(
        {
            "docs/integration/CONTRACT_CHANGELOG.md": "entry\n",
            "docs/integration/deliveries/lalith.md": note_text(
                "lalith", sha=HASH_B, built_on=repo.baseline
            ),
        },
        "announce",
    )
    assert messages(check(repo, cfg, "lalith")) == ""


def test_stale_contract_hash_after_target_moved_is_called_out(repo: Repo, cfg: object) -> None:
    repo.branch(
        "ashish",
        {
            "code/slam/ingestion/x.py": "x = 1\n",
            "docs/integration/deliveries/ashish.md": note_text(built_on=repo.baseline),
        },
    )
    run_git(repo.path, "switch", "-q", "dev")
    repo.commit({"contracts/SCHEMA_SHA256": f"{HASH_B}  s.json\n"}, "contract moved on dev")
    # CI checks the merge result, so simulate it: merge dev's new contract into the branch.
    run_git(repo.path, "switch", "-q", "ashish")
    run_git(repo.path, "merge", "-q", "--no-edit", "dev")
    assert "the contract moved since you wrote the note" in messages(check(repo, cfg, "ashish"))


def test_dependency_change_cannot_say_none(repo: Repo, cfg: object) -> None:
    repo.branch(
        "lalith",
        {
            "pyproject.toml": "[project]\ndependencies=['x']\n",
            "docs/integration/deliveries/lalith.md": note_text("lalith", built_on=repo.baseline),
        },
    )
    assert "dependency/build files changed" in messages(check(repo, cfg, "lalith"))


def test_built_on_must_be_an_ancestor(repo: Repo, cfg: object) -> None:
    repo.branch(
        "ashish",
        {
            "code/slam/ingestion/x.py": "x = 1\n",
            "docs/integration/deliveries/ashish.md": note_text(built_on="deadbeef"),
        },
    )
    assert "not a known commit" in messages(check(repo, cfg, "ashish"))


def test_changing_the_rules_file_counts_as_a_code_change(repo: Repo, cfg: object) -> None:
    repo.branch("ashish", {"docs/integration/ownership.toml": OWNERSHIP_TEXT + "\n# tweak\n"})
    out = messages(check(repo, cfg, "ashish"))
    assert "deliveries/ashish.md was not updated" in out
    assert "belonging to: integration" in out


# ------------------------------------------------------------------ preflight


def test_dry_run_reports_clean_and_conflicting_merges(repo: Repo) -> None:
    repo.branch("a", {"shared.txt": "from a\n"})
    repo.branch("b", {"shared.txt": "from b\n"})
    assert dc.dry_run_merge(repo.path, "a", "b") == ("conflicts", ["shared.txt"])
    repo.branch("c", {"other.txt": "ok\n"})
    assert dc.dry_run_merge(repo.path, "a", "c") == ("clean", [])


def _ready_branch(repo: Repo, owner: str, files: dict[str, str], merge_after: str) -> None:
    repo.branch(
        owner,
        {
            **files,
            f"docs/integration/deliveries/{owner}.md": note_text(
                owner, built_on=repo.baseline, merge_after=merge_after
            ),
        },
    )


def test_preflight_blocks_out_of_order_merges_unless_allowed(repo: Repo, cfg: object) -> None:
    _ready_branch(repo, "manya", {"code/slam/reconstruction/g.py": "x = 1\n"}, "ashish")
    findings, _ = dc.preflight(repo.path, cfg, "manya", "dev", allow_out_of_order=False)
    assert "merge_after ashish" in messages(findings)
    relaxed, _ = dc.preflight(repo.path, cfg, "manya", "dev", allow_out_of_order=True)
    assert messages(relaxed) == "" and "merge_after ashish" in messages(relaxed, "warning")


def test_preflight_passes_when_predecessor_is_integrated_on_target(repo: Repo, cfg: object) -> None:
    run_git(repo.path, "switch", "-q", "dev")
    repo.commit(
        {"docs/integration/deliveries/ashish.md": note_text(status="INTEGRATED")}, "integrated"
    )
    base = run_git(repo.path, "rev-parse", "--short", "HEAD")
    repo.branch(
        "manya",
        {
            "code/slam/reconstruction/g.py": "x = 1\n",
            "docs/integration/deliveries/manya.md": note_text(
                "manya", built_on=base, merge_after="ashish"
            ),
        },
    )
    findings, info = dc.preflight(repo.path, cfg, "manya", "dev", allow_out_of_order=False)
    assert messages(findings) == ""
    assert any("merge    clean" in line for line in info)


def test_preflight_flags_a_target_that_lacks_the_baseline(repo: Repo, cfg: object) -> None:
    run_git(repo.path, "switch", "-q", "-c", "baseline")
    repo.commit({"code/slam/runtime/p.py": "x = 1\n"}, "foundation")
    foundation = run_git(repo.path, "rev-parse", "--short", "HEAD")
    repo.commit(
        {
            "code/slam/ingestion/x.py": "x = 1\n",
            "docs/integration/deliveries/ashish.md": note_text(built_on=foundation),
        },
        "ingestion",
    )
    run_git(repo.path, "branch", "-m", "ashish")
    findings, _ = dc.preflight(repo.path, cfg, "ashish", "dev", allow_out_of_order=False)
    assert "does not contain" in messages(findings)


def test_preflight_reports_conflicts_and_hotspots(repo: Repo, cfg: object) -> None:
    _ready_branch(repo, "ashish", {"tests/contracts/test_owned_boundaries.py": "x = 2\n"}, "none")
    run_git(repo.path, "switch", "-q", "dev")
    repo.commit({"tests/contracts/test_owned_boundaries.py": "x = 3\n"}, "other edit")
    findings, _ = dc.preflight(repo.path, cfg, "ashish", "dev", allow_out_of_order=False)
    assert "would conflict in: tests/contracts/test_owned_boundaries.py" in messages(findings)
    assert "known collision files" in messages(findings, "warning")


def test_preflight_unknown_ref_is_an_error(repo: Repo, cfg: object) -> None:
    findings, _ = dc.preflight(repo.path, cfg, "origin/nope", "dev", allow_out_of_order=False)
    assert "does not resolve" in messages(findings)


# ------------------------------------------------------------------ this repository's own files


def test_ownership_file_is_coherent() -> None:
    cfg, _ = dc.load_config(ROOT, None)
    assert cfg.integrator in cfg.owners and cfg.contract_approver in cfg.owners
    assert set(cfg.order) == set(cfg.owners)
    for key in cfg.owners:
        # each delivery note belongs to exactly its owner, so nobody can edit another's note
        assert dc.owner_of_path(cfg, cfg.note_path(key)) == key
        assert dc.owner_for_branch(cfg, cfg.owners[key].branch) == key


def test_committed_delivery_notes_pass_their_own_validator() -> None:
    cfg, _ = dc.load_config(ROOT, None)
    for key in cfg.owners:
        path = ROOT / cfg.note_path(key)
        assert path.is_file(), f"{cfg.note_path(key)} is missing"
        note, problems = dc.parse_note(path.read_text(encoding="utf-8"))
        assert dc.validate_note(cfg, key, cfg.note_path(key), note, problems) == []


def test_started_notes_carry_the_contract_hash_in_the_tree() -> None:
    cfg, _ = dc.load_config(ROOT, None)
    tree_hash = (ROOT / cfg.contract_hash_file).read_text(encoding="utf-8").split()[0]
    for key in cfg.owners:
        note, _ = dc.parse_note((ROOT / cfg.note_path(key)).read_text(encoding="utf-8"))
        if note.status != "NOT_STARTED":  # a note nobody has started has nothing to re-verify
            assert note.front["contract_sha256"] == tree_hash, f"{key}.md is on another contract"
