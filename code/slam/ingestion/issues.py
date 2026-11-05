"""Ingestion issue record.

Interim, ingestion-private type. Contract 1.0.0 puts "ingestion issues" in
``EvidenceBundle`` but its schema is not published yet. When ``contracts.py``
lands, issues are mapped onto the contract type in one place (the normalizer).

Messages must stay free of source values (emails, names, phone numbers). Point
at a location instead of quoting content, so reports never leak personal data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class Issue:
    """One explicit ingestion problem. A failure is never silent absence."""

    code: str
    severity: Severity
    message: str
    source_id: str | None = None
    locator: str | None = None


class RowErrors:
    """Collects error issues for one row, all tagged with the same id and locator."""

    def __init__(self, source_id: str | None, locator: str) -> None:
        self.issues: list[Issue] = []
        self._source_id = source_id
        self._locator = locator

    def add(self, code: str, message: str) -> None:
        self.issues.append(Issue(code, "error", message, self._source_id, self._locator))

    def warn(self, code: str, message: str) -> None:
        self.issues.append(Issue(code, "warning", message, self._source_id, self._locator))

    @property
    def has_error(self) -> bool:
        return any(i.severity == "error" for i in self.issues)
