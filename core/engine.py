"""Deterministic Goal -> Plan -> Execute -> Observe -> Adapt -> Verify loop."""
from __future__ import annotations

import logging
import inspect
import re
from datetime import datetime
from typing import Awaitable, Callable, Any

from core.adapter import Adapter
from core.config import settings
from core.hitl import HITLManager
from core.observer import Observer
from core.planner import Planner
from core.state import (ActionStep, AgentStatus, ExecutionTrace, Goal, HITLDecision,
                        HITLRequest, StepStatus)
from core.verifier import Verifier
from memory.company_context import company_policy
from memory.episodic_memory import episodic_memory
from tools.registry import ToolRegistry, registry
from tools.browser.browser_tool import browser_manager

logger = logging.getLogger(__name__)


class AgentEngine:
    def __init__(self, planner: Planner | None = None, tool_registry: ToolRegistry | None = None,
                 observer: Observer | None = None, adapter: Adapter | None = None,
                 verifier: Verifier | None = None, hitl: HITLManager | None = None,
                 max_steps: int | None = None,
                 event_sink: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None) -> None:
        self.planner = planner or Planner()
        self.tools = tool_registry or registry
        self.observer = observer or Observer()
        self.adapter = adapter or Adapter()
        self.verifier = verifier or Verifier()
        self.hitl = hitl or HITLManager()
        self.max_steps = max_steps or settings.max_steps
        self.event_sink = event_sink

    async def _emit(self, event: dict[str, Any]) -> None:
        if self.event_sink:
            result = self.event_sink(event)
            if inspect.isawaitable(result):
                await result

    async def run(self, goal: Goal) -> ExecutionTrace:
        trace = ExecutionTrace(goal=goal, agent_status=AgentStatus.PLANNING)
        browser_started = False
        try:
            if not self.tools.list_tools():
                from tools import register_all_tools
                register_all_tools()
            planning_goal = goal
            if self.tools.list_tools() and self.tools.get("find_latest_invoice") is None:
                planning_goal = goal.model_copy(update={"context": {**goal.context, "_compatibility_mode": True}})
            trace.plan = await self.planner.create_plan(planning_goal)
            trace.agent_status = AgentStatus.EXECUTING
            browser_needed = any(
                step.tool_name in {"navigate", "click", "type_text", "select_option", "extract_text", "take_screenshot", "get_dom", "submit_invoice", "query_erp_db"}
                for milestone in trace.plan.milestones for step in milestone.steps
            )
            # Injectable unit-test registries intentionally omit browser tools;
            # only launch Playwright when this run can actually execute them.
            if browser_needed and self.tools.get("navigate") is not None and browser_manager._page is None:
                await browser_manager.start(headless=True)
                browser_started = True
            calls = 0
            seen: set[tuple[str, str]] = set()
            replans = 0
            while True:
                replan_requested = False
                for milestone in trace.plan.milestones:
                    for step in milestone.steps:
                        if step.status == StepStatus.COMPLETED:
                            continue
                        if calls >= self.max_steps:
                            raise RuntimeError(f"Step budget exhausted ({self.max_steps})")
                        if not step.tool_name:
                            raise RuntimeError(f"Step has no tool: {step.description}")
                        step.tool_args = self._resolve_args(step.tool_args, trace)
                        signature = (step.tool_name, repr(sorted(step.tool_args.items())))
                        if signature in seen and step.retry_count == 0:
                            raise RuntimeError("Cycle detected in planned actions")
                        seen.add(signature)
                        policy = company_policy.evaluate(step.tool_name, step.tool_args, self.observer.memory.all_facts())
                        if step.requires_hitl or policy.requires_approval or self._requires_amount_approval(step):
                            await self._approval(trace, step)
                        step.status = StepStatus.IN_PROGRESS
                        result = await self.tools.execute(step.tool_name, **step.tool_args)
                        calls += 1
                        await self._emit({"type": "tool_call", "step_id": step.id, "tool": step.tool_name, "args": step.tool_args})
                        observation = self.observer.observe(step, result)
                        trace.observations.append(observation)
                        await self._emit({"type": "observation", "step_id": step.id, "success": observation.success, "facts": observation.facts_extracted, "error": result.error_message})
                        trace.working_memory = self.observer.memory.all_facts()
                        if observation.success:
                            step.status = StepStatus.COMPLETED
                            step.result = str(result.data)[:4000]
                            step.completed_at = datetime.utcnow()
                            continue
                        step.error = result.error_message
                        decision = self.adapter.recover(step, result)
                        if decision.strategy == "adjust_args" and decision.tool_args:
                            step.tool_args = decision.tool_args
                            decision.strategy = "retry_same"
                        if decision.strategy == "retry_same":
                            step.retry_count += 1
                            step.status = StepStatus.RETRYING
                            while step.retry_count <= self.adapter.max_retries:
                                step.tool_args = self._resolve_args(step.tool_args, trace)
                                result = await self.tools.execute(step.tool_name, **step.tool_args)
                                calls += 1
                                observation = self.observer.observe(step, result)
                                trace.observations.append(observation)
                                await self._emit({"type": "observation", "step_id": step.id, "success": observation.success, "facts": observation.facts_extracted, "error": result.error_message, "retry": step.retry_count})
                                trace.working_memory = self.observer.memory.all_facts()
                                if observation.success:
                                    step.status = StepStatus.COMPLETED
                                    step.result = str(result.data)[:4000]
                                    break
                                step.retry_count += 1
                            if step.status == StepStatus.COMPLETED:
                                continue
                        if decision.strategy == "replan":
                            replans += 1
                            if replans > self.adapter.max_retries:
                                step.status = StepStatus.FAILED
                                raise RuntimeError(step.error or "Replanning budget exhausted")
                            trace.agent_status = AgentStatus.ADAPTING
                            trace.plan = await self.planner.replan(
                                goal, trace.plan, step.error or "tool failure"
                            )
                            seen.clear()
                            replan_requested = True
                            break
                        step.status = StepStatus.FAILED
                        raise RuntimeError(step.error or "Tool execution failed")
                    if replan_requested:
                        break
                if not replan_requested:
                    break
                trace.agent_status = AgentStatus.EXECUTING
            trace.agent_status = AgentStatus.VERIFYING
            trace.verification = await self.verifier.verify(trace)
            trace.agent_status = AgentStatus.COMPLETED if trace.verification.passed else AgentStatus.FAILED
            if not trace.verification.passed:
                trace.error = trace.verification.failure_reason
            try:
                episodic_memory.store(
                    f"Goal: {goal.raw_text}\nStatus: {trace.agent_status.value}\nFacts: {trace.working_memory}",
                    {"status": trace.agent_status.value, "run_id": trace.id},
                )
            except Exception as exc:
                logger.warning("Could not persist episodic memory: %s", exc)
        except Exception as exc:
            trace.agent_status = AgentStatus.FAILED
            trace.error = str(exc)
            logger.exception("Agent run failed: %s", exc)
        trace.completed_at = datetime.utcnow()
        if browser_started:
            await browser_manager.stop()
        return trace

    @staticmethod
    def _resolve_args(args: dict[str, Any], trace: ExecutionTrace) -> dict[str, Any]:
        facts = {**trace.working_memory, "run_id": trace.id}
        for observation in reversed(trace.observations):
            facts.update(observation.facts_extracted)
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str):
                resolved[key] = re.sub(r"\{\{\s*([\w-]+)\s*\}\}", lambda match: str(facts.get(match.group(1), match.group(0))), value)
            else:
                resolved[key] = value
        return resolved

    async def _approval(self, trace: ExecutionTrace, step: ActionStep) -> None:
        request = HITLRequest(reason=f"Approval required for: {step.description}",
                              context_summary=trace.goal.raw_text,
                              options=["Approve", "Reject", "Provide correction"],
                              relevant_data=step.tool_args)
        trace.agent_status = AgentStatus.WAITING_HITL
        trace.hitl_requests.append(request)
        resolved = await self.hitl.request(request)
        if resolved.decision != HITLDecision.APPROVED:
            raise RuntimeError(f"Human approval {resolved.decision.value}")
        trace.agent_status = AgentStatus.EXECUTING

    @staticmethod
    def _requires_amount_approval(step: ActionStep) -> bool:
        threshold = settings.hitl_amount_threshold
        for key, value in step.tool_args.items():
            if "amount" in key.lower() or "total" in key.lower():
                try:
                    if float(str(value).replace(",", "")) > threshold:
                        return True
                except (TypeError, ValueError):
                    continue
        return False
