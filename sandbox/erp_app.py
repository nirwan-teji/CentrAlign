"""
sandbox/erp_app.py — Mock Enterprise ERP Portal (FastAPI + Jinja2/React)

Simulates a real enterprise accounting system with:
  - Session-based authentication
  - Purchase Orders table (searchable, paginated)
  - Invoice submission form (validation, duplicate detection)
  - Chaos mode flags for testing agent self-healing
  - REST API endpoints for direct query by the verifier tool
"""
from __future__ import annotations

import json
import os
import random
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Cookie, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

DATA_DIR = Path(__file__).parent / "data"
TEMPLATES_DIR = Path(__file__).parent / "templates"
PO_FILE = DATA_DIR / "purchase_orders.json"
INVOICE_DB_FILE = DATA_DIR / "invoices_db.json"

app = FastAPI(title="CentrAlign Mock ERP", version="1.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ── Chaos control ────────────────────────────────────────────────────────────
CHAOS = {
    "network_error_rate": 0.0,   # 0.0 = off, 0.3 = 30% chance of 503
    "validation_error_mode": False,  # force validation rejection once
    "slow_mode": False,              # add 2s delay to simulate slow network
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> list | dict:
    if path.exists():
        return json.loads(path.read_text())
    return []


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


def _chaos_check(response: Response = None):
    """Apply chaos rules before processing requests."""
    if CHAOS["slow_mode"]:
        time.sleep(2)
    if random.random() < CHAOS["network_error_rate"]:
        raise HTTPException(status_code=503, detail="Simulated network error (chaos mode)")


SESSION_STORE: dict[str, str] = {}  # token -> username
VALID_CREDENTIALS = {"admin": "admin123"}


def _get_current_user(session_token: str | None) -> str | None:
    if session_token and session_token in SESSION_STORE:
        return SESSION_STORE[session_token]
    return None


def _require_auth(session_token: str | None) -> str:
    user = _get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, session_token: Optional[str] = Cookie(None)):
    user = _get_current_user(session_token)
    if not user:
        return RedirectResponse("/login")
    return RedirectResponse("/dashboard")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def do_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if VALID_CREDENTIALS.get(username) == password:
        token = str(uuid.uuid4())
        SESSION_STORE[token] = username
        resp = RedirectResponse("/dashboard", status_code=302)
        resp.set_cookie("session_token", token, httponly=True)
        return resp
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "error": "Invalid credentials"},
    )


@app.get("/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    if session_token in SESSION_STORE:
        del SESSION_STORE[session_token]
    resp = RedirectResponse("/login")
    resp.delete_cookie("session_token")
    return resp


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session_token: Optional[str] = Cookie(None)):
    _require_auth(session_token)
    invoices = _load_json(INVOICE_DB_FILE)
    pos = _load_json(PO_FILE)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "invoice_count": len(invoices),
            "po_count": len(pos),
            "pending_count": sum(1 for i in invoices if i.get("status") == "pending"),
        },
    )


# ── Purchase Orders ───────────────────────────────────────────────────────────

@app.get("/purchase-orders", response_class=HTMLResponse)
async def purchase_orders(
    request: Request,
    search: str = "",
    session_token: Optional[str] = Cookie(None),
):
    _require_auth(session_token)
    _chaos_check()
    pos = _load_json(PO_FILE)
    if search:
        search_lower = search.lower()
        pos = [
            p for p in pos
            if search_lower in p["vendor"].lower()
            or search_lower in p["id"].lower()
        ]
    return templates.TemplateResponse(
        request,
        "purchase_orders.html",
        {"request": request, "pos": pos, "search": search},
    )


# ── Invoices ──────────────────────────────────────────────────────────────────

@app.get("/invoices", response_class=HTMLResponse)
async def list_invoices(
    request: Request,
    session_token: Optional[str] = Cookie(None),
):
    _require_auth(session_token)
    invoices = _load_json(INVOICE_DB_FILE)
    return templates.TemplateResponse(
        request,
        "invoices.html",
        {"request": request, "invoices": invoices},
    )


@app.get("/invoices/new", response_class=HTMLResponse)
async def new_invoice_form(
    request: Request,
    session_token: Optional[str] = Cookie(None),
):
    _require_auth(session_token)
    pos = _load_json(PO_FILE)
    return templates.TemplateResponse(
        request,
        "invoice_form.html",
        {"request": request, "pos": pos, "error": None, "success": None},
    )


@app.post("/invoices/new", response_class=HTMLResponse)
async def submit_invoice(
    request: Request,
    vendor_name: str = Form(...),
    vendor_code: str = Form(...),
    po_number: str = Form(...),
    invoice_number: str = Form(...),
    invoice_date: str = Form(...),
    due_date: str = Form(...),
    subtotal: str = Form(...),
    tax: str = Form(...),
    total_amount: str = Form(...),
    notes: str = Form(default=""),
    session_token: Optional[str] = Cookie(None),
):
    _require_auth(session_token)
    _chaos_check()
    pos = _load_json(PO_FILE)

    # ── Chaos: force validation error once ───────────────────────────────────
    if CHAOS["validation_error_mode"]:
        CHAOS["validation_error_mode"] = False  # only fires once
        return templates.TemplateResponse(
            request,
            "invoice_form.html",
            {
                "request": request,
                "pos": pos,
                "error": "CHAOS: Validation rejected. Please resubmit.",
                "success": None,
            },
        )

    # ── Validate total amount ─────────────────────────────────────────────────
    try:
        total = float(total_amount.replace(",", ""))
    except ValueError:
        return templates.TemplateResponse(
            request,
            "invoice_form.html",
            {
                "request": request,
                "pos": pos,
                "error": "Invalid total amount — must be a number.",
                "success": None,
            },
        )

    # ── Validate date format ──────────────────────────────────────────────────
    try:
        datetime.strptime(invoice_date, "%Y-%m-%d")
    except ValueError:
        return templates.TemplateResponse(
            request,
            "invoice_form.html",
            {
                "request": request,
                "pos": pos,
                "error": "Invalid invoice date. Use YYYY-MM-DD format.",
                "success": None,
            },
        )

    # ── Validate PO exists ────────────────────────────────────────────────────
    matching_po = next((p for p in pos if p["id"] == po_number), None)
    if not matching_po:
        return templates.TemplateResponse(
            request,
            "invoice_form.html",
            {
                "request": request,
                "pos": pos,
                "error": f"PO Number {po_number!r} not found in system.",
                "success": None,
            },
        )

    # ── Duplicate check ───────────────────────────────────────────────────────
    invoices = _load_json(INVOICE_DB_FILE)
    if any(i["invoice_number"] == invoice_number for i in invoices):
        return templates.TemplateResponse(
            request,
            "invoice_form.html",
            {
                "request": request,
                "pos": pos,
                "error": f"Invoice {invoice_number!r} already exists (duplicate).",
                "success": None,
            },
        )

    # ── Persist invoice ───────────────────────────────────────────────────────
    record_id = f"INV-DB-{uuid.uuid4().hex[:8].upper()}"
    record = {
        "id": record_id,
        "vendor_name": vendor_name,
        "vendor_code": vendor_code,
        "po_number": po_number,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "subtotal": float(subtotal.replace(",", "")),
        "tax": float(tax.replace(",", "")),
        "total_amount": total,
        "notes": notes,
        "status": "pending",
        "submitted_at": datetime.utcnow().isoformat(),
    }
    invoices.append(record)
    _save_json(INVOICE_DB_FILE, invoices)

    return templates.TemplateResponse(
        request,
        "invoice_form.html",
        {
            "request": request,
            "pos": pos,
            "error": None,
            "success": f"Invoice submitted successfully! Record ID: {record_id}",
            "record_id": record_id,
        },
    )


# ── REST API (used by agent verifier tool) ────────────────────────────────────

@app.get("/api/invoices", response_class=JSONResponse)
async def api_list_invoices(session_token: Optional[str] = Cookie(None)):
    _require_auth(session_token)
    return JSONResponse(_load_json(INVOICE_DB_FILE))


@app.get("/api/invoices/{record_id}", response_class=JSONResponse)
async def api_get_invoice(record_id: str, session_token: Optional[str] = Cookie(None)):
    _require_auth(session_token)
    invoices = _load_json(INVOICE_DB_FILE)
    inv = next((i for i in invoices if i["id"] == record_id), None)
    if not inv:
        raise HTTPException(404, f"Invoice {record_id} not found")
    return JSONResponse(inv)


@app.get("/api/purchase-orders", response_class=JSONResponse)
async def api_list_pos(session_token: Optional[str] = Cookie(None)):
    _require_auth(session_token)
    return JSONResponse(_load_json(PO_FILE))


# ── Chaos control API (test harness) ─────────────────────────────────────────

@app.post("/chaos/set")
async def set_chaos(
    network_error_rate: float = 0.0,
    validation_error_mode: bool = False,
    slow_mode: bool = False,
):
    CHAOS["network_error_rate"] = network_error_rate
    CHAOS["validation_error_mode"] = validation_error_mode
    CHAOS["slow_mode"] = slow_mode
    return {"chaos": CHAOS}


@app.post("/chaos/reset")
async def reset_chaos():
    CHAOS["network_error_rate"] = 0.0
    CHAOS["validation_error_mode"] = False
    CHAOS["slow_mode"] = False
    return {"chaos": CHAOS}


@app.delete("/api/invoices/reset")
async def reset_invoices():
    """Test utility to wipe the invoice DB between test runs."""
    _save_json(INVOICE_DB_FILE, [])
    return {"status": "reset"}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "CentrAlign Mock ERP", "chaos": CHAOS}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sandbox.erp_app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8001")), reload=False)
