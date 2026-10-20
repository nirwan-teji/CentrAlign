"""Audit evidence pack generation for completed and failed runs."""
from __future__ import annotations

import json
from pathlib import Path

from core.config import settings
from core.state import ExecutionTrace


class EvidencePackager:
    def __init__(self, output_dir: str | None = None) -> None:
        self.output_dir = Path(output_dir or settings.evidence_dir)

    def package(self, trace: ExecutionTrace, run_id: str | None = None) -> dict[str, str]:
        run_id = run_id or trace.id
        destination = self.output_dir / run_id
        destination.mkdir(parents=True, exist_ok=True)
        json_path = destination / "evidence_package.json"
        json_path.write_text(json.dumps(trace.to_evidence_dict(), indent=2, default=str), encoding="utf-8")
        summary_path = destination / "audit_summary.md"
        summary_path.write_text(self._markdown(trace), encoding="utf-8")
        return {"directory": str(destination), "json": str(json_path), "summary": str(summary_path)}

    @staticmethod
    def _markdown(trace: ExecutionTrace) -> str:
        verdict = trace.verification.passed if trace.verification else False
        lines = [
            "# CentrAlign Audit Summary", "",
            f"- Run ID: `{trace.id}`",
            f"- Goal: {trace.goal.raw_text}",
            f"- Status: **{trace.agent_status.value}**",
            f"- Verification: **{'PASSED' if verdict else 'FAILED'}**", "",
            "## Execution timeline", "",
        ]
        for observation in trace.observations:
            status = "OK" if observation.success else "ERROR"
            lines.append(f"- `{observation.timestamp.isoformat()}` `{observation.tool_result.tool_name}` — {status}")
        if trace.verification:
            lines.extend(["", "## Verification evidence", "", "```json", json.dumps(trace.verification.evidence, indent=2, default=str), "```"])
            if trace.verification.failure_reason:
                lines.append(f"\nFailure reason: {trace.verification.failure_reason}")
        return "\n".join(lines) + "\n"
