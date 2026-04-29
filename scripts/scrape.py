#!/usr/bin/env python3
"""
FreeCrawl Scrape v1.1 — single page scraper + SearXNG search
Usage: python scrape.py <url> [options]
       python scrape.py --search <keyword> [--count N]
"""

import argparse
import re
import sys
import os
import time
from urllib.parse import urlparse
from html.parser import HTMLParser

# ═══════════════════════════════════════════════════════════════════
# UTF-8 force for Windows compatibility
# ═══════════════════════════════════════════════════════════════════
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    import requests
except ImportError:
    print("ERROR: install requests. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

DEFAULT_TIMEOUT = int(os.environ.get("FREECRAWL_TIMEOUT", "30"))
DEFAULT_PROXY = os.environ.get("FREECRAWL_PROXY")
DEFAULT_UA = os.environ.get(
    "FREECRAWL_USER_AGENT",
    "FreeCrawl/1.1 (+https://github.com/freecrawl)"
)
SEARXNG_BASE = os.environ.get("SEARXNG_BASE", "http://192.168.18.43:8090")
MAX_RETRIES = int(os.environ.get("FREECRAWL_RETRIES", "3"))


# ═══════════════════════════════════════════════════════════════════
# HTTP helper with retry
# ═══════════════════════════════════════════════════════════════════

def http_get(url, proxy=None, timeout=DEFAULT_TIMEOUT, retries=MAX_RETRIES, **kwargs):
    """HTTP GET with retry + exponential backoff."""
    s = requests.Session()
    s.headers.update({"User-Agent": DEFAULT_UA})
    proxies = {"http": proxy, "https": proxy} if proxy else None

    last_err = None
    for attempt in range(retries):
        try:
            r = s.get(url, timeout=timeout, proxies=proxies, allow_redirects=True, **kwargs)
            r.raise_for_status()
            return r
        except requests.exceptions.Timeout as e:
            last_err = e
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"[retry] timeout, waiting {wait}s (attempt {attempt+1}/{retries})", file=sys.stderr)
                time.sleep(wait)
                timeout = int(timeout * 1.5)  # Increase timeout on retry
        except requests.exceptions.RequestException as e:
            last_err = e
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"[retry] {e}, waiting {wait}s (attempt {attempt+1}/{retries})", file=sys.stderr)
                time.sleep(wait)
    raise last_err


# ═══════════════════════════════════════════════════════════════════
# HTML → Text (stdlib only, no bs4)
# ═══════════════════════════════════════════════════════════════════

class HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = {"script", "style", "noscript", "iframe", "svg", "head"}
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self.skip:
            self.depth += 1
        if t in ("br", "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self.skip:
            self.depth = max(0, self.depth - 1)
        if t in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self.depth == 0:
            s = data.strip()
            if s:
                self.parts.append(s + " ")

    def get_text(self):
        return "".join(self.parts).strip()


def html_to_text(html):
    p = HTMLToText()
    p.feed(html)
    p.close()
    return p.get_text()


# ═══════════════════════════════════════════════════════════════════
# HTML → Markdown (bs4)
# ═══════════════════════════════════════════════════════════════════

def html_to_markdown(html, base_url=""):
    """Convert HTML to Markdown using BeautifulSoup."""
    if not HAS_BS4:
        return html_to_text(html)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "nav", "footer", "header"]):
        tag.decompose()

    out = []

    def walk(el):
        if el.name is None:
            t = str(el).strip()
            if t:
                out.append(t)
            return

        tag = el.name.lower()

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            lv = int(tag[1])
            out.append(f"\n{'#' * lv} {el.get_text(strip=True)}\n")
            return

        if tag == "a":
            href = el.get("href", "")
            txt = el.get_text(strip=True)
            if href and txt:
                if base_url and not href.startswith(("http://", "https://", "//")):
                    href = base_url.rstrip("/") + "/" + href.lstrip("/")
                out.append(f"[{txt}]({href})")
            elif txt:
                out.append(txt)
            return

        if tag == "img":
            alt = el.get("alt", "")
            src = el.get("src", "")
            if src:
                if base_url and not src.startswith(("http://", "https://", "//")):
                    src = base_url.rstrip("/") + "/" + src.lstrip("/")
                out.append(f"\n![{alt}]({src})\n")
            return

        if tag == "li":
            out.append("\n- ")
            for c in el.children:
                walk(c)
            out.append("\n")
            return

        if tag == "pre":
            lang = ""
            ce = el.find("code")
            if ce and ce.get("class"):
                for c in ce.get("class"):
                    if c.startswith("language-"):
                        lang = c[9:]
            out.append(f"\n```{lang}\n{el.get_text()}\n```\n")
            return
        if tag == "code":
            out.append(f"`{el.get_text()}`")
            return

        block = {"p", "div", "section", "article", "blockquote", "hr", "table", "br"}
        if tag in block:
            out.append("\n")
        for c in el.children:
            walk(c)
        if tag in block:
            out.append("\n")

    main = soup.find("main") or soup.find("article") or soup.find("body") or soup
    walk(main)
    result = "\n".join(out).strip()
    # Collapse excessive blank lines
    result = re.sub(r'\n{4,}', '\n\n\n', result)
    return result


# ═══════════════════════════════════════════════════════════════════
# Fetch
# ═══════════════════════════════════════════════════════════════════

def fetch_url(url, proxy=None, timeout=DEFAULT_TIMEOUT):
    r = http_get(url, proxy=proxy, timeout=timeout)
    ct = r.headers.get("content-type", "")
    if "text/html" not in ct and "application/xhtml" not in ct:
        print(f"[warn] content-type is '{ct}', may not be HTML", file=sys.stderr)
    return r


def js_render(url, proxy=None, screenshot_path=None, timeout=DEFAULT_TIMEOUT):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: install playwright. Run: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        sys.exit(1)

    with sync_playwright() as p:
        kwargs = {"headless": True}
        if proxy:
            kwargs["proxy"] = {"server": proxy}
        browser = p.chromium.launch(**kwargs)
        ctx = browser.new_context(user_agent=DEFAULT_UA)
        page = ctx.new_page()
        try:
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
            html = page.content()
            if screenshot_path:
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"[screenshot] saved: {screenshot_path}", file=sys.stderr)
            return html
        finally:
            ctx.close()
            browser.close()


# ═══════════════════════════════════════════════════════════════════
# Search (v1.1: engine fallback + JSON output)
# ═══════════════════════════════════════════════════════════════════

SEARCH_ENGINE_GROUPS = [
    "bing,sogou,360search,baidu",
    "bing,google,duckduckgo",
    "bing,baidu",
]


def cmd_search(keyword, count=5, engines=None, json_output=False):
    """Search via SearXNG with engine fallback."""
    import json

    engine_groups = [engines] if engines else SEARCH_ENGINE_GROUPS

    for eg in engine_groups:
        params = {"q": keyword, "format": "json", "engines": eg}
        try:
            r = http_get(f"{SEARXNG_BASE}/search", params=params, timeout=15)
            data = r.json()
            results = data.get("results", [])
            if results:
                results = results[:count]
                if json_output:
                    output = []
                    for item in results:
                        output.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": (item.get("content") or item.get("snippet", ""))[:300],
                            "engine": item.get("engine", ""),
                        })
                    print(json.dumps(output, ensure_ascii=False, indent=2))
                else:
                    for i, item in enumerate(results, 1):
                        title = item.get("title", "N/A")
                        url = item.get("url", "")
                        snippet = (item.get("content") or item.get("snippet", ""))[:200]
                        print(f"{i}. **{title}**")
                        print(f"   URL: {url}")
                        if snippet:
                            print(f"   {snippet}")
                        print()
                return results
            else:
                print(f"[warn] 0 results with engines '{eg}', trying next...", file=sys.stderr)
        except Exception as e:
            print(f"[warn] search failed with engines '{eg}': {e}, trying next...", file=sys.stderr)

    print("[error] all engine groups failed", file=sys.stderr)
    return []


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="FreeCrawl Scrape v1.1 — single page fetch + SearXNG search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scrape.py https://httpbin.org/html
  python scrape.py https://example.com --format text
  python scrape.py https://spa-site.com --js-render --screenshot shot.png
  python scrape.py https://blocked.com --proxy http://127.0.0.1:6738
  python scrape.py --search "python web scraping" --count 5
  python scrape.py --search "AI" --json -o results.json
        """,
    )
    parser.add_argument("url", nargs="?", help="URL to scrape (omit for --search)")
    parser.add_argument("--search", "-S", metavar="KEYWORD", help="Search via SearXNG instead of fetching URL")
    parser.add_argument("--count", type=int, default=5, help="Search result count (default: 5)")
    parser.add_argument("--engines", help="SearXNG search engines (default: auto-fallback)")
    parser.add_argument("--json", action="store_true", help="Output search results as JSON")
    parser.add_argument("--format", "-f", choices=["markdown", "html", "text"], default="markdown")
    parser.add_argument("--js-render", action="store_true", help="Use Playwright for JS rendering")
    parser.add_argument("--screenshot", "-s", metavar="PATH", help="Save screenshot (requires --js-render)")
    parser.add_argument("--proxy", "-p", default=DEFAULT_PROXY, help="Proxy URL (auto-detected from FREECRAWL_PROXY)")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help=f"Timeout seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--output", "-o", metavar="FILE", help="Output to file")
    parser.add_argument("--max-chars", "-m", type=int, default=None, help="Max output characters")
    parser.add_argument("--retries", "-r", type=int, default=MAX_RETRIES, help=f"Max HTTP retries (default: {MAX_RETRIES})")

    args = parser.parse_args()

    # Search mode
    if args.search:
        cmd_search(args.search, args.count, args.engines, args.json)
        return

    # URL required for fetch
    if not args.url:
        parser.print_help()
        sys.exit(1)

    try:
        if args.js_render:
            print(f"[js-render] {args.url}", file=sys.stderr)
            html = js_render(args.url, proxy=args.proxy,
                             screenshot_path=args.screenshot, timeout=args.timeout)
        else:
            print(f"[fetch] {args.url}", file=sys.stderr)
            resp = fetch_url(args.url, proxy=args.proxy, timeout=args.timeout)
            html = resp.text

        if args.format == "html":
            output = html
        elif args.format == "text":
            output = html_to_text(html)
        else:
            base_url = f"{urlparse(args.url).scheme}://{urlparse(args.url).netloc}"
            output = html_to_markdown(html, base_url)

        if args.max_chars and len(output) > args.max_chars:
            output = output[:args.max_chars] + f"\n\n... [truncated, original {len(output)} chars]"

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"[saved] {args.output} ({len(output)} chars)", file=sys.stderr)
        else:
            print(output)

    except requests.exceptions.RequestException as e:
        print(f"ERROR: request failed - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
