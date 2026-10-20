"""
tools/system/calculator.py — Deterministic arithmetic tool.

Prevents LLM math hallucinations for tax, totals, and reconciliation checks.
"""
from __future__ import annotations

import ast
import logging
import operator
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from core.state import ToolResult, ToolResultStatus
from tools.base import BaseTool

logger = logging.getLogger(__name__)

# Whitelist safe AST node types for the expression evaluator
_SAFE_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
    ast.USub, ast.UAdd, ast.Num, ast.Constant,
}
_SAFE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}


def _safe_eval(expr: str) -> float:
    """Evaluate a pure arithmetic expression safely (no builtins, no imports)."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression syntax: {exc}") from exc

    for node in ast.walk(tree):
        if type(node) not in _SAFE_NODES:
            raise ValueError(f"Unsafe expression node: {type(node).__name__}")

    def _eval(node: Any) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Num):  # Python 3.7 compat
            return float(node.n)
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            fn = _SAFE_OPS.get(type(node.op))
            if fn is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return fn(left, right)
        if isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        raise ValueError(f"Unsupported node: {type(node).__name__}")

    return _eval(tree)


def _round2(v: float) -> float:
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class CalculateTool(BaseTool):
    name = "calculate"
    description = (
        "Evaluate a safe arithmetic expression and return the numeric result. "
        "Use for invoice total verification, tax calculation, and reconciliation checks."
    )
    timeout_seconds = 5

    async def _run(self, expression: str) -> ToolResult:
        try:
            result = _safe_eval(expression)
            rounded = _round2(result)
            return ToolResult(
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={"expression": expression, "result": rounded},
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error_message=str(exc),
            )


class ReconcileTool(BaseTool):
    name = "reconcile"
    description = (
        "Compare an invoice total against a PO expected amount. "
        "Returns match status and discrepancy amount."
    )
    timeout_seconds = 5

    async def _run(
        self,
        invoice_total: float,
        po_total: float,
        tolerance: float = 0.01,
    ) -> ToolResult:
        invoice_total = float(invoice_total)
        po_total = float(po_total)
        tolerance = float(tolerance)
        diff = abs(invoice_total - po_total)
        matched = diff <= tolerance
        return ToolResult(
            tool_name=self.name,
            status=ToolResultStatus.SUCCESS,
            data={
                "invoice_total": _round2(invoice_total),
                "po_total": _round2(po_total),
                "discrepancy": _round2(diff),
                "matched": matched,
                "tolerance": tolerance,
            },
        )
