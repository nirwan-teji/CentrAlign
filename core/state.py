"""
core/state.py — Canonical Pydantic v2 data models for the entire agent lifecycle.

Every message passed between components is one of these types, giving us
type safety, automatic validation, and clean serialisation to JSON for
evidence packages and audit logs.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enumerations ────────────────────────────────────────────────────────────

class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class AgentStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    ADAPTING = "adapting"
    WAITING_HITL = "waiting_hitl"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolResultStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class HITLDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    GUIDANCE = "guidance"
    PENDING = "pending"


# ── Core data models ─────────────────────────────────────────────────────────

class Goal(BaseModel):
    """The top-level objective provided by the user in natural language."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    context: Dict[str, Any] = Field(default_factory=dict)


class ActionStep(BaseModel):
    """A single concrete action within a plan milestone."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    requires_hitl: bool = False
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class Milestone(BaseModel):
    """A logical grouping of ActionSteps representing one phase of the plan."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    steps: List[ActionStep] = Field(default_factory=list)
    status: StepStatus = StepStatus.PENDING


class TaskPlan(BaseModel):
    """The complete structured plan for achieving a Goal."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal_id: str
    milestones: List[Milestone] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1  # incremented on replanning

    @property
    def total_steps(self) -> int:
        return sum(len(m.steps) for m in self.milestones)

    @property
    def completed_steps(self) -> int:
        return sum(
            1
            for m in self.milestones
            for s in m.steps
            if s.status == StepStatus.COMPLETED
        )

    @property
    def progress_pct(self) -> float:
        total = self.total_steps
        return (self.completed_steps / total * 100) if total > 0 else 0.0


class ToolResult(BaseModel):
    """Structured output from any tool execution."""
    tool_name: str
    status: ToolResultStatus
    data: Any = None           # main payload (text, dict, list, …)
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None  # for browser tools
    metadata: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: Optional[float] = None


class Observation(BaseModel):
    """The agent's interpretation of a ToolResult."""
    step_id: str
    tool_result: ToolResult
    facts_extracted: Dict[str, Any] = Field(default_factory=dict)
    success: bool
    next_action_hint: Optional[str] = None  # planner hint from observer
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HITLRequest(BaseModel):
    """Payload sent to a human when the agent cannot safely proceed."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reason: str
    context_summary: str
    options: List[str] = Field(default_factory=lambda: ["Approve", "Reject"])
    relevant_data: Dict[str, Any] = Field(default_factory=dict)
    decision: HITLDecision = HITLDecision.PENDING
    human_comment: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VerificationResult(BaseModel):
    """Independent outcome check performed after all steps complete."""
    passed: bool
    evidence: Dict[str, Any] = Field(default_factory=dict)
    screenshot_path: Optional[str] = None
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    failure_reason: Optional[str] = None


class ExecutionTrace(BaseModel):
    """Full end-to-end record of a single agent run — the audit log."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: Goal
    plan: Optional[TaskPlan] = None
    observations: List[Observation] = Field(default_factory=list)
    hitl_requests: List[HITLRequest] = Field(default_factory=list)
    verification: Optional[VerificationResult] = None
    agent_status: AgentStatus = AgentStatus.IDLE
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    working_memory: Dict[str, Any] = Field(default_factory=dict)

    def to_evidence_dict(self) -> Dict[str, Any]:
        """Serialise to a clean dict for the audit evidence package."""
        return self.model_dump(mode="json")
