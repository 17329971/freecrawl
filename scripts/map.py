#!/usr/bin/env python3
"""
FreeCrawl Map — URL 发现工具
用法: python map.py <url> [--depth N] [--proxy URL] [-o FILE]

尝试多种方式发现目标站点的链接：
1. sitemap.xml / sitemap_index.xml
2. robots.txt
3. 页面内链接提取
"""

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field, asdict
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

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


@dataclass
class MapResult:
    source: str  # "sitemap", "robots.txt", "page_links"
    urls: list = field(default_factory=list)
    count: int = 0


def fetch(url: str, proxy: str = None, timeout: int = DEFAULT_TIMEOUT) -> requests.Response:
    """Fetch a URL."""
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_UA})
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = session.get(url, timeout=timeout, proxies=proxies, allow_redirects=True)
    resp.raise_for_status()
    return resp


def discover_sitemaps(base_url: str, proxy: str = None, timeout: int = DEFAULT_TIMEOUT) -> list:
    """Try to find sitemaps: sitemap.xml, then robots.txt."""
    sitemap_urls = []
    parsed = urlparse(base_url)
    base_origin = f"{parsed.scheme}://{parsed.netloc}"

    # Method 1: Standard sitemap paths
    candidates = [
        f"{base_origin}/sitemap.xml",
        f"{base_origin}/sitemap_index.xml",
        f"{base_origin}/sitemap-index.xml",
        f"{base_origin}/sitemap.php",
        f"{base_origin}/sitemap.txt",
        f"{base_origin}/wp-sitemap.xml",  # WordPress
    ]

    print("[map] 尝试查找 sitemap...", file=sys.stderr)
    for url in candidates:
        try:
            resp = fetch(url, proxy, timeout)
            content_type = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and ("xml" in content_type or "text/plain" in content_type):
                print(f"  [sitemap] 找到: {url}", file=sys.stderr)
                sitemap_urls.append(url)
            if resp.status_code == 200 and "text/xml" not in content_type.lower():
                # Might still be XML
                if resp.text.strip().startswith("<?xml") or "<urlset" in resp.text or "<sitemapindex" in resp.text:
                    print(f"  [sitemap] 找到: {url}", file=sys.stderr)
                    sitemap_urls.append(url)
        except Exception:
            continue

    return sitemap_urls


def parse_sitemap(url: str, proxy: str = None, timeout: int = DEFAULT_TIMEOUT) -> list:
    """Parse a sitemap XML and extract URLs."""
    urls = []
    try:
        resp = fetch(url, proxy, timeout)
        text = resp.text

        # Remove namespace prefixes for easier parsing
        text = re.sub(r' xmlns="[^"]*"', "", text, count=1)
        text = re.sub(r' xmlns:[a-z]+="[^"]*"', "", text, count=3)

        root = ET.fromstring(text)

        # Check if it's a sitemap index
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        # Try to find <sitemap> elements (sitemap index)
        for sm in root.iter("sitemap"):
            loc = sm.find("loc")
            if loc is not None and loc.text:
                urls.append(loc.text.strip())

        # If we found sitemap references, recursively parse them
        if urls:
            # These are sub-sitemaps
            nested_urls = []
            for sm_url in urls[:10]:  # Limit recursion
                try:
                    nested = parse_sitemap(sm_url, proxy, timeout)
                    nested_urls.extend(nested)
                except Exception:
                    continue
            return nested_urls

        # Otherwise parse <url> elements
        for url_el in root.iter("url"):
            loc = url_el.find("loc")
            if loc is not None and loc.text:
                urls.append(loc.text.strip())

        # Also try without namespace
        if not urls:
            for loc in root.iter("loc"):
                if loc.text:
                    urls.append(loc.text.strip())

    except ET.ParseError as e:
        print(f"  [sitemap] XML 解析错误: {e}", file=sys.stderr)
    except Exception as e:
        print(f"  [sitemap] 获取失败: {e}", file=sys.stderr)

    return urls


def get_robots_txt_urls(base_url: str, proxy: str = None, timeout: int = DEFAULT_TIMEOUT) -> list:
    """Extract Sitemap references and allowed paths from robots.txt."""
    urls = []
    try:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        resp = fetch(robots_url, proxy, timeout)

        if resp.status_code == 200:
            print(f"  [robots.txt] 找到: {robots_url}", file=sys.stderr)

            # Extract Sitemap: lines
            for line in resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sm_url = line.split(":", 1)[1].strip()
                    urls.append(sm_url)
                    print(f"  [robots.txt] Sitemap 引用: {sm_url}", file=sys.stderr)

    except Exception:
        pass

    return urls


def extract_page_links(html: str, base_url: str) -> list:
    """Extract all links from a page."""
    links = []
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                full_url = urljoin(base_url, href)
                links.append(full_url)
    else:
        pattern = re.compile(r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\']', re.IGNORECASE)
        for match in pattern.finditer(html):
            href = match.group(1).strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                full_url = urljoin(base_url, href)
                links.append(full_url)
    return links


def is_same_domain(url: str, base_domain: str) -> bool:
    """Check same domain."""
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if base_domain.startswith("www."):
            base_domain = base_domain[4:]
        return domain == base_domain
    except Exception:
        return False


def discover_page_links(
    base_url: str,
    depth: int = 1,
    proxy: str = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list:
    """Discover links by crawling pages up to specified depth."""
    base_domain = urlparse(base_url).netloc.lower()
    if base_domain.startswith("www."):
        base_domain = base_domain[4:]

    all_links = set()
    visited = set()
    queue = deque()
    queue.append((base_url, 0))

    print(f"[page_links] 爬取深度 {depth}...", file=sys.stderr)

    while queue:
        url, current_depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        print(f"  [page_links] depth={current_depth} {url}", file=sys.stderr)

        try:
            resp = fetch(url, proxy, timeout)
            if "text/html" not in resp.headers.get("Content-Type", ""):
                continue

            links = extract_page_links(resp.text, url)
            for link in links:
                all_links.add(link)
                if current_depth < depth and is_same_domain(link, base_domain) and link not in visited:
                    queue.append((link, current_depth + 1))

            time.sleep(0.5)  # Be polite

        except Exception as e:
            print(f"  [page_links] 错误: {e}", file=sys.stderr)
            continue

    return sorted(all_links)


def main():
    parser = argparse.ArgumentParser(
        description="FreeCrawl Map — URL 发现（sitemap → robots.txt → 页面链接）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python map.py https://example.com
  python map.py https://example.com --depth 2
  python map.py https://example.com -o urls.json --format json
  python map.py https://blocked.com --proxy http://127.0.0.1:6738
        """,
    )
    parser.add_argument("url", help="目标站点 URL")
    parser.add_argument("--depth", "-d", type=int, default=1, help="页面链接发现深度 (默认: 1)")
    parser.add_argument("--proxy", "-p", default=DEFAULT_PROXY, help="代理地址")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help=f"请求超时秒数 (默认: {DEFAULT_TIMEOUT})")
    parser.add_argument("--output", "-o", metavar="FILE", help="输出到文件")
    parser.add_argument("--format", "-f", choices=["list", "json"], default="list", help="输出格式 (默认: list)")

    args = parser.parse_args()

    print(f"FreeCrawl Map: {args.url}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    all_results = []

    # Step 1: Try sitemap
    sitemaps = discover_sitemaps(args.url, args.proxy, args.timeout)

    if sitemaps:
        for sm_url in sitemaps:
            urls = parse_sitemap(sm_url, args.proxy, args.timeout)
            if urls:
                all_results.append(MapResult(source=f"sitemap:{sm_url}", urls=urls, count=len(urls)))
                print(f"  [sitemap] 发现 {len(urls)} 个 URL", file=sys.stderr)
    else:
        # Step 2: Try robots.txt for sitemap refs
        robots_sitemaps = get_robots_txt_urls(args.url, args.proxy, args.timeout)
        for sm_url in robots_sitemaps:
            try:
                urls = parse_sitemap(sm_url, args.proxy, args.timeout)
                if urls:
                    all_results.append(MapResult(source=f"sitemap(from robots.txt):{sm_url}", urls=urls, count=len(urls)))
                    print(f"  [sitemap(robots)] 发现 {len(urls)} 个 URL", file=sys.stderr)
            except Exception:
                pass

    # Step 3: Page link discovery
    page_links = discover_page_links(args.url, args.depth, args.proxy, args.timeout)
    if page_links:
        all_results.append(MapResult(source="page_links", urls=page_links, count=len(page_links)))
        print(f"  [page_links] 发现 {len(page_links)} 个 URL", file=sys.stderr)

    # Output
    if args.format == "json":
        output_data = {
            "base_url": args.url,
            "sources": [asdict(r) for r in all_results],
            "total_unique_urls": len(set().union(*[r.urls for r in all_results])),
        }
        json_str = json.dumps(output_data, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(json_str)
        else:
            print(json_str)
    else:
        # Flat list format
        seen = set()
        lines = []
        for result in all_results:
            lines.append(f"# Source: {result.source} ({result.count} URLs)")
            for url in result.urls:
                if url not in seen:
                    seen.add(url)
                    lines.append(url)
            lines.append("")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        else:
            print("\n".join(lines))

    # Summary to stderr
    total = len(set().union(*[r.urls for r in all_results]))
    print(f"\n总计: {total} 个唯一 URL (来自 {len(all_results)} 个来源)", file=sys.stderr)


if __name__ == "__main__":
    main()
