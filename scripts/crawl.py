#!/usr/bin/env python3
"""
FreeCrawl Crawl — 多页递归爬取工具
用法: python crawl.py <url> [--depth N] [--max-pages M] [--proxy URL] [-o FILE]

从起始页出发，递归爬取同域名所有链接，自动去重、深度控制。
"""

import argparse
import json
import os
import re
import sys
import time
import hashlib
from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse
from dataclasses import dataclass, field, asdict

try:
    import requests
except ImportError:
    print("错误: 需要安装 requests。运行: pip install requests")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# --- Defaults ---
DEFAULT_TIMEOUT = int(os.environ.get("FREECRAWL_TIMEOUT", "30"))
DEFAULT_PROXY = os.environ.get("FREECRAWL_PROXY")
DEFAULT_UA = os.environ.get(
    "FREECRAWL_USER_AGENT",
    "FreeCrawl/1.0 (compatible; +https://github.com/freecrawl)"
)
DEFAULT_DELAY = float(os.environ.get("FREECRAWL_DELAY", "0.5"))  # 请求间隔（礼貌爬取）


@dataclass
class PageResult:
    url: str
    title: str = ""
    text_preview: str = ""
    links: list = field(default_factory=list)
    status: int = 0
    content_type: str = ""
    content_length: int = 0


def normalize_url(url: str, base_domain: str) -> str:
    """Normalize URL: remove fragment, trailing slash, common tracking params."""
    parsed = urlparse(url)
    # Remove fragment
    cleaned = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))
    # Remove trailing slash for consistency
    if cleaned.endswith("/") and cleaned.count("/") > 3:
        cleaned = cleaned.rstrip("/")
    return cleaned


def is_same_domain(url: str, base_domain: str) -> bool:
    """Check if URL belongs to the same domain."""
    try:
        domain = urlparse(url).netloc.lower()
        # Strip www.
        if domain.startswith("www."):
            domain = domain[4:]
        if base_domain.startswith("www."):
            base_domain = base_domain[4:]
        return domain == base_domain
    except Exception:
        return False


def is_likely_page(url: str) -> bool:
    """Skip non-HTML resources."""
    skip_extensions = {
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
        ".css", ".js", ".json", ".xml", ".rss", ".atom",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
        ".mp3", ".mp4", ".avi", ".mov", ".webm", ".wmv",
        ".woff", ".woff2", ".ttf", ".eot",
        ".map", ".md5", ".sha1",
    }
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path:
        for ext in skip_extensions:
            if path.endswith(ext):
                return False
    return True


def extract_links(html: str, base_url: str) -> list:
    """Extract all <a href> links from HTML."""
    links = []
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                full_url = urljoin(base_url, href)
                links.append(full_url)
    else:
        # Fallback: simple regex
        pattern = re.compile(r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\']', re.IGNORECASE)
        for match in pattern.finditer(html):
            href = match.group(1).strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                full_url = urljoin(base_url, href)
                links.append(full_url)
    return links


def extract_text_preview(html: str, max_chars: int = 500) -> str:
    """Extract a short text preview from HTML."""
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
    else:
        # Remove tags roughly
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def crawl(
    start_url: str,
    depth: int = 2,
    max_pages: int = 50,
    proxy: str = None,
    timeout: int = DEFAULT_TIMEOUT,
    delay: float = DEFAULT_DELAY,
    progress_callback=None,
) -> list:
    """BFS crawl starting from start_url."""
    base_domain = urlparse(start_url).netloc.lower()
    if base_domain.startswith("www."):
        base_domain = base_domain[4:]

    visited = set()
    queue = deque()
    queue.append((start_url, 0))
    results = []

    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_UA})
    proxies = {"http": proxy, "https": proxy} if proxy else None

    while queue and len(results) < max_pages:
        url, current_depth = queue.popleft()
        normalized = normalize_url(url, base_domain)

        if normalized in visited:
            continue
        visited.add(normalized)

        print(f"[{len(results) + 1}/{max_pages}] depth={current_depth} {url}", file=sys.stderr)

        try:
            resp = session.get(url, timeout=timeout, proxies=proxies, allow_redirects=True)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                print(f"  -> skip (Content-Type: {content_type})", file=sys.stderr)
                continue

            html = resp.text
            title = ""
            links = []

            if HAS_BS4:
                soup = BeautifulSoup(html, "html.parser")
                title_tag = soup.find("title")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                links = extract_links(html, url)
            else:
                title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
                if title_match:
                    title = title_match.group(1).strip()
                links = extract_links(html, url)

            text_preview = extract_text_preview(html)

            result = PageResult(
                url=resp.url,
                title=title,
                text_preview=text_preview,
                links=links[:20],  # Only keep first 20 links for output
                status=resp.status_code,
                content_type=content_type,
                content_length=len(html),
            )
            results.append(result)

            if progress_callback:
                progress_callback(result)

            # Enqueue same-domain links
            if current_depth < depth:
                new_links = []
                for link in links:
                    norm_link = normalize_url(link, base_domain)
                    if norm_link not in visited and is_same_domain(link, base_domain) and is_likely_page(link):
                        new_links.append(link)

                # Deduplicate and limit per level
                seen_new = set()
                for link in new_links:
                    nl = normalize_url(link, base_domain)
                    if nl not in seen_new and nl not in visited:
                        seen_new.add(nl)
                        queue.append((link, current_depth + 1))

            # Be polite
            if delay > 0:
                time.sleep(delay)

        except requests.exceptions.RequestException as e:
            print(f"  -> error: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"  -> error: {e}", file=sys.stderr)
            continue

    return results


def main():
    parser = argparse.ArgumentParser(
        description="FreeCrawl Crawl — 多页递归爬取，同域名、去重、深度控制",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python crawl.py https://example.com --depth 2 --max-pages 50
  python crawl.py https://example.com -o results.json --format json
  python crawl.py https://blocked.com --proxy http://127.0.0.1:6738
        """,
    )
    parser.add_argument("url", help="起始 URL")
    parser.add_argument("--depth", "-d", type=int, default=2, help="爬取深度 (默认: 2)")
    parser.add_argument("--max-pages", "-m", type=int, default=50, help="最大页面数 (默认: 50)")
    parser.add_argument("--proxy", "-p", default=DEFAULT_PROXY, help="代理地址")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help=f"请求超时秒数 (默认: {DEFAULT_TIMEOUT})")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"请求间隔秒数 (默认: {DEFAULT_DELAY})")
    parser.add_argument("--output", "-o", metavar="FILE", help="输出到 JSON 文件")
    parser.add_argument("--format", "-f", choices=["json", "summary"], default="summary", help="输出格式 (默认: summary)")

    args = parser.parse_args()

    print(f"FreeCrawl Crawl: {args.url}", file=sys.stderr)
    print(f"  depth={args.depth} max_pages={args.max_pages} delay={args.delay}s", file=sys.stderr)
    print("", file=sys.stderr)

    results = crawl(
        start_url=args.url,
        depth=args.depth,
        max_pages=args.max_pages,
        proxy=args.proxy,
        timeout=args.timeout,
        delay=args.delay,
    )

    print(f"\n完成! 共抓取 {len(results)} 个页面", file=sys.stderr)

    if args.format == "json":
        output_data = [asdict(r) for r in results]
        json_str = json.dumps(output_data, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(f"已保存: {args.output}", file=sys.stderr)
        else:
            print(json_str)
    else:
        # Summary format
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r.url}")
            if r.title:
                lines.append(f"    标题: {r.title}")
            if r.text_preview:
                preview = r.text_preview[:200].replace("\n", " ")
                lines.append(f"    预览: {preview}...")
            lines.append(f"    链接数: {len(r.links)} | 状态: {r.status} | 大小: {r.content_length}B")
            lines.append("")
        output = "\n".join(lines)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"已保存: {args.output}", file=sys.stderr)
        else:
            print(output)


if __name__ == "__main__":
    main()
