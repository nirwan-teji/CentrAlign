"""
tools/__init__.py — Registers all tools into the global registry at import time.
"""
from tools.registry import registry
from tools.browser.browser_tool import (
    NavigateTool, ClickTool, TypeTextTool, SelectOptionTool,
    ExtractTextTool, TakeScreenshotTool, GetDomTool, QueryERPDbTool, SubmitInvoiceTool,
)
from tools.filesystem.file_tool import ReadFileTool, ListFilesTool, FindLatestInvoiceTool, ParseInvoiceTool, LookupPurchaseOrderTool
from tools.system.calculator import CalculateTool, ReconcileTool

def register_all_tools() -> None:
    """Call this once at agent startup to populate the tool registry."""
    for tool_cls in [
        NavigateTool, ClickTool, TypeTextTool, SelectOptionTool,
        ExtractTextTool, TakeScreenshotTool, GetDomTool, QueryERPDbTool, SubmitInvoiceTool,
        ReadFileTool, ListFilesTool,
        FindLatestInvoiceTool, ParseInvoiceTool, LookupPurchaseOrderTool,
        CalculateTool, ReconcileTool,
    ]:
        registry.register(tool_cls())
