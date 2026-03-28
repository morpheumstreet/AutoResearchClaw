"""Web page → Markdown extraction.

Backends:

- **crawl4ai** (default): Crawl4AI when available; falls back to urllib.
- **spider_cli**: [spider-rs spider CLI](https://github.com/spider-rs/spider/tree/main/spider_cli)
  (`spider --url … --return-format markdown scrape`); falls back to urllib.
- **urllib**: HTTP fetch + simple HTML → Markdown (no Crawl4AI / spider).

Usage::

    crawler = WebCrawler()
    result = await crawler.crawl("https://arxiv.org/abs/2301.00001")
    print(result.markdown)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.request import Request, urlopen

from researchclaw.web._ssrf import check_url_ssrf

logger = logging.getLogger(__name__)

CRAWL_BACKEND_CRAWL4AI = "crawl4ai"
CRAWL_BACKEND_SPIDER_CLI = "spider_cli"
CRAWL_BACKEND_URLLIB = "urllib"


@dataclass
class CrawlResult:
    """Result of crawling a single URL."""

    url: str
    markdown: str = ""
    title: str = ""
    success: bool = False
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    @property
    def has_content(self) -> bool:
        return bool(self.markdown and len(self.markdown.strip()) > 50)


class WebCrawler:
    """Web page → Markdown crawler (Crawl4AI, spider CLI, or urllib).

    Parameters
    ----------
    backend:
        ``crawl4ai`` | ``spider_cli`` | ``urllib``.
    timeout:
        Request timeout in seconds.
    max_content_length:
        Maximum content length in characters (truncate beyond this).
    spider_cli_path:
        Executable name or path for `spider` (see spider_cli).
    spider_cli_http_only:
        Pass ``--http`` to spider (no headless Chrome; default).
    spider_cli_headless:
        Pass ``--headless`` when not using HTTP-only mode (JS-heavy pages).
    """

    def __init__(
        self,
        *,
        backend: str = CRAWL_BACKEND_CRAWL4AI,
        timeout: int = 30,
        max_content_length: int = 50_000,
        user_agent: str = "ResearchClaw/0.5 (Academic Research Bot)",
        spider_cli_path: str = "spider",
        spider_cli_http_only: bool = True,
        spider_cli_headless: bool = False,
    ) -> None:
        self.backend = (backend or CRAWL_BACKEND_CRAWL4AI).strip().lower()
        if self.backend not in (
            CRAWL_BACKEND_CRAWL4AI,
            CRAWL_BACKEND_SPIDER_CLI,
            CRAWL_BACKEND_URLLIB,
        ):
            self.backend = CRAWL_BACKEND_CRAWL4AI
        self.timeout = timeout
        self.max_content_length = max_content_length
        self.user_agent = user_agent
        self.spider_cli_path = spider_cli_path
        self.spider_cli_http_only = spider_cli_http_only
        self.spider_cli_headless = spider_cli_headless

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def crawl(self, url: str) -> CrawlResult:
        """Crawl a URL and return Markdown content (async)."""
        err = check_url_ssrf(url)
        if err:
            return CrawlResult(url=url, success=False, error=err, elapsed_seconds=0.0)
        t0 = time.monotonic()
        if self.backend == CRAWL_BACKEND_URLLIB:
            try:
                return await asyncio.to_thread(self._crawl_with_urllib, url, t0)
            except Exception as exc:  # noqa: BLE001
                elapsed = time.monotonic() - t0
                return CrawlResult(
                    url=url, success=False, error=str(exc), elapsed_seconds=elapsed
                )

        if self.backend == CRAWL_BACKEND_SPIDER_CLI:
            r = await asyncio.to_thread(self._crawl_with_spider_cli, url, t0)
            if r.success:
                return r
            try:
                return await asyncio.to_thread(self._crawl_with_urllib, url, t0)
            except Exception as exc2:  # noqa: BLE001
                elapsed = time.monotonic() - t0
                logger.warning("spider_cli + urllib failed for %s: %s", url, exc2)
                return CrawlResult(
                    url=url, success=False, error=str(exc2), elapsed_seconds=elapsed
                )

        try:
            return await self._crawl_with_crawl4ai(url, t0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Crawl4AI failed for %s (%s), trying urllib fallback", url, exc)
            try:
                return await asyncio.to_thread(self._crawl_with_urllib, url, t0)
            except Exception as exc2:  # noqa: BLE001
                elapsed = time.monotonic() - t0
                logger.warning("All crawl backends failed for %s: %s", url, exc2)
                return CrawlResult(url=url, success=False, error=str(exc2), elapsed_seconds=elapsed)

    def crawl_sync(self, url: str) -> CrawlResult:
        """Synchronous crawl — backend-specific, with urllib fallback where applicable."""
        err = check_url_ssrf(url)
        if err:
            return CrawlResult(url=url, success=False, error=err, elapsed_seconds=0.0)
        t0 = time.monotonic()
        if self.backend == CRAWL_BACKEND_URLLIB:
            try:
                return self._crawl_with_urllib(url, t0)
            except Exception as exc:  # noqa: BLE001
                elapsed = time.monotonic() - t0
                return CrawlResult(
                    url=url, success=False, error=str(exc), elapsed_seconds=elapsed
                )

        if self.backend == CRAWL_BACKEND_SPIDER_CLI:
            r = self._crawl_with_spider_cli(url, t0)
            if r.success:
                return r
            try:
                return self._crawl_with_urllib(url, t0)
            except Exception as exc:  # noqa: BLE001
                elapsed = time.monotonic() - t0
                return CrawlResult(
                    url=url, success=False, error=str(exc), elapsed_seconds=elapsed
                )

        try:
            return asyncio.run(self._crawl_with_crawl4ai(url, t0))
        except Exception:  # noqa: BLE001
            try:
                return self._crawl_with_urllib(url, t0)
            except Exception as exc:  # noqa: BLE001
                elapsed = time.monotonic() - t0
                return CrawlResult(url=url, success=False, error=str(exc), elapsed_seconds=elapsed)

    async def crawl_many(self, urls: list[str]) -> list[CrawlResult]:
        """Crawl multiple URLs (parallel where possible)."""
        if self.backend == CRAWL_BACKEND_SPIDER_CLI:
            return await asyncio.gather(*[self._crawl_one_spider(u) for u in urls])

        if self.backend == CRAWL_BACKEND_URLLIB:
            return await asyncio.gather(
                *[self._crawl_one_urllib(u) for u in urls]
            )

        results: list[CrawlResult] = []
        try:
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig

            browser_config = BrowserConfig(headless=True)
            run_config = CrawlerRunConfig(
                word_count_threshold=10,
                excluded_tags=["nav", "footer", "header", "sidebar"],
                remove_overlay_elements=True,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                for url in urls:
                    err = check_url_ssrf(url)
                    if err:
                        results.append(CrawlResult(url=url, success=False, error=err, elapsed_seconds=0.0))
                        continue
                    t0 = time.monotonic()
                    try:
                        raw = await crawler.arun(url=url, config=run_config)
                        elapsed = time.monotonic() - t0
                        if raw.success:
                            md = self._extract_markdown(raw)
                            results.append(CrawlResult(
                                url=url, markdown=md,
                                title=getattr(raw, "title", "") or "",
                                success=True, elapsed_seconds=elapsed,
                                metadata=raw.metadata if hasattr(raw, "metadata") and raw.metadata else {},
                            ))
                        else:
                            results.append(CrawlResult(
                                url=url, success=False,
                                error=getattr(raw, "error_message", "crawl failed"),
                                elapsed_seconds=elapsed,
                            ))
                    except Exception as exc:  # noqa: BLE001
                        elapsed = time.monotonic() - t0
                        results.append(CrawlResult(url=url, success=False, error=str(exc), elapsed_seconds=elapsed))
        except ImportError:
            # Crawl4AI browser not set up — use urllib for each
            for url in urls:
                err = check_url_ssrf(url)
                if err:
                    results.append(CrawlResult(url=url, success=False, error=err, elapsed_seconds=0.0))
                    continue
                t0 = time.monotonic()
                try:
                    results.append(self._crawl_with_urllib(url, t0))
                except Exception as exc:  # noqa: BLE001
                    elapsed = time.monotonic() - t0
                    results.append(CrawlResult(url=url, success=False, error=str(exc), elapsed_seconds=elapsed))
        return results

    async def _crawl_one_spider(self, url: str) -> CrawlResult:
        err = check_url_ssrf(url)
        if err:
            return CrawlResult(url=url, success=False, error=err, elapsed_seconds=0.0)
        t0 = time.monotonic()
        r = await asyncio.to_thread(self._crawl_with_spider_cli, url, t0)
        if r.success:
            return r
        try:
            return await asyncio.to_thread(self._crawl_with_urllib, url, time.monotonic())
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            return CrawlResult(
                url=url, success=False, error=str(exc), elapsed_seconds=elapsed
            )

    async def _crawl_one_urllib(self, url: str) -> CrawlResult:
        err = check_url_ssrf(url)
        if err:
            return CrawlResult(url=url, success=False, error=err, elapsed_seconds=0.0)
        t0 = time.monotonic()
        try:
            return await asyncio.to_thread(self._crawl_with_urllib, url, t0)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            return CrawlResult(
                url=url, success=False, error=str(exc), elapsed_seconds=elapsed
            )

    # ------------------------------------------------------------------
    # Crawl4AI backend (primary)
    # ------------------------------------------------------------------

    async def _crawl_with_crawl4ai(self, url: str, t0: float) -> CrawlResult:
        """Use Crawl4AI for high-quality extraction."""
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig

        browser_config = BrowserConfig(headless=True)
        run_config = CrawlerRunConfig(
            word_count_threshold=10,
            excluded_tags=["nav", "footer", "header", "sidebar"],
            remove_overlay_elements=True,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            raw = await crawler.arun(url=url, config=run_config)

        elapsed = time.monotonic() - t0
        if raw.success:
            md = self._extract_markdown(raw)
            return CrawlResult(
                url=url, markdown=md,
                title=getattr(raw, "title", "") or "",
                success=True, elapsed_seconds=elapsed,
                metadata=raw.metadata if hasattr(raw, "metadata") and raw.metadata else {},
            )
        return CrawlResult(
            url=url, success=False,
            error=getattr(raw, "error_message", "Unknown crawl4ai error"),
            elapsed_seconds=elapsed,
        )

    def _extract_markdown(self, raw: Any) -> str:
        """Extract markdown from a Crawl4AI result object."""
        # Crawl4AI v0.8+ uses markdown_v2.raw_markdown
        md = ""
        if hasattr(raw, "markdown_v2") and raw.markdown_v2:
            md = getattr(raw.markdown_v2, "raw_markdown", "") or ""
        if not md and hasattr(raw, "markdown"):
            md = raw.markdown or ""
        if len(md) > self.max_content_length:
            md = md[: self.max_content_length] + "\n\n[... truncated]"
        return md

    # ------------------------------------------------------------------
    # spider_cli (spider-rs) — https://github.com/spider-rs/spider/tree/main/spider_cli
    # ------------------------------------------------------------------

    def _crawl_with_spider_cli(self, url: str, t0: float) -> CrawlResult:
        """Run ``spider --url … --return-format markdown scrape``; parse JSONL stdout."""
        cmd: list[str] = [
            self.spider_cli_path,
            "--url",
            url,
            "--return-format",
            "markdown",
            "scrape",
        ]
        if self.spider_cli_http_only:
            cmd.append("--http")
        elif self.spider_cli_headless:
            cmd.append("--headless")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=float(self.timeout),
                check=False,
            )
        except FileNotFoundError:
            elapsed = time.monotonic() - t0
            return CrawlResult(
                url=url,
                success=False,
                error=f"spider CLI not found ({self.spider_cli_path!r})",
                elapsed_seconds=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - t0
            return CrawlResult(
                url=url,
                success=False,
                error="spider CLI timed out",
                elapsed_seconds=elapsed,
            )

        elapsed = time.monotonic() - t0
        if proc.returncode != 0:
            err_tail = (proc.stderr or proc.stdout or "").strip()[:500]
            return CrawlResult(
                url=url,
                success=False,
                error=f"spider CLI exited {proc.returncode}: {err_tail}",
                elapsed_seconds=elapsed,
                metadata={"stderr": (proc.stderr or "")[:2000]},
            )

        markdown, title = self._parse_spider_scrape_output(proc.stdout or "")
        if not markdown.strip():
            return CrawlResult(
                url=url,
                success=False,
                error="spider CLI produced no markdown",
                elapsed_seconds=elapsed,
            )
        if len(markdown) > self.max_content_length:
            markdown = markdown[: self.max_content_length] + "\n\n[... truncated]"
        return CrawlResult(
            url=url,
            markdown=markdown,
            title=title,
            success=True,
            elapsed_seconds=elapsed,
            metadata={"backend": "spider_cli"},
        )

    def _parse_spider_scrape_output(self, stdout: str) -> tuple[str, str]:
        """Parse spider ``scrape`` JSONL stdout into markdown and a best-effort title."""
        md_parts: list[str] = []
        title = ""
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                t = obj.get("title") or obj.get("page_title") or obj.get("name")
                if isinstance(t, str) and t.strip():
                    title = t.strip()
                m = (
                    obj.get("markdown")
                    or obj.get("content")
                    or obj.get("text")
                    or obj.get("raw_markdown")
                )
                if isinstance(m, str) and m.strip():
                    md_parts.append(m.strip())
                elif isinstance(obj.get("html"), str) and str(obj["html"]).strip():
                    md_parts.append(self._html_to_markdown(str(obj["html"])))
        markdown = "\n\n".join(md_parts)
        return markdown, title

    # ------------------------------------------------------------------
    # urllib fallback (lightweight, no browser needed)
    # ------------------------------------------------------------------

    def _crawl_with_urllib(self, url: str, t0: float) -> CrawlResult:
        """Lightweight fallback: fetch HTML and strip tags."""
        req = Request(url, headers={"User-Agent": self.user_agent})
        resp = urlopen(req, timeout=self.timeout)  # noqa: S310
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read()

        encoding = "utf-8"
        if "charset=" in content_type:
            encoding = content_type.split("charset=")[-1].split(";")[0].strip()
        html = raw.decode(encoding, errors="replace")

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""

        markdown = self._html_to_markdown(html)
        if len(markdown) > self.max_content_length:
            markdown = markdown[: self.max_content_length] + "\n\n[... truncated]"

        elapsed = time.monotonic() - t0
        return CrawlResult(
            url=url, markdown=markdown, title=title,
            success=bool(markdown.strip()), elapsed_seconds=elapsed,
        )

    @staticmethod
    def _html_to_markdown(html: str) -> str:
        """Best-effort HTML → Markdown conversion via regex."""
        text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<a[^>]*href=[\"']([^\"']*)[\"'][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        import html as _html
        text = _html.unescape(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()
