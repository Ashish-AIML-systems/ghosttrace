"""Frozen planning interface: ``plan(context)`` works from the context alone (contract 1.1.0)."""

from slam.contracts import CaseAnswer, CaseContext

from .engine import plan_case


def plan(context: CaseContext) -> CaseAnswer:
    """Decide and order one case from its context; exposure is assumed when unknown."""

    return plan_case(context)
