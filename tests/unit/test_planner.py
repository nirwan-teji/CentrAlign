from __future__ import annotations

import pytest

from core.planner import Planner
from core.state import Goal, StepStatus


class NoLLM:
    async def complete_json(self, **kwargs):
        raise RuntimeError("offline")


@pytest.mark.asyncio
async def test_planner_has_deterministic_offline_invoice_plan():
    plan = await Planner(llm=NoLLM()).create_plan(Goal(raw_text="Process incoming invoices"))
    assert plan.total_steps >= 3
    assert all(step.tool_name for m in plan.milestones for step in m.steps)


@pytest.mark.asyncio
async def test_replan_preserves_completed_steps():
    planner = Planner(llm=NoLLM())
    goal = Goal(raw_text="Process incoming invoices")
    old = await planner.create_plan(goal)
    old.milestones[0].steps[0].status = StepStatus.COMPLETED
    revised = await planner.replan(goal, old, "temporary error")
    assert revised.version == 2
    assert revised.milestones[0].steps[0].status == StepStatus.COMPLETED
