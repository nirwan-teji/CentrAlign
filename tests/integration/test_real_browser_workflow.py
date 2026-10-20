"""Opt-in real Playwright smoke test for the local ERP workflow.

Run with RUN_BROWSER_E2E=1 after installing Chromium and starting no other ERP
process. The default suite remains hermetic and does not require a browser.
"""
from __future__ import annotations

import os

import httpx
import pytest

from core.engine import AgentEngine
from core.planner import Planner
from core.state import Goal
from core.hitl import HITLManager
from core.state import HITLDecision
from tools import register_all_tools
from tools.registry import registry


class OfflineLLM:
    async def complete_json(self, **kwargs):
        raise RuntimeError("offline real-workflow test")


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("RUN_BROWSER_E2E"), reason="opt-in real browser test")
async def test_real_invoice_workflow_against_local_erp():
    register_all_tools()
    async with httpx.AsyncClient() as client:
        await client.post("http://localhost:8001/chaos/set", params={"validation_error_mode": "true"})
    async def approve(_request):
        return HITLDecision.APPROVED
    trace = await AgentEngine(planner=Planner(llm=OfflineLLM()), hitl=HITLManager(approve)).run(
        Goal(raw_text="Find the latest invoice, reconcile it against its purchase order, and submit it to the ERP.")
    )
    assert trace.agent_status.value == "completed", trace.error
    assert trace.verification and trace.verification.passed
    assert trace.verification.evidence.get("database_confirmation")
    assert trace.verification.evidence.get("screenshots")
    assert any((not observation.success) and "validation" in (observation.tool_result.error_message or "").lower() for observation in trace.observations)
    async with httpx.AsyncClient() as client:
        await client.post("http://localhost:8001/chaos/reset")
