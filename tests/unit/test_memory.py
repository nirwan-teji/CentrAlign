from __future__ import annotations

from memory.working_memory import WorkingMemory
from memory.company_context import CompanyPolicy


def test_working_memory_tracks_facts_and_bounded_history():
    memory = WorkingMemory()
    memory.update({"invoice_id": "INV-1", "total": 6200})
    memory.record_action("read_file", "parsed invoice")
    assert memory.get("invoice_id") == "INV-1"
    assert "read_file" in memory.history_summary()


def test_company_policy_requires_high_value_approval():
    decision = CompanyPolicy().evaluate("submit_invoice", {"total_amount": 6201})
    assert decision.requires_approval


def test_company_policy_requires_new_vendor_approval():
    decision = CompanyPolicy().evaluate("submit_invoice", {}, {"new_vendor": True})
    assert decision.requires_approval
