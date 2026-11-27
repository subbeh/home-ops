"""Crawl4ai extract provider — self-hosted, Bearer token auth."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List

import httpx
from agent.web_search_provider import WebSearchProvider
from tools.url_safety import is_safe_url

logger = logging.getLogger(__name__)

# /md fixes its CrawlerRunConfig, so reads go through /crawl to turn on stealth. The server
# refuses magic, simulate_user and override_navigator from a request body; its config.yml
# base_config already sets simulate_user.
_CRAWL_CONFIG = {
    "browser_config": {"type": "BrowserConfig", "params": {"enable_stealth": True}},
    "crawler_config": {"type": "CrawlerRunConfig", "params": {"wait_until": "load"}},
}


def _crawl4ai_url() -> str:
    """Return CRAWL4AI_URL from config.yaml, then Hermes env, then process env."""
    # 1. Check config.yaml web.crawl4ai_url
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        val = cfg.get("web", {}).get("crawl4ai_url", "").strip()
        if val:
            return val.rstrip("/")
    except Exception:
        pass
    
    # 2. Fallback to Hermes config-aware env (get_env_value checks .env files)
    try:
        from hermes_cli.config import get_env_value
        val = get_env_value("CRAWL4AI_URL")
    except Exception:
        val = None
    if val is None:
        val = os.getenv("CRAWL4AI_URL", "")
    return (val or "").strip().rstrip("/")


def _crawl4ai_token() -> str:
    """Return CRAWL4AI_API_TOKEN from Hermes config-aware env, falling back to process env."""
    try:
        from hermes_cli.config import get_env_value
        val = get_env_value("CRAWL4AI_API_TOKEN")
    except Exception:
        val = None
    if val is None:
        val = os.getenv("CRAWL4AI_API_TOKEN", "")
    return (val or "").strip()


class Crawl4aiWebExtractProvider(WebSearchProvider):
    """Crawl4ai extraction provider using /crawl, with one Tavily retry for a blocked read."""

    @property
    def name(self) -> str:
        return "crawl4ai"

    @property
    def display_name(self) -> str:
        return "Crawl4ai (self-hosted)"

    def is_available(self) -> bool:
        return bool(_crawl4ai_url() and _crawl4ai_token())

    def supports_search(self) -> bool:
        return False  # Use SearXNG for search

    def supports_extract(self) -> bool:
        return True

    async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        format = kwargs.get("format", "markdown")
        results: List[Dict[str, Any]] = []

        base_url = _crawl4ai_url()
        token = _crawl4ai_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            for url in urls:
                # SSRF check
                if not is_safe_url(url):
                    results.append({
                        "url": url,
                        "title": "",
                        "content": "",
                        "error": "Blocked: URL targets a private or internal network address",
                    })
                    continue

                try:
                    logger.info("Crawl4ai extracting: %s", url)
                    response = await client.post(
                        f"{base_url}/crawl",
                        json={"urls": [url], **_CRAWL_CONFIG},
                        headers=headers,
                    )
                    response.raise_for_status()
                    # A blocked page is HTTP 200 with success false and the block in error_message.
                    data = (response.json().get("results") or [{}])[0]
                    if not data.get("success"):
                        reason = data.get("error_message") or "crawl failed"
                        results.append(await self._tavily_retry(url, f"Crawl4ai: {reason}"))
                        continue

                    markdown = data.get("markdown", "")
                    if isinstance(markdown, dict):
                        markdown = markdown.get("raw_markdown", "") or markdown.get("markdown", "")

                    title = self._extract_title(markdown, url)

                    results.append({
                        "url": url,
                        "title": title,
                        "content": markdown,
                        "raw_content": markdown,
                        "metadata": {},
                    })

                except httpx.HTTPStatusError as e:
                    logger.warning("Crawl4ai HTTP error for %s: %s", url, e)
                    status = e.response.status_code
                    reason = f"Crawl4ai HTTP {status}: {e.response.text[:200]}"
                    # A 401 or 400 is this plugin's own fault, so retrying would spend a credit on every read.
                    if status >= 500 or status in (403, 429):
                        results.append(await self._tavily_retry(url, reason))
                    else:
                        results.append({"url": url, "title": "", "content": "", "error": reason})
                except Exception as e:  # noqa: BLE001
                    logger.warning("Crawl4ai extraction error for %s: %s", url, e)
                    results.append({
                        "url": url,
                        "title": "",
                        "content": "",
                        "error": f"Crawl4ai extraction failed: {e}",
                    })

        return results

    async def _tavily_retry(self, url: str, reason: str) -> Dict[str, Any]:
        """Read a page crawl4ai couldn't through Hermes's Tavily provider, so credits go only on blocks."""
        logger.info("Crawl4ai blocked on %s (%s), retrying through Tavily", url, reason)
        # Raised here, inside the caller's except handler, an error would fail the whole batch.
        try:
            from plugins.web.tavily.provider import TavilyWebSearchProvider

            page = (await asyncio.to_thread(TavilyWebSearchProvider().extract, [url]) or [{}])[0]
        except Exception as e:  # noqa: BLE001
            page = {"error": str(e)}
        if page.get("content") and not page.get("error"):
            return page
        return {
            "url": url,
            "title": "",
            "content": "",
            "error": f"{reason}; Tavily retry: {page.get('error') or 'no content'}",
        }

    def _extract_title(self, markdown: str, fallback_url: str) -> str:
        if not markdown:
            return fallback_url
        for line in markdown.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return fallback_url

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "self-hosted",
            "tag": "Uses your self-hosted crawl4ai instance at CRAWL4AI_URL",
            "env_vars": [
                {
                    "key": "CRAWL4AI_URL",
                    "prompt": "Crawl4ai instance URL (e.g., https://crawl4ai.example.com)",
                    "url": "https://github.com/unclecode/crawl4ai",
                },
                {
                    "key": "CRAWL4AI_API_TOKEN",
                    "prompt": "Crawl4ai JWT API token",
                    "url": "",
                },
            ],
        }