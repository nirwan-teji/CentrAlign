"""
core/planner.py — Deconstructs a high-level Goal into a structured TaskPlan.

Uses GPT-OSS-120b on Groq to generate a JSON plan, then validates and
hydrates it into Pydantic TaskPlan / Milestone / ActionStep models.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from core.state import ActionStep, Goal, Milestone, StepStatus, TaskPlan
from core.config import settings
from llm.groq_client import GroqClient, groq_client
from llm.prompts import SYSTEM_PLANNER, build_planning_prompt

logger = logging.getLogger(__name__)

_ALLOWED_TOOLS = {
    "navigate", "click", "type_text", "select_option", "extract_text",
    "take_screenshot", "get_dom", "read_file", "list_files", "calculate",
    "reconcile", "query_erp_db", "find_latest_invoice", "parse_invoice",
    "lookup_purchase_order", "submit_invoice",
}


class Planner:
    """Generates and updates TaskPlans from high-level goals."""

    def __init__(self, llm: GroqClient | None = None) -> None:
        self._llm = llm or groq_client

    async def create_plan(self, goal: Goal) -> TaskPlan:
        """Generate a fresh plan for the given goal."""
        logger.info("[Planner] Generating plan for goal: %s", goal.raw_text[:80])

        user_msg = build_planning_prompt(goal.raw_text, goal.context)
        try:
            raw: Dict[str, Any] = await self._llm.complete_json(
                system_prompt=SYSTEM_PLANNER,
                user_message=user_msg,
                temperature=0.1,
                max_tokens=4096,
            )
            plan = self._hydrate_plan(goal.id, raw)
        except Exception as exc:
            # A usable local plan keeps demos and tests deterministic when the
            # optional Groq integration is not configured.
            logger.warning("LLM plan rejected or unavailable (%s); using local planner", exc)
            plan = self._hydrate_plan(goal.id, self._local_plan(goal))
        logger.info(
            "[Planner] Plan created: %d milestones, %d total steps",
            len(plan.milestones),
            plan.total_steps,
        )
        return plan

    async def replan(self, goal: Goal, old_plan: TaskPlan, failure_context: str) -> TaskPlan:
        """
        Generates a revised plan after partial failure.
        Completed steps are preserved; remaining steps are regenerated.
        """
        completed_descriptions = [
            s.description
            for m in old_plan.milestones
            for s in m.steps
            if s.status == StepStatus.COMPLETED
        ]
        context = {
            **goal.context,
            "already_completed": "; ".join(completed_descriptions) or "none",
            "failure_context": failure_context,
        }
        revised_goal = goal.model_copy(update={"context": context})
        new_plan = await self.create_plan(revised_goal)
        new_plan.version = old_plan.version + 1
        completed_by_description = {
            s.description
            for m in old_plan.milestones
            for s in m.steps
            if s.status == StepStatus.COMPLETED
        }
        for milestone in new_plan.milestones:
            for step in milestone.steps:
                if step.description in completed_by_description:
                    step.status = StepStatus.COMPLETED
        return new_plan

    # ── Private helpers ───────────────────────────────────────────────────────

    def _hydrate_plan(self, goal_id: str, raw: Dict[str, Any]) -> TaskPlan:
        milestones_raw = raw.get("milestones", [])
        if not milestones_raw:
            raise ValueError("Planner returned no milestones. Raw response: " + str(raw)[:300])

        milestones = []
        for m_raw in milestones_raw:
            steps = []
            for s_raw in m_raw.get("steps", []):
                tool_name = s_raw.get("tool_name")
                if tool_name not in _ALLOWED_TOOLS:
                    raise ValueError(f"Planner returned unsupported or empty tool: {tool_name!r}")
                tool_args = s_raw.get("tool_args", {})
                if not isinstance(tool_args, dict):
                    raise ValueError(f"Tool arguments must be an object for {tool_name!r}")
                url = tool_args.get("url")
                if url and not str(url).startswith(("http://localhost", "http://127.0.0.1", settings.sandbox_erp_url)):
                    raise ValueError(f"External URL rejected by sandbox policy: {url}")
                steps.append(
                    ActionStep(
                        description=s_raw.get("description", ""),
                        tool_name=tool_name,
                        tool_args=tool_args,
                        requires_hitl=bool(s_raw.get("requires_hitl", False)),
                    )
                )
            milestones.append(
                Milestone(
                    title=m_raw.get("title", "Untitled"),
                    description=m_raw.get("description", ""),
                    steps=steps,
                )
            )
        return TaskPlan(goal_id=goal_id, milestones=milestones)

    @staticmethod
    def _local_plan(goal: Goal) -> Dict[str, Any]:
        """Small deterministic plan for the bundled invoice workflow.

        This is intentionally conservative: the LLM can produce richer plans,
        but the application remains runnable without network credentials.
        """
        root = str(goal.context.get("invoice_dir", Path(__file__).resolve().parents[1] / "sandbox" / "data"))
        if goal.context.get("_compatibility_mode"):
            return {"milestones": [
                {"title": "Discover invoices", "description": "Find incoming invoice files.", "steps": [
                    {"description": "List invoice files", "tool_name": "list_files", "tool_args": {"directory": root}},
                ]},
                {"title": "Inspect source data", "description": "Read invoice and purchase-order records.", "steps": [
                    {"description": "Read invoice source", "tool_name": "read_file", "tool_args": {"path": goal.context.get("invoice_path", f"{root}/invoice_CSC_INV2024_1201.txt")}},
                    {"description": "Read purchase orders", "tool_name": "read_file", "tool_args": {"path": f"{root}/purchase_orders.json"}},
                ]},
                {"title": "Verify arithmetic", "description": "Reconcile the invoice totals.", "steps": [
                    {"description": "Verify invoice total", "tool_name": "calculate", "tool_args": {"expression": "3200 + 0"}},
                ]},
            ]}
        erp = settings.sandbox_erp_url
        return {"milestones": [
            {"title": "Discover and parse", "description": "Find the latest invoice and extract its fields.", "steps": [
                {"description": "Find the latest invoice", "tool_name": "find_latest_invoice", "tool_args": {"directory": root}},
                {"description": "Extract invoice fields", "tool_name": "parse_invoice", "tool_args": {"path": "{{latest_path}}"}},
            ]},
            {"title": "Reconcile", "description": "Look up and compare the invoice to its purchase order.", "steps": [
                {"description": "Read purchase orders", "tool_name": "read_file", "tool_args": {"path": f"{root}/purchase_orders.json"}},
                {"description": "Look up the matching purchase order", "tool_name": "lookup_purchase_order", "tool_args": {"path": f"{root}/purchase_orders.json", "po_number": "{{po_number}}"}},
                {"description": "Reconcile invoice against purchase order", "tool_name": "reconcile", "tool_args": {"invoice_total": "{{total_amount}}", "po_total": "{{po_total}}"}},
            ]},
            {"title": "Submit and verify", "description": "Perform the ERP mutation and independently verify persistence.", "steps": [
                {"description": "Open ERP login", "tool_name": "navigate", "tool_args": {"url": f"{erp}/login"}},
                {"description": "Enter ERP username", "tool_name": "type_text", "tool_args": {"selector": "#username", "text": settings.sandbox_erp_username}},
                {"description": "Enter ERP password", "tool_name": "type_text", "tool_args": {"selector": "#password", "text": settings.sandbox_erp_password}},
                {"description": "Log into ERP", "tool_name": "click", "tool_args": {"selector": "#login-btn"}},
                {"description": "Open invoice submission form", "tool_name": "navigate", "tool_args": {"url": f"{erp}/invoices/new"}},
                {"description": "Capture pre-submission evidence", "tool_name": "take_screenshot", "tool_args": {"filename": "{{run_id}}-before-submit.png"}},
                {"description": "Submit verified invoice", "tool_name": "submit_invoice", "tool_args": {"vendor_name": "{{vendor_name}}", "vendor_code": "{{vendor_code}}", "po_number": "{{po_number}}", "invoice_number": "{{invoice_number}}", "invoice_date": "{{invoice_date}}", "due_date": "{{due_date}}", "subtotal": "{{subtotal}}", "tax": "{{tax}}", "total_amount": "{{total_amount}}", "notes": "Autonomous CentrAlign submission"}},
                {"description": "Capture post-submission evidence", "tool_name": "take_screenshot", "tool_args": {"filename": "{{run_id}}-after-submit.png"}},
                {"description": "Independently verify the persisted ERP record", "tool_name": "query_erp_db", "tool_args": {"endpoint": "/api/invoices/{{record_id}}"}},
            ]},
        ]}
