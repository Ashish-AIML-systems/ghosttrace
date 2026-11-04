"""SQLite + FTS5 evidence ledger.

Stores normalized sources, observations, identifiers and ingestion issues so
evidence can be searched and re-read without re-parsing. Writes are idempotent:
a source version is identified by ``(source_id, sha256, fingerprint)``, where the
fingerprint covers parser, normalizer, prompt, schema, provider, model and
settings. Writing the same version again changes nothing; a changed version
atomically replaces the older rows of that source.

All SQL is parameterised. The schema is created by numbered migrations tracked
in ``PRAGMA user_version``, so opening an existing ledger is always safe.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Self

from slam.contracts import IngestionIssue, IssueSeverity, Observation, SourceRecord

_MAX_FTS_FIELD_CHARS = 4000
_WORD = re.compile(r"[\w@.+\-]+", re.UNICODE)


class LedgerError(RuntimeError):
    """The ledger cannot be used safely (for example SQLite lacks FTS5)."""


_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE sources (
        source_id   TEXT NOT NULL,
        sha256      TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        position    INTEGER NOT NULL,
        record_json TEXT NOT NULL,
        PRIMARY KEY (source_id, sha256, fingerprint)
    );
    CREATE TABLE observations (
        observation_id  TEXT PRIMARY KEY,
        source_id       TEXT NOT NULL,
        source_sha256   TEXT NOT NULL,
        fingerprint     TEXT NOT NULL,
        ordinal         INTEGER NOT NULL,
        system_id       TEXT NOT NULL,
        resource_id     TEXT NOT NULL,
        category        TEXT NOT NULL,
        observed_state  TEXT NOT NULL,
        effective_time  TEXT NOT NULL,
        source_kind     TEXT NOT NULL,
        payload_json    TEXT NOT NULL
    );
    CREATE INDEX idx_obs_resource ON observations (system_id, resource_id);
    CREATE INDEX idx_obs_time ON observations (effective_time);
    CREATE INDEX idx_obs_source ON observations (source_id, source_sha256, fingerprint, ordinal);
    CREATE TABLE identifiers (
        observation_id TEXT NOT NULL REFERENCES observations (observation_id) ON DELETE CASCADE,
        kind           TEXT NOT NULL,
        value          TEXT NOT NULL,
        PRIMARY KEY (observation_id, kind, value)
    );
    CREATE INDEX idx_ident_value ON identifiers (value);
    CREATE TABLE issues (
        id          INTEGER PRIMARY KEY,
        source_id   TEXT,
        sha256      TEXT,
        fingerprint TEXT,
        ordinal     INTEGER NOT NULL,
        severity    TEXT NOT NULL,
        code        TEXT NOT NULL,
        message     TEXT NOT NULL,
        locator     TEXT
    );
    CREATE INDEX idx_issue_source ON issues (source_id, sha256, fingerprint, ordinal);
    CREATE VIRTUAL TABLE observation_fts USING fts5 (
        observation_id UNINDEXED,
        body,
        tokenize = 'unicode61 remove_diacritics 2'
    );
    """,
)


def _leaf_text(value: object, budget: list[int]) -> Iterator[str]:
    """Yield string leaves of nested data until the character budget is spent."""
    if budget[0] <= 0:
        return
    if isinstance(value, str):
        budget[0] -= len(value)
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _leaf_text(item, budget)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _leaf_text(item, budget)


def _body(observation: Observation) -> str:
    parts = [
        observation.system_id,
        observation.resource_id,
        observation.category,
        observation.observed_state,
        *observation.identifiers.values(),
        *observation.subject_hints,
    ]
    budget = [_MAX_FTS_FIELD_CHARS]
    parts.extend(_leaf_text(observation.fields.get("source"), budget))
    return " ".join(parts)


def _fts_query(text: str) -> str:
    """Quote every word so user text can never be parsed as FTS5 syntax."""
    words = _WORD.findall(text)
    return " ".join('"' + word.replace('"', '""') + '"' for word in words)


class Ledger:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(":memory:" if path is None else str(path), isolation_level=None)
        self._db.execute("PRAGMA foreign_keys=ON")
        if path is not None:
            self._db.execute("PRAGMA journal_mode=WAL")
        self._require_fts5()
        self.migrate()

    # -- lifecycle -------------------------------------------------------------

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _require_fts5(self) -> None:
        try:
            self._db.execute("CREATE VIRTUAL TABLE temp._fts_probe USING fts5(x)")
            self._db.execute("DROP TABLE temp._fts_probe")
        except sqlite3.OperationalError as exc:
            raise LedgerError("this SQLite build has no FTS5 support") from exc

    @property
    def schema_version(self) -> int:
        row = self._db.execute("PRAGMA user_version").fetchone()
        return int(row[0])

    def migrate(self) -> None:
        """Apply any missing migrations. Safe to call repeatedly."""
        current = self.schema_version
        if current > len(_MIGRATIONS):
            raise LedgerError(f"ledger schema {current} is newer than this code understands")
        for version in range(current, len(_MIGRATIONS)):
            with self._transaction():
                for statement in _split(_MIGRATIONS[version]):
                    self._db.execute(statement)
                self._db.execute(f"PRAGMA user_version={version + 1}")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._db.execute("BEGIN")
        try:
            yield
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        else:
            self._db.execute("COMMIT")

    # -- writes ----------------------------------------------------------------

    def has_source(self, source_id: str, sha256: str, fingerprint: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM sources WHERE source_id=? AND sha256=? AND fingerprint=?",
            (source_id, sha256, fingerprint),
        ).fetchone()
        return row is not None

    def write_source(
        self,
        source: SourceRecord,
        fingerprint: str,
        position: int,
        observations: Sequence[Observation],
        issues: Sequence[IngestionIssue],
    ) -> bool:
        """Store one source version. Returns ``False`` if it was already stored."""
        if self.has_source(source.source_id, source.sha256, fingerprint):
            return False
        with self._transaction():
            self._delete_source(source.source_id)
            self._db.execute(
                "INSERT INTO sources (source_id, sha256, fingerprint, position, record_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (source.source_id, source.sha256, fingerprint, position, source.model_dump_json()),
            )
            for ordinal, observation in enumerate(observations):
                self._db.execute(
                    "INSERT INTO observations (observation_id, source_id, source_sha256, "
                    "fingerprint, ordinal, system_id, resource_id, category, observed_state, "
                    "effective_time, source_kind, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        observation.observation_id,
                        source.source_id,
                        source.sha256,
                        fingerprint,
                        ordinal,
                        observation.system_id,
                        observation.resource_id,
                        observation.category,
                        observation.observed_state,
                        observation.effective_time.isoformat(),
                        observation.source_kind.value,
                        observation.model_dump_json(),
                    ),
                )
                for kind, value in observation.identifiers.items():
                    self._db.execute(
                        "INSERT OR IGNORE INTO identifiers (observation_id, kind, value) "
                        "VALUES (?, ?, ?)",
                        (observation.observation_id, kind, value),
                    )
                self._db.execute(
                    "INSERT INTO observation_fts (observation_id, body) VALUES (?, ?)",
                    (observation.observation_id, _body(observation)),
                )
            for ordinal, issue in enumerate(issues):
                self._db.execute(
                    "INSERT INTO issues (source_id, sha256, fingerprint, ordinal, severity, "
                    "code, message, locator) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        issue.source_id,
                        source.sha256,
                        fingerprint,
                        ordinal,
                        issue.severity.value,
                        issue.code,
                        issue.message,
                        issue.locator,
                    ),
                )
        return True

    def _delete_source(self, source_id: str) -> None:
        """Remove every stored version of ``source_id`` (called inside a transaction)."""
        ids = [
            r[0]
            for r in self._db.execute(
                "SELECT observation_id FROM observations WHERE source_id=?", (source_id,)
            )
        ]
        for observation_id in ids:
            self._db.execute(
                "DELETE FROM observation_fts WHERE observation_id=?", (observation_id,)
            )
        self._db.execute("DELETE FROM observations WHERE source_id=?", (source_id,))
        self._db.execute("DELETE FROM issues WHERE source_id=?", (source_id,))
        self._db.execute("DELETE FROM sources WHERE source_id=?", (source_id,))

    # -- reads -----------------------------------------------------------------

    def read_source(
        self, source_id: str, sha256: str, fingerprint: str
    ) -> tuple[SourceRecord, list[Observation], list[IngestionIssue]] | None:
        row = self._db.execute(
            "SELECT record_json FROM sources WHERE source_id=? AND sha256=? AND fingerprint=?",
            (source_id, sha256, fingerprint),
        ).fetchone()
        if row is None:
            return None
        observations = [
            Observation.model_validate_json(r[0])
            for r in self._db.execute(
                "SELECT payload_json FROM observations WHERE source_id=? AND source_sha256=? "
                "AND fingerprint=? ORDER BY ordinal",
                (source_id, sha256, fingerprint),
            )
        ]
        issues = [
            IngestionIssue(
                severity=IssueSeverity(r[0]),
                code=r[1],
                message=r[2],
                source_id=r[3],
                locator=r[4],
            )
            for r in self._db.execute(
                "SELECT severity, code, message, source_id, locator FROM issues "
                "WHERE source_id=? AND sha256=? AND fingerprint=? ORDER BY ordinal",
                (source_id, sha256, fingerprint),
            )
        ]
        return SourceRecord.model_validate_json(row[0]), observations, issues

    def find_by_identifier(self, value: str) -> list[Observation]:
        """Observations that carry ``value`` (exact, case-insensitive) as any identifier."""
        rows = self._db.execute(
            "SELECT DISTINCT o.payload_json FROM observations o "
            "JOIN identifiers i ON i.observation_id = o.observation_id "
            "WHERE lower(i.value) = lower(?) ORDER BY o.effective_time, o.observation_id",
            (value,),
        )
        return [Observation.model_validate_json(r[0]) for r in rows]

    def find_by_resource(self, system_id: str, resource_id: str) -> list[Observation]:
        rows = self._db.execute(
            "SELECT payload_json FROM observations WHERE system_id=? AND resource_id=? "
            "ORDER BY effective_time, observation_id",
            (system_id, resource_id),
        )
        return [Observation.model_validate_json(r[0]) for r in rows]

    def search(self, text: str, limit: int = 50) -> list[Observation]:
        """Full-text search over resource ids, identifiers and record text."""
        query = _fts_query(text)
        if not query:
            return []
        rows = self._db.execute(
            "SELECT o.payload_json FROM observation_fts f "
            "JOIN observations o ON o.observation_id = f.observation_id "
            "WHERE observation_fts MATCH ? ORDER BY rank, o.observation_id LIMIT ?",
            (query, int(limit)),
        )
        return [Observation.model_validate_json(r[0]) for r in rows]

    def counts(self) -> dict[str, int]:
        return {
            name: int(self._db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in ("sources", "observations", "identifiers", "issues")
        }


def _split(script: str) -> list[str]:
    """Split a migration script into single statements (no semicolons inside literals)."""
    return [part.strip() for part in script.split(";") if part.strip()]
