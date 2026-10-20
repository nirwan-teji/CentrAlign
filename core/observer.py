"""Interpret tool results and retain useful facts for the next action."""
from __future__ import annotations

import json
from typing import Any, Dict

from core.state import Observation, ActionStep, ToolResult, ToolResultStatus
from memory.working_memory import WorkingMemory


class Observer:
    def __init__(self, memory: WorkingMemory | None = None) -> None:
        self.memory = memory or WorkingMemory()

    def observe(self, step: ActionStep, result: ToolResult) -> Observation:
        facts = self._facts(result.data)
        if result.error_message:
            facts["last_error"] = result.error_message
        self.memory.update(facts)
        self.memory.record_action(result.tool_name, self._summary(result))
        return Observation(
            step_id=step.id,
            tool_result=result,
            facts_extracted=facts,
            success=result.status in (ToolResultStatus.SUCCESS, ToolResultStatus.PARTIAL),
            next_action_hint=self._hint(result),
        )

    @staticmethod
    def _facts(data: Any) -> Dict[str, Any]:
        if data is None:
            return {}
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, (str, int, float, bool, list, dict))}
        return {"last_output": data}

    @staticmethod
    def _summary(result: ToolResult) -> str:
        if result.error_message:
            return f"ERROR: {result.error_message}"
        payload = json.dumps(result.data, default=str)[:240]
        return payload

    @staticmethod
    def _hint(result: ToolResult) -> str | None:
        return result.error_message if result.status == ToolResultStatus.ERROR else None
