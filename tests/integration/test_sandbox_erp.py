from __future__ import annotations

import httpx
import pytest

from sandbox.erp_app import app, reset_chaos, reset_invoices


@pytest.mark.asyncio
async def test_sandbox_login_and_invoice_submission():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://erp") as client:
        await reset_chaos()
        await reset_invoices()
        login = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
        assert login.status_code == 302
        client.cookies.update(login.cookies)
        page = await client.get("/purchase-orders")
        assert page.status_code == 200
        assert "PO-2024-003" in page.text
        submitted = await client.post("/invoices/new", data={
            "vendor_name": "CloudServices Corp", "vendor_code": "CSC003", "po_number": "PO-2024-003",
            "invoice_number": "TEST-INV-1", "invoice_date": "2024-09-25", "due_date": "2024-10-25",
            "subtotal": "3200", "tax": "0", "total_amount": "3200", "notes": "test",
        })
        assert submitted.status_code == 200
        assert "Invoice submitted successfully" in submitted.text
        records = await client.get("/api/invoices")
        assert records.status_code == 200
        assert any(item["invoice_number"] == "TEST-INV-1" for item in records.json())
        await reset_invoices()
