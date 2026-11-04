"""Isolated, deny-by-default loading of SQLite-compatible snapshot dumps.

The dump is untrusted text. It is replayed into a private in-memory database
that has no filesystem or network reach:

* an authorizer allows only CREATE TABLE/INDEX, INSERT, SELECT/READ,
  transactions, ``PRAGMA foreign_keys`` and a small list of pure functions.
  ATTACH, other PRAGMAs, triggers, views, virtual tables, recursive CTEs,
  DELETE/UPDATE/DROP/ALTER and ``load_extension`` are all refused;
* extension loading is switched off, the temp store is memory-only, and size
  and complexity limits (input bytes, statement bytes, page count, VM steps,
  SQL length, expression depth, columns, attached DBs) are enforced;
* statements run one at a time, so one refused or broken statement is reported
  with its line range and the rest of the file is still loaded (a *partial*
  parse, never a silent one).

Rows keep the source line range of the INSERT that produced them, which is
what a ``SourceSpan`` needs later. Error messages are scrubbed so they never
echo data values.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Literal

from ..issues import Issue


def _const(name: str, default: int) -> int:
    value = getattr(sqlite3, name, default)
    return int(value)


_CREATE_INDEX = _const("SQLITE_CREATE_INDEX", 1)
_CREATE_TABLE = _const("SQLITE_CREATE_TABLE", 2)
_INSERT = _const("SQLITE_INSERT", 18)
_PRAGMA = _const("SQLITE_PRAGMA", 19)
_READ = _const("SQLITE_READ", 20)
_SELECT = _const("SQLITE_SELECT", 21)
_TRANSACTION = _const("SQLITE_TRANSACTION", 22)
_FUNCTION = _const("SQLITE_FUNCTION", 31)
_SAVEPOINT = _const("SQLITE_SAVEPOINT", 32)
# SQLite raises REINDEX while it populates a new index during CREATE INDEX. It
# only rebuilds indexes inside the private in-memory DB (bounded by the budget).
_REINDEX = _const("SQLITE_REINDEX", 27)

_ALLOWED_ACTIONS = frozenset(
    {_CREATE_INDEX, _CREATE_TABLE, _INSERT, _READ, _SELECT, _TRANSACTION, _SAVEPOINT, _REINDEX}
)
_ALLOWED_PRAGMAS = frozenset({"foreign_keys"})
_ALLOWED_FUNCTIONS = frozenset(
    {
        "json_valid",
        "json_extract",
        "json_type",
        "json",
        "lower",
        "upper",
        "length",
        "typeof",
        "coalesce",
        "ifnull",
        "nullif",
        "abs",
        "trim",
        "ltrim",
        "rtrim",
        "substr",
        "substring",
        "replace",
        "instr",
        "hex",
        "quote",
        "like",
        "glob",
        "count",
        "min",
        "max",
        "sum",
        "total",
        "avg",
    }
)
_ACTION_NAMES = {
    _const("SQLITE_CREATE_TEMP_TABLE", 4): "CREATE TEMP TABLE",
    _const("SQLITE_CREATE_TRIGGER", 7): "CREATE TRIGGER",
    _const("SQLITE_CREATE_VIEW", 8): "CREATE VIEW",
    _const("SQLITE_DELETE", 9): "DELETE",
    _const("SQLITE_DROP_TABLE", 11): "DROP TABLE",
    _PRAGMA: "PRAGMA",
    _const("SQLITE_UPDATE", 23): "UPDATE",
    _const("SQLITE_ATTACH", 24): "ATTACH",
    _const("SQLITE_DETACH", 25): "DETACH",
    _const("SQLITE_ALTER_TABLE", 26): "ALTER TABLE",
    _const("SQLITE_CREATE_VTABLE", 29): "CREATE VIRTUAL TABLE",
    _FUNCTION: "FUNCTION",
    _const("SQLITE_RECURSIVE", 33): "RECURSIVE CTE",
}

# SQLite error text that is safe to surface (identifiers only, never values).
_SAFE_MESSAGE = re.compile(
    r"^(no such (table|column|function): [\w.\"]+"
    r"|table [\w\"]+ already exists"
    r"|[A-Za-z ]+ constraint failed: [\w.(),_ \"]+)$"
)
_HEADER_FIELD = re.compile(r"^([A-Za-z][\w .]{0,63})\s*[:=]\s*(.*)$")
# SQLite itself UPDATEs its schema table while executing CREATE TABLE. That is
# the only UPDATE allowed; with PRAGMA writable_schema denied, SQLite also
# refuses direct user edits of these tables.
_CATALOG_TABLES = frozenset(
    {"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema"}
)
_UPDATE = _const("SQLITE_UPDATE", 23)


@dataclass(frozen=True, slots=True)
class SqlLimits:
    max_input_bytes: int = 8 * 1024 * 1024
    max_statement_bytes: int = 1024 * 1024
    max_statements: int = 200_000
    max_vm_steps: int = 50_000_000
    progress_interval: int = 10_000
    max_pages: int = 16_384  # x 4096-byte pages = 64 MiB of database


@dataclass(frozen=True, slots=True)
class SqlRow:
    table: str
    rowid: int | None
    values: dict[str, object]
    line_start: int | None  # source lines of the INSERT; None if unknown
    line_end: int | None


@dataclass(frozen=True, slots=True)
class SqlTable:
    name: str
    columns: tuple[str, ...]
    rows: tuple[SqlRow, ...]


@dataclass(frozen=True, slots=True)
class CommentLine:
    line: int
    text: str  # evidence text only; never an instruction


@dataclass(frozen=True, slots=True)
class SqlSnapshot:
    tables: dict[str, SqlTable]
    comments: tuple[CommentLine, ...]
    header: dict[str, tuple[str, int]]  # "Captured at" -> (value, line)
    issues: tuple[Issue, ...]
    statements_total: int
    statements_ok: int
    status: Literal["parsed", "partial", "failed"]


class _Guard:
    """Authorizer plus VM-step budget for one sandbox connection."""

    def __init__(self, limits: SqlLimits) -> None:
        self._limits = limits
        self.steps = 0
        self.exhausted = False
        self.last_insert_table: str | None = None
        self.last_denied = ""

    def authorize(
        self,
        action: int,
        arg1: str | None,
        arg2: str | None,
        _db: str | None,
        _source: str | None,
    ) -> int:
        if action == _INSERT and arg1 and not arg1.lower().startswith("sqlite_"):
            self.last_insert_table = arg1
        if action in _ALLOWED_ACTIONS:
            return sqlite3.SQLITE_OK
        if action == _UPDATE and (arg1 or "").lower() in _CATALOG_TABLES:
            return sqlite3.SQLITE_OK
        if action == _PRAGMA and (arg1 or "").lower() in _ALLOWED_PRAGMAS:
            return sqlite3.SQLITE_OK
        if action == _FUNCTION and (arg2 or "").lower() in _ALLOWED_FUNCTIONS:
            return sqlite3.SQLITE_OK
        name = _ACTION_NAMES.get(action, f"action {action}")
        detail = f" {arg1 or arg2}" if action in (_PRAGMA, _FUNCTION) and (arg1 or arg2) else ""
        self.last_denied = f"{name}{detail}"
        return sqlite3.SQLITE_DENY

    def tick(self) -> int:
        self.steps += self._limits.progress_interval
        if self.steps > self._limits.max_vm_steps:
            self.exhausted = True
            return 1  # non-zero aborts the running statement
        return 0


def _harden(con: sqlite3.Connection, limits: SqlLimits) -> None:
    """Configure the connection before any untrusted statement runs."""
    if hasattr(con, "enable_load_extension"):
        con.enable_load_extension(False)
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA trusted_schema=OFF")
    con.execute(f"PRAGMA max_page_count={int(limits.max_pages)}")
    for name, value in (
        ("SQLITE_LIMIT_LENGTH", 1_000_000),
        ("SQLITE_LIMIT_SQL_LENGTH", limits.max_statement_bytes),
        ("SQLITE_LIMIT_COLUMN", 100),
        ("SQLITE_LIMIT_EXPR_DEPTH", 100),
        ("SQLITE_LIMIT_COMPOUND_SELECT", 50),
        ("SQLITE_LIMIT_FUNCTION_ARG", 16),
        ("SQLITE_LIMIT_ATTACHED", 0),
        ("SQLITE_LIMIT_TRIGGER_DEPTH", 0),
    ):
        category = getattr(sqlite3, name, None)
        if category is not None and hasattr(con, "setlimit"):
            con.setlimit(category, value)


def _scrub(exc: BaseException) -> str:
    message = str(exc)
    if "syntax error" in message:
        return "SQL syntax error"
    if _SAFE_MESSAGE.match(message):
        return message
    return f"SQLite error ({type(exc).__name__})"


def _only_comments(lines: list[str]) -> bool:
    return all(not s.strip() or s.strip().startswith("--") for s in lines)


def parse_sql_snapshot(
    data: bytes, *, source_id: str | None = None, limits: SqlLimits | None = None
) -> SqlSnapshot:
    """Replay a SQL dump safely and return its tables, rows and issues."""
    lim = limits or SqlLimits()
    issues: list[Issue] = []

    def add(
        code: str,
        severity: Literal["error", "warning", "info"],
        message: str,
        locator: str | None = None,
    ) -> None:
        issues.append(Issue(code, severity, message, source_id, locator))

    def failed() -> SqlSnapshot:
        return SqlSnapshot({}, (), {}, tuple(issues), 0, 0, "failed")

    if len(data) > lim.max_input_bytes:
        add("SQL_INPUT_TOO_LARGE", "error", f"input is {len(data)} bytes, over the limit")
        return failed()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        add("SQL_NOT_UTF8", "error", "file is not valid UTF-8; not guessing another encoding")
        return failed()
    if "\x00" in text:
        # SQLite statements cannot contain NUL; refusing is safer than truncating at it.
        add("SQL_NUL_BYTE", "error", "file contains a NUL byte; not a plain-text SQL dump")
        return failed()
    if text.startswith("﻿"):
        text = text[1:]
        add("SQL_BOM_STRIPPED", "info", "UTF-8 byte-order mark removed")

    comments: list[CommentLine] = []
    header: dict[str, tuple[str, int]] = {}
    row_lines: dict[tuple[str, int], tuple[int, int]] = {}
    total = ok = 0
    stopped = False

    con = sqlite3.connect(":memory:", isolation_level=None)
    try:
        _harden(con, lim)
        guard = _Guard(lim)
        con.set_authorizer(guard.authorize)
        con.set_progress_handler(guard.tick, lim.progress_interval)

        buffer: list[str] = []
        start = 0
        for number, line in enumerate(text.split("\n"), start=1):
            stripped = line.strip()
            if not buffer:
                if not stripped:
                    continue
                if stripped.startswith("--"):
                    body = stripped[2:].strip()
                    comments.append(CommentLine(number, body))
                    match = _HEADER_FIELD.match(body)
                    if match:
                        key = match.group(1).strip()
                        if key not in header:  # first occurrence wins
                            header[key] = (match.group(2).strip(), number)
                    continue
                start = number
            buffer.append(line)
            statement = "\n".join(buffer)
            if len(statement) > lim.max_statement_bytes:
                add(
                    "SQL_STATEMENT_TOO_LARGE",
                    "error",
                    "statement exceeds size limit; stopped",
                    f"line {start}",
                )
                stopped = True
                break
            if not sqlite3.complete_statement(statement):
                continue

            buffer = []
            total += 1
            locator = f"lines {start}-{number}" if number != start else f"line {start}"
            guard.last_insert_table = None
            try:
                cursor = con.execute(statement)
            except (sqlite3.Error, sqlite3.Warning) as exc:
                message = str(exc)
                if "not authorized" in message:
                    add(
                        "SQL_STATEMENT_DENIED",
                        "error",
                        f"refused by sandbox: {guard.last_denied or 'unsupported operation'}",
                        locator,
                    )
                elif guard.exhausted or "interrupted" in message:
                    add(
                        "SQL_BUDGET_EXCEEDED",
                        "error",
                        "execution step budget exceeded; stopped",
                        locator,
                    )
                    stopped = True
                elif "database or disk is full" in message:
                    add(
                        "SQL_STORAGE_LIMIT",
                        "error",
                        "in-memory size limit reached; stopped",
                        locator,
                    )
                    stopped = True
                elif "one statement at a time" in message:
                    add(
                        "SQL_MULTIPLE_STATEMENTS",
                        "error",
                        "more than one statement on a line; not executed",
                        locator,
                    )
                else:
                    add("SQL_STATEMENT_ERROR", "error", _scrub(exc), locator)
            else:
                ok += 1
                if guard.last_insert_table is not None and cursor.lastrowid:
                    row_lines[(guard.last_insert_table.lower(), cursor.lastrowid)] = (start, number)
            if stopped:
                break
            if total >= lim.max_statements:
                add("SQL_TOO_MANY_STATEMENTS", "error", "statement count limit reached; stopped")
                stopped = True
                break

        if buffer and not stopped and not _only_comments(buffer):
            add(
                "SQL_UNTERMINATED_STATEMENT",
                "error",
                "file ends inside a statement",
                f"line {start}",
            )

        con.set_authorizer(None)
        con.set_progress_handler(None, 0)
        tables = _dump_tables(con, row_lines)
    finally:
        con.close()

    if total == 0:
        add("SQL_NO_STATEMENTS", "warning", "file contains no SQL statements")
    has_error = any(i.severity == "error" for i in issues)
    status: Literal["parsed", "partial", "failed"]
    if not has_error:
        status = "parsed"
    elif ok:
        status = "partial"
    else:
        status = "failed"
    return SqlSnapshot(tables, tuple(comments), header, tuple(issues), total, ok, status)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _dump_tables(
    con: sqlite3.Connection, row_lines: dict[tuple[str, int], tuple[int, int]]
) -> dict[str, SqlTable]:
    """Read every table out of the sandbox with the authorizer removed.

    Only catalog-derived, properly quoted identifiers reach the SQL text.
    """
    names = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' ORDER BY name"
        )
    ]
    result: dict[str, SqlTable] = {}
    for name in names:
        columns = tuple(r[1] for r in con.execute(f"PRAGMA table_info({_quote(name)})"))
        rows: list[SqlRow] = []
        try:
            cursor = con.execute(f"SELECT rowid, * FROM {_quote(name)} ORDER BY rowid")
            with_rowid = True
        except sqlite3.OperationalError:  # WITHOUT ROWID table
            cursor = con.execute(f"SELECT * FROM {_quote(name)}")
            with_rowid = False
        for record in cursor:
            rowid: int | None = record[0] if with_rowid else None
            cells = record[1:] if with_rowid else record
            span = row_lines.get((name.lower(), rowid)) if rowid is not None else None
            rows.append(
                SqlRow(
                    name,
                    rowid,
                    dict(zip(columns, cells, strict=True)),
                    span[0] if span else None,
                    span[1] if span else None,
                )
            )
        result[name] = SqlTable(name, columns, tuple(rows))
    return result


__all__ = [
    "CommentLine",
    "SqlLimits",
    "SqlRow",
    "SqlSnapshot",
    "SqlTable",
    "parse_sql_snapshot",
]
