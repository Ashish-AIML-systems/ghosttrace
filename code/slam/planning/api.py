"""Frozen planning interface; implementation is owned by Satvika."""

from slam.contracts import CaseAnswer, CaseContext


def plan(context: CaseContext) -> CaseAnswer:
    del context
    raise NotImplementedError("policy planning is owned by Satvika")
