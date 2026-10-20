"""
tools/filesystem/file_tool.py — Safe file reader supporting TXT, CSV, and PDF.
"""
from __future__ import annotations

import csv
import io
import logging
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.state import ToolResult, ToolResultStatus
from tools.base import BaseTool

logger = logging.getLogger(__name__)

SAFE_EXTENSIONS = {".txt", ".csv", ".pdf", ".json", ".md"}


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the text content of a TXT, CSV, PDF, or JSON file safely."
    timeout_seconds = 15

    async def _run(self, path: str, max_chars: int = 8000) -> ToolResult:
        fp = Path(path)
        if not fp.exists():
            return ToolResult(
                tool_name=self.name, status=ToolResultStatus.ERROR,
                error_message=f"File not found: {path}",
            )
        if fp.suffix.lower() not in SAFE_EXTENSIONS:
            return ToolResult(
                tool_name=self.name, status=ToolResultStatus.ERROR,
                error_message=f"Unsupported file type: {fp.suffix}",
            )

        try:
            content = _read_file(fp, max_chars)
            return ToolResult(
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={"path": str(fp), "content": content, "size_bytes": fp.stat().st_size},
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name, status=ToolResultStatus.ERROR, error_message=str(exc),
            )


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files in a directory, optionally filtered by extension."
    timeout_seconds = 5

    async def _run(self, directory: str, extension: Optional[str] = None) -> ToolResult:
        dp = Path(directory)
        if not dp.exists():
            return ToolResult(
                tool_name=self.name, status=ToolResultStatus.ERROR,
                error_message=f"Directory not found: {directory}",
            )
        try:
            files = []
            for f in sorted(dp.iterdir()):
                if f.is_file() and (extension is None or f.suffix.lower() == extension.lower()):
                    files.append({"name": f.name, "path": str(f), "size_bytes": f.stat().st_size, "extension": f.suffix})
            return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS,
                              data={"directory": str(dp), "files": files, "count": len(files)})
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=str(exc))


class FindLatestInvoiceTool(BaseTool):
    name = "find_latest_invoice"
    description = "Find the newest invoice file in a directory by invoice date, falling back to modification time."
    timeout_seconds = 5

    async def _run(self, directory: str) -> ToolResult:
        dp = Path(directory)
        candidates = [p for p in dp.iterdir() if p.is_file() and p.suffix.lower() in {".txt", ".pdf", ".csv"} and "invoice" in p.name.lower()]
        if not candidates:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=f"No invoice files found in {directory}")
        def sort_key(path: Path):
            try:
                if path.suffix.lower() == ".csv":
                    row = next(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
                    date_value = row.get("Invoice Date") or row.get("Date")
                    if date_value:
                        return datetime.strptime(date_value.strip(), "%Y-%m-%d")
                text = _read_file(path, 12000)
                match = re.search(r"(?:Invoice Date|Date)\s*:\s*(\d{4}-\d{2}-\d{2})", text, re.I)
                return datetime.strptime(match.group(1), "%Y-%m-%d") if match else datetime.fromtimestamp(path.stat().st_mtime)
            except Exception:
                return datetime.fromtimestamp(path.stat().st_mtime)
        latest = max(candidates, key=sort_key)
        return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS, data={"latest_path": str(latest), "count": len(candidates)})


class ParseInvoiceTool(BaseTool):
    name = "parse_invoice"
    description = "Extract structured vendor, invoice, date, PO, line-item, tax, and total fields from an invoice file."
    timeout_seconds = 15

    async def _run(self, path: str) -> ToolResult:
        fp = Path(path)
        if not fp.exists():
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=f"File not found: {path}")
        try:
            text = _read_file(fp, 30000)
            if fp.suffix.lower() == ".csv":
                row = next(csv.DictReader(fp.read_text(encoding="utf-8-sig").splitlines()))
                text = "\n".join(f"{key}: {value}" for key, value in row.items())
            def field(pattern: str, default: str = "") -> str:
                match = re.search(pattern, text, re.I | re.M)
                return match.group(1).strip() if match else default
            vendor = field(r"^\s*(?:FROM:|Vendor Name:)\s*\n?\s*([^\n]+)")
            if vendor.upper() == "FROM:":
                vendor = field(r"FROM:\s*\n\s*([^\n]+)")
            values = {
                "source_path": str(fp),
                "vendor_name": vendor,
                "vendor_code": field(r"Vendor Code:\s*([A-Z0-9-]+)"),
                "invoice_number": field(r"Invoice Number:\s*([^\n]+)"),
                "invoice_date": field(r"(?:Invoice )?Date:\s*(\d{4}-\d{2}-\d{2})"),
                "due_date": field(r"Due Date:\s*(\d{4}-\d{2}-\d{2})"),
                "po_number": field(r"(?:REFERENCE|PO Number):\s*([A-Z0-9-]+)"),
                "subtotal": _money(field(r"SUBTOTAL:\s*\$?([\d,]+(?:\.\d{2})?)")),
                "tax": _money(field(r"^\s*TAX(?:\s*\([^)]*\))?:\s*\$?([\d,]+(?:\.\d{2})?)")),
                "total_amount": _money(field(r"(?:TOTAL DUE|TOTAL AMOUNT|TOTAL):\s*\$?([\d,]+(?:\.\d{2})?)")),
            }
            missing = [key for key in ("vendor_name", "invoice_number", "invoice_date", "po_number", "total_amount") if not values[key]]
            if missing:
                return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=f"Could not extract invoice fields: {', '.join(missing)}")
            values["line_items"] = [line.strip() for line in text.splitlines() if re.search(r"\d[,.]\d{2}", line)][:10]
            return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS, data=values)
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=str(exc))


class LookupPurchaseOrderTool(BaseTool):
    name = "lookup_purchase_order"
    description = "Look up a purchase order by ID from the local company purchase-order registry."
    timeout_seconds = 5

    async def _run(self, path: str, po_number: str) -> ToolResult:
        try:
            records = json.loads(Path(path).read_text(encoding="utf-8"))
            record = next((item for item in records if item.get("id") == po_number), None)
            if not record:
                return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=f"Purchase order {po_number!r} not found")
            return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS, data={"po_total": record["total_amount"], "po_vendor": record["vendor"], "po": record})
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=str(exc))


def _money(value: str) -> float:
    return float(value.replace(",", "")) if value else 0.0


def _read_file(fp: Path, max_chars: int) -> str:
    suffix = fp.suffix.lower()

    if suffix == ".pdf":
        return _read_pdf(fp, max_chars)

    if suffix == ".csv":
        return _read_csv(fp, max_chars)

    # TXT, JSON, MD — plain text read
    text = fp.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars]


def _read_pdf(fp: Path, max_chars: int) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(fp))
        pages_text = []
        for page in reader.pages:
            pages_text.append(page.extract_text() or "")
        text = "\n".join(pages_text)
        return text[:max_chars]
    except ImportError:
        raise RuntimeError("pypdf is not installed. Run: pip install pypdf")


def _read_csv(fp: Path, max_chars: int) -> str:
    raw = fp.read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    lines = []
    for row in reader:
        lines.append(str(dict(row)))
    return "\n".join(lines)[:max_chars]
