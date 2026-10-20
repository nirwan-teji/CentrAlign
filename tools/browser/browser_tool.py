"""
tools/browser/browser_tool.py — Async Playwright browser automation tool.

Provides navigate, click, type_text, select_option, extract_text,
take_screenshot, and get_dom actions. Follows smart waiting strategies
to avoid race conditions on dynamic pages.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from core.config import settings
from core.state import ToolResult, ToolResultStatus
from tools.base import BaseTool
from tools.browser.dom_parser import parse_dom

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        PlaywrightContextManager,
        TimeoutError as PWTimeout,
    )
    _PW_AVAILABLE = True
except ImportError:
    _PW_AVAILABLE = False
    logger.warning("Playwright not installed. Browser tools will not function.")


class BrowserManager:
    """
    Singleton that manages the Playwright browser lifecycle.
    Call `start()` once at agent startup, `stop()` at shutdown.
    """

    def __init__(self) -> None:
        self._pw: Optional[PlaywrightContextManager] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self, headless: bool = True) -> None:
        if not _PW_AVAILABLE:
            raise RuntimeError("playwright is not installed.")
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 CentrAlign-Agent/1.0"
            ),
        )
        self._page = await self._context.new_page()
        logger.info("Browser started (headless=%s)", headless)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._page = self._context = self._browser = self._pw = None
        logger.info("Browser stopped")

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call BrowserManager.start() first.")
        return self._page


browser_manager = BrowserManager()


class NavigateTool(BaseTool):
    name = "navigate"
    description = "Navigate the browser to a URL."
    timeout_seconds = 30

    async def _run(self, url: str, wait_until: str = "domcontentloaded") -> ToolResult:
        try:
            response = await browser_manager.page.goto(url, wait_until=wait_until, timeout=25000)
            status = response.status if response else 0
            title = await browser_manager.page.title()
            return ToolResult(
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={"url": url, "status_code": status, "page_title": title},
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=str(exc))


class ClickTool(BaseTool):
    name = "click"
    description = "Click an element by CSS selector, text content, or ID."
    timeout_seconds = 15

    async def _run(self, selector: str) -> ToolResult:
        page = browser_manager.page
        try:
            # Try direct selector first
            try:
                await page.locator(selector).click(timeout=8000)
            except Exception:
                # Fallback: click by visible text
                await page.get_by_text(selector, exact=False).first.click(timeout=8000)
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
            return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS,
                              data={"clicked": selector})
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR,
                              error_message=str(exc))


class TypeTextTool(BaseTool):
    name = "type_text"
    description = "Type text into an input field identified by CSS selector."
    timeout_seconds = 10

    async def _run(self, selector: str, text: str, clear_first: bool = True) -> ToolResult:
        page = browser_manager.page
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=8000)
            if clear_first:
                await locator.clear()
            await locator.fill(text)
            return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS,
                              data={"selector": selector, "text": text})
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR,
                              error_message=str(exc))


class SelectOptionTool(BaseTool):
    name = "select_option"
    description = "Select a dropdown option by value."
    timeout_seconds = 10

    async def _run(self, selector: str, value: str) -> ToolResult:
        page = browser_manager.page
        try:
            await page.locator(selector).select_option(value=value, timeout=8000)
            return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS,
                              data={"selector": selector, "value": value})
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR,
                              error_message=str(exc))


class ExtractTextTool(BaseTool):
    name = "extract_text"
    description = "Extract visible text and interactive elements from the current page."
    timeout_seconds = 15

    async def _run(self, selector: Optional[str] = None) -> ToolResult:
        page = browser_manager.page
        try:
            if selector:
                el = page.locator(selector).first
                text = await el.inner_text(timeout=8000)
            else:
                html = await page.content()
                text = parse_dom(html)
            return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS,
                              data={"content": text})
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR,
                              error_message=str(exc))


class TakeScreenshotTool(BaseTool):
    name = "take_screenshot"
    description = "Capture a PNG screenshot of the current browser viewport."
    timeout_seconds = 10

    async def _run(self, filename: str = "screenshot.png") -> ToolResult:
        page = browser_manager.page
        try:
            path = Path(settings.screenshots_dir) / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(path), full_page=False)
            return ToolResult(
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={"path": str(path)},
                screenshot_path=str(path),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR,
                              error_message=str(exc))


class GetDomTool(BaseTool):
    name = "get_dom"
    description = "Get the compact DOM snapshot of the current page for LLM reasoning."
    timeout_seconds = 10

    async def _run(self) -> ToolResult:
        page = browser_manager.page
        try:
            html = await page.content()
            dom = parse_dom(html)
            return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS, data={"dom": dom})
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=str(exc))


class SubmitInvoiceTool(BaseTool):
    name = "submit_invoice"
    description = "Fill and submit the currently open ERP invoice form, returning the persisted record ID or validation error."
    timeout_seconds = 30

    async def _run(self, **fields: str) -> ToolResult:
        try:
            page = browser_manager.page
            for name, value in fields.items():
                if name == "notes":
                    continue
                locator = page.locator(f"#{name}")
                if await locator.evaluate("el => el.tagName.toLowerCase()") == "select":
                    await locator.select_option(str(value))
                else:
                    await locator.fill(str(value))
            if fields.get("notes") is not None:
                await page.locator("#notes").fill(str(fields["notes"]))
            await page.locator("#submit-invoice-btn").click()
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            error = page.locator("#form-error")
            if await error.count():
                return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=await error.inner_text())
            success = page.locator("#form-success")
            record = page.locator("#record-id")
            if not await success.count() or not await record.count():
                return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message="ERP did not show a submission confirmation")
            return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS,
                              data={"record_id": (await record.inner_text()).strip(), "confirmation": (await success.inner_text()).strip()})
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=str(exc))


class QueryERPDbTool(BaseTool):
    """Directly query the ERP REST API — used by the verifier for independent DB checks."""
    name = "query_erp_db"
    description = "Query the ERP API to verify a record exists (returns record JSON)."
    timeout_seconds = 15

    async def _run(self, endpoint: str) -> ToolResult:
        import httpx
        try:
            # Use the session cookie that should already exist in browser context
            cookies = await browser_manager.page.context.cookies()
            session_token = next((c["value"] for c in cookies if c["name"] == "session_token"), None)
            headers = {}
            cookie_header = f"session_token={session_token}" if session_token else ""
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.sandbox_erp_url}{endpoint}",
                    headers={"Cookie": cookie_header} if cookie_header else {},
                )
            if resp.status_code == 200:
                return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS,
                                  data=resp.json())
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR,
                              error_message=f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message=str(exc))
