"""FastAPI observation console and run-control API."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.evidence import EvidencePackager
from core.engine import AgentEngine
from core.hitl import HITLManager
from core.state import Goal, HITLDecision
from server.events import broker

app = FastAPI(title="CentrAlign Agent Console", version="1.0")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
RUNS: dict[str, Any] = {}
HITL_EVENTS: dict[str, asyncio.Event] = {}
PENDING_APPROVALS: dict[str, asyncio.Future] = {}
PENDING_COMMENTS: dict[str, str | None] = {}


class RunRequest(BaseModel):
    goal: str = Field(min_length=3)
    context: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    decision: HITLDecision
    comment: Optional[str] = None


async def _run_agent(goal: Goal) -> None:
    await broker.publish(goal.id, {"type": "status", "status": "started", "goal": goal.raw_text})
    async def emit(event):
        await broker.publish(goal.id, event)
    async def approval_handler(request):
        future = asyncio.get_running_loop().create_future()
        PENDING_APPROVALS[goal.id] = future
        await broker.publish(goal.id, {"type": "approval_required", "request": request.model_dump(mode="json")})
        try:
            decision = await future
            request.human_comment = PENDING_COMMENTS.get(goal.id)
            return decision
        finally:
            PENDING_APPROVALS.pop(goal.id, None)
            PENDING_COMMENTS.pop(goal.id, None)
    trace = await AgentEngine(event_sink=emit, hitl=HITLManager(handler=approval_handler)).run(goal)
    evidence = EvidencePackager().package(trace)
    RUNS[goal.id] = {"trace": trace, "evidence": evidence}
    await broker.publish(goal.id, {"type": "complete", "status": trace.agent_status.value, "verification": trace.verification.model_dump(mode="json") if trace.verification else None, "evidence": evidence})


@app.get("/", response_class=FileResponse)
async def dashboard() -> str:
    return str(STATIC_DIR / "index.html")


@app.post("/api/runs", status_code=202)
async def create_run(payload: RunRequest):
    goal = Goal(raw_text=payload.goal, context=payload.context)
    RUNS[goal.id] = {"trace": None, "evidence": None}
    asyncio.create_task(_run_agent(goal))
    return {"run_id": goal.id, "status": "started"}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404, "Run not found")
    item = RUNS[run_id]
    return {"run_id": run_id, "status": item["trace"].agent_status.value if item["trace"] else "running", "evidence": item["evidence"]}


@app.get("/api/runs/{run_id}/artifacts/{filename}")
async def get_artifact(run_id: str, filename: str):
    item = RUNS.get(run_id)
    if not item or not item.get("evidence") or filename not in {"evidence_package.json", "audit_summary.md"}:
        raise HTTPException(404, "Artifact not found")
    path = Path(item["evidence"]["directory"]) / filename
    if not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path)


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404, "Run not found")

    async def stream():
        async for event in broker.subscribe(run_id):
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event.get("type") == "complete":
                break

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/runs/{run_id}/approval")
async def resolve_approval(run_id: str, payload: ApprovalRequest):
    if run_id not in RUNS:
        raise HTTPException(404, "Run not found")
    await broker.publish(run_id, {"type": "approval", "decision": payload.decision.value, "comment": payload.comment})
    pending = PENDING_APPROVALS.get(run_id)
    if pending and not pending.done():
        PENDING_COMMENTS[run_id] = payload.comment
        pending.set_result(payload.decision)
    return {"run_id": run_id, "decision": payload.decision.value}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "CentrAlign Agent Console"}
