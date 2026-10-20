"""Independent verification of the evidence collected during execution."""
from __future__ import annotations

from typing import Awaitable, Callable, Any

from core.state import ExecutionTrace, VerificationResult, ToolResultStatus


class Verifier:
    def __init__(self, independent_checker: Callable[[ExecutionTrace], Awaitable[dict[str, Any]]] | None = None) -> None:
        self.independent_checker = independent_checker

    async def verify(self, trace: ExecutionTrace) -> VerificationResult:
        successful = [o for o in trace.observations if o.success]
        evidence = {
            "successful_steps": len(successful),
            "observations": [o.facts_extracted for o in successful],
            "screenshots": [o.tool_result.screenshot_path for o in successful if o.tool_result.screenshot_path],
        }
        if not trace.plan or trace.plan.completed_steps != trace.plan.total_steps:
            return VerificationResult(passed=False, evidence=evidence, failure_reason="Not all planned steps completed.")
        submitted = [o for o in successful if o.tool_result.tool_name == "submit_invoice"]
        real_mutation_plan = any(
            s.tool_name == "query_erp_db"
            for milestone in (trace.plan.milestones if trace.plan else [])
            for s in milestone.steps
        )
        if submitted and real_mutation_plan:
            confirmations = [o for o in successful if o.tool_result.tool_name == "query_erp_db"]
            if not confirmations:
                return VerificationResult(passed=False, evidence=evidence, failure_reason="ERP mutation completed without an independent database confirmation.")
            if not evidence["screenshots"]:
                return VerificationResult(passed=False, evidence=evidence, failure_reason="ERP mutation completed without visual evidence.")
            evidence["submission"] = submitted[-1].tool_result.data
            evidence["database_confirmation"] = [o.tool_result.data for o in confirmations]
        if self.independent_checker:
            try:
                check = await self.independent_checker(trace)
            except Exception as exc:
                return VerificationResult(passed=False, evidence=evidence, failure_reason=f"Independent check failed: {exc}")
            evidence["independent_check"] = check
            if not check.get("passed", False):
                return VerificationResult(passed=False, evidence=evidence, failure_reason=check.get("reason", "Independent check did not confirm the outcome."))
        if trace.goal.context.get("require_independent_verification"):
            confirmations = [
                o for o in successful
                if o.tool_result.tool_name == "query_erp_db"
                and o.tool_result.status == ToolResultStatus.SUCCESS
            ]
            if not confirmations:
                return VerificationResult(passed=False, evidence=evidence, failure_reason="No independent ERP/database confirmation was collected.")
            evidence["database_confirmation"] = [o.tool_result.data for o in confirmations]
        return VerificationResult(passed=True, evidence=evidence)
