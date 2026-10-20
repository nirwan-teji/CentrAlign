"""Company policies and safety rules used before executing risky actions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config import settings


@dataclass(frozen=True)
class PolicyDecision:
    requires_approval: bool
    reason: str = ""
    options: tuple[str, ...] = ("Approve", "Reject", "Provide correction")


class CompanyPolicy:
    def evaluate(self, tool_name: str | None, args: dict[str, Any], facts: dict[str, Any] | None = None) -> PolicyDecision:
        facts = facts or {}
        for key, value in args.items():
            if "amount" in key.lower() or "total" in key.lower():
                try:
                    if float(str(value).replace(",", "")) > settings.hitl_amount_threshold:
                        return PolicyDecision(True, f"Amount exceeds ${settings.hitl_amount_threshold:,.2f} approval threshold.")
                except (TypeError, ValueError):
                    pass
        if facts.get("new_vendor") is True:
            return PolicyDecision(True, "Vendor is not present in the approved vendor context.")
        return PolicyDecision(False)


company_policy = CompanyPolicy()
