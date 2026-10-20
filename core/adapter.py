"""Bounded failure recovery for tool actions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.state import ActionStep, ToolResult


@dataclass
class RecoveryDecision:
    strategy: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    reason: str = ""


class Adapter:
    def __init__(self, max_retries: int = 2) -> None:
        self.max_retries = max_retries

    def recover(self, step: ActionStep, result: ToolResult) -> RecoveryDecision:
        error = (result.error_message or "").lower()
        if step.retry_count >= self.max_retries:
            return RecoveryDecision("replan", reason="retry budget exhausted")
        # ERP returns validation errors in the rendered page. Retrying is safe
        # because the endpoint is duplicate-protected and chaos errors are one-shot.
        if "invalid invoice date" in error:
            date_value = step.tool_args.get("invoice_date")
            if isinstance(date_value, str):
                for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        corrected = datetime.strptime(date_value, fmt).strftime("%Y-%m-%d")
                        return RecoveryDecision("adjust_args", tool_args={**step.tool_args, "invoice_date": corrected}, reason="normalized ERP date format")
                    except ValueError:
                        continue
        if "validation" in error or "network" in error or "timeout" in error:
            return RecoveryDecision("retry_same", reason="transient or correctable validation failure")
        if "not found" in error and step.tool_name == "click":
            return RecoveryDecision("retry_same", reason="DOM may still be settling")
        return RecoveryDecision("replan", reason="unclassified tool failure")
