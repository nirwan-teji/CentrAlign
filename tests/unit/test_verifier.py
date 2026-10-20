from __future__ import annotations

import json

import pytest

from core.evidence import EvidencePackager
from core.state import ExecutionTrace, Goal, TaskPlan, Milestone, ActionStep, Observation, ToolResult, ToolResultStatus
from core.verifier import Verifier


def _trace(require_db: bool, db_confirmed: bool) -> ExecutionTrace:
    goal = Goal(raw_text="Submit invoice", context={"require_independent_verification": require_db})
    step = ActionStep(description="submit", tool_name="submit_invoice", status="completed")
    plan = TaskPlan(goal_id=goal.id, milestones=[Milestone(title="x", description="x", steps=[step])])
    result = ToolResult(tool_name="query_erp_db" if db_confirmed else "submit_invoice", status=ToolResultStatus.SUCCESS, data={"id": "INV-1"})
    trace = ExecutionTrace(goal=goal, plan=plan)
    trace.observations.append(Observation(step_id=step.id, tool_result=result, success=True, facts_extracted={"id": "INV-1"}))
    return trace


@pytest.mark.asyncio
async def test_verifier_rejects_missing_independent_confirmation():
    result = await Verifier().verify(_trace(True, False))
    assert not result.passed
    assert "independent" in result.failure_reason.lower()


@pytest.mark.asyncio
async def test_verifier_accepts_database_confirmation():
    result = await Verifier().verify(_trace(True, True))
    assert result.passed


def test_evidence_packager_writes_audit_files(tmp_path):
    trace = _trace(False, False)
    paths = EvidencePackager(str(tmp_path)).package(trace)
    assert (tmp_path / trace.id / "evidence_package.json").exists()
    assert (tmp_path / trace.id / "audit_summary.md").exists()
    assert json.loads((tmp_path / trace.id / "evidence_package.json").read_text())["goal"]["raw_text"] == "Submit invoice"
