"""Rich terminal runner for a single CentrAlign task."""
from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console
from rich.table import Table

from core.engine import AgentEngine
from core.evidence import EvidencePackager
from core.state import Goal

app = typer.Typer(help="Run CentrAlign autonomous workflows")
console = Console()


@app.command()
def run(goal: str = typer.Argument(..., help="Natural-language business goal")) -> None:
    """Execute a goal and print its verification and audit evidence."""
    trace = asyncio.run(AgentEngine().run(Goal(raw_text=goal)))
    table = Table(title="CentrAlign execution")
    table.add_column("Field"); table.add_column("Value")
    table.add_row("Status", trace.agent_status.value)
    table.add_row("Steps", f"{trace.plan.completed_steps if trace.plan else 0}/{trace.plan.total_steps if trace.plan else 0}")
    table.add_row("Verification", str(trace.verification.passed if trace.verification else False))
    console.print(table)
    paths = EvidencePackager().package(trace)
    console.print(f"Audit package: {paths['directory']}")
    if trace.error:
        console.print(f"[red]{trace.error}[/red]")


if __name__ == "__main__":
    app()
