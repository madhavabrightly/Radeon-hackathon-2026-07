"""Browser tools - open, search, click, type, download."""

from __future__ import annotations

import asyncio
import time
from typing import Dict, Any, Optional


DEFAULT_IDLE_TIMEOUT_SEC = 300


class BrowserTools:
    """Browser control tools using Playwright."""

    def __init__(self):
        """Initialize browser tools."""
        self.browser = None
        self.page = None
        self._playwright = None
        self.last_used = 0.0
        self.idle_timeout_sec = DEFAULT_IDLE_TIMEOUT_SEC

    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        await self.unload_idle()
        if self.browser is None:
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                self.browser = await self._playwright.chromium.launch(
                    headless=False
                )
                self.page = await self.browser.new_page()
            except ImportError:
                raise RuntimeError(
                    "Playwright not installed. Run: pip install playwright"
                )
        self.last_used = time.monotonic()

    async def prepare(self) -> Dict[str, Any]:
        """Warm import Playwright without launching Chromium."""
        try:
            await asyncio.to_thread(__import__, "playwright.async_api")
            return {"status": "success", "prepared": "playwright-import"}
        except ImportError:
            return {
                "status": "skipped",
                "reason": "Playwright is not installed",
            }

    async def unload_idle(self) -> None:
        """Close Chromium after idle timeout to free 400MB+ on small machines."""
        if not self.browser:
            return
        if time.monotonic() - self.last_used >= self.idle_timeout_sec:
            await self.close()

    async def open(self, url: str) -> Dict[str, Any]:
        """Open a URL in browser."""
        try:
            await self._ensure_browser()
            await self.page.goto(url)
            self.last_used = time.monotonic()
            return {
                "status": "success",
                "url": url,
                "title": await self.page.title(),
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    async def search(self, query: str, engine: str = "google") -> Dict[str, Any]:
        """Search the web."""
        try:
            await self._ensure_browser()

            if engine == "google":
                url = f"https://www.google.com/search?q={query}"
            elif engine == "bing":
                url = f"https://www.bing.com/search?q={query}"
            elif engine == "duckduckgo":
                url = f"https://duckduckgo.com/?q={query}"
            else:
                url = f"https://www.google.com/search?q={query}"

            await self.page.goto(url)
            self.last_used = time.monotonic()
            return {
                "status": "success",
                "query": query,
                "engine": engine,
                "url": url,
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    async def click(self, selector: str) -> Dict[str, Any]:
        """Click an element by selector."""
        try:
            await self._ensure_browser()
            await self.page.click(selector)
            self.last_used = time.monotonic()
            return {
                "status": "success",
                "selector": selector,
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    async def type(self, selector: str, text: str) -> Dict[str, Any]:
        """Type text into an element."""
        try:
            await self._ensure_browser()
            await self.page.fill(selector, text)
            self.last_used = time.monotonic()
            return {
                "status": "success",
                "selector": selector,
                "text": text,
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    async def read(self, selector: str = "body") -> Dict[str, Any]:
        """Read page content."""
        try:
            await self._ensure_browser()
            content = await self.page.text_content(selector)
            self.last_used = time.monotonic()
            return {
                "status": "success",
                "content": content,
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    async def download(self, url: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """Download a file."""
        try:
            import urllib.request
            from pathlib import Path

            ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
            DOWNLOAD_DIR = ROOT / "ai_pc_operator" / "data" / "downloads"
            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

            if not filename:
                filename = url.split("/")[-1]

            download_path = DOWNLOAD_DIR / filename

            urllib.request.urlretrieve(url, str(download_path))

            return {
                "status": "success",
                "url": url,
                "path": str(download_path),
                "size": download_path.stat().st_size,
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    async def close(self) -> Dict[str, Any]:
        """Close browser."""
        try:
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
                self.browser = None
                self.page = None
                self._playwright = None
                self.last_used = 0.0
            return {"status": "success"}
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }
