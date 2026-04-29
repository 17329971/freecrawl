---
name: freecrawl
description: "Zero-cost web scraping with search, single-page fetch, multi-page crawl, and URL discovery. Use when you need to search the web via SearXNG, extract content from web pages as Markdown/HTML/text, render JavaScript-heavy pages with Playwright, recursively crawl multi-page documentation sites, or discover all URLs on a site via sitemap.xml. Based on SearXNG + Playwright + requests — no API key required."
---

# FreeCrawl

> Zero-cost web scraping toolkit — search, fetch, crawl, and map the web.
> No API key. No subscription. Just your own infrastructure.

FreeCrawl is a free, open-source alternative to commercial web scraping APIs (xcrawl, Firecrawl, etc.). It combines SearXNG for search, Playwright for JS rendering, and Python for everything else — all running on your own hardware.

## ✨ Features

| Capability | Tool | Description |
|-----------|------|-------------|
| 🔍 **Search** | `scrape.py search` | Keyword search via SearXNG with engine fallback + JSON output |
| 📄 **Fetch** | `scrape.py fetch` | Single-page extraction to clean Markdown/HTML/Text |
| 🎨 **JS Render** | `scrape.py fetch --js-render` | Playwright-powered rendering for SPA/JS-heavy sites |
| 📸 **Screenshot** | `scrape.py fetch --screenshot` | Full-page screenshots (requires JS render) |
| 🕷️ **Crawl** | `crawl.py` | Recursive BFS crawling with depth control and dedup |
| 🗺️ **Map** | `map.py` | URL discovery via sitemap.xml, robots.txt, and link extraction |

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- SearXNG instance (self-hosted or public)
- v1.1 (UTF-8 safe, retry, engine fallback, JSON output)

### Installation

```bash
# Clone or copy the freecrawl directory
git clone https://github.com/YOUR_USER/freecrawl.git
cd freecrawl

# Install dependencies
pip install requests beautifulsoup4

# Optional: for JS rendering
pip install playwright
python -m playwright install chromium
```

### Configuration

Set environment variables or use defaults:

```bash
# SearXNG endpoint (default: local network)
export SEARXNG_BASE=http://192.168.18.43:8090

# Optional: proxy for blocked sites
export FREECRAWL_PROXY=http://127.0.0.1:6738

# Optional: custom user agent
export FREECRAWL_USER_AGENT="FreeCrawl/1.0"
```

## 📖 Usage

### Search

```bash
# Basic search
python scripts/scrape.py search "machine learning tutorial" --count 5

# Custom search engines
python scripts/scrape.py search "python async" --engines bing,google --count 10
```

### Fetch (Single Page)

```bash
# Extract to Markdown (default)
python scripts/scrape.py fetch "https://example.com/article"

# Plain text output
python scripts/scrape.py fetch "https://example.com" --format text

# Raw HTML
python scripts/scrape.py fetch "https://example.com" --format html

# Render JavaScript SPA
python scripts/scrape.py fetch "https://spa-site.com" --js-render

# With full-page screenshot
python scripts/scrape.py fetch "https://example.com" --js-render --screenshot page.png

# Use proxy for blocked sites
python scripts/scrape.py fetch "https://blocked.com" --proxy http://127.0.0.1:6738

# Save to file with character limit
python scripts/scrape.py fetch "https://docs.example.com" -o result.md --max-chars 10000

# Long timeout for slow sites
python scripts/scrape.py fetch "https://slow-site.com" --timeout 60
```

### Crawl (Multi-Page)

```bash
# Recursive crawl with depth control
python scripts/crawl.py "https://docs.example.com" --depth 2 --max-pages 30

# Output as JSON for processing
python scripts/crawl.py "https://blog.example.com" --depth 1 --max-pages 10 -o posts.json --format json

# Crawl with delay to avoid rate limiting
python scripts/crawl.py "https://example.com" --depth 2 --delay 2
```

### Map (URL Discovery)

```bash
# Discover all URLs on a site
python scripts/map.py "https://example.com" --depth 0 --format list

# JSON output
python scripts/map.py "https://example.com" --format json -o urls.json
```

## 🔧 Architecture

```
freecrawl/
├── SKILL.md              # OpenClaw skill definition
├── scripts/
│   ├── scrape.py         # Search + single-page fetch
│   ├── crawl.py          # Multi-page recursive crawler
│   └── map.py            # Sitemap/URL discovery
```

### How It Works

1. **Search** → Calls SearXNG JSON API → returns structured results (title, URL, snippet)
2. **Fetch** → HTTP GET → HTML → BeautifulSoup cleaning → Markdown/Text/HTML output
3. **JS Render** → Playwright Chromium → evaluates JavaScript → extracts rendered DOM
4. **Crawl** → BFS traversal → per-page fetch → link extraction → dedup → repeat
5. **Map** → Checks sitemap.xml + robots.txt → extracts all `<a href>` links

## ⚖️ Comparison

| | FreeCrawl | xcrawl | Firecrawl |
|---|-----------|--------|-----------|
| 💰 **Price** | Free | Paid API | Freemium |
| 🔍 **Search** | SearXNG | Built-in | ❌ |
| 🎨 **JS Render** | Playwright | ✅ | ✅ |
| 🕷️ **Crawl** | BFS built-in | ✅ | ✅ |
| 🔑 **API Key** | None | Required | Required |
| 🏠 **Self-hosted** | ✅ | ❌ | ❌ |
| 📜 **License** | MIT | MIT | Apache 2.0 |

## 🛠️ Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| `requests` | HTTP client | ✅ Always |
| `beautifulsoup4` | HTML parsing | ✅ Recommended |
| `playwright` | JS rendering | ⚠️ Optional |
| SearXNG | Search backend | ⚠️ For search only |

## 📝 License

MIT — do whatever you want, just keep the license notice.

## 🙏 Acknowledgments

Built with [SearXNG](https://searxng.org/), [Playwright](https://playwright.dev/), and [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/).
