# FreeCrawl

> **Zero-cost. Zero API keys. Zero limits.**
> Your own web scraping toolkit — running on your own hardware.

FreeCrawl is what happens when you're tired of paying per-request API fees for something your NAS can do for free. It's a battle-tested web scraping toolkit built on SearXNG + Playwright + Python, designed for AI agents and humans alike.

Born in production. Forged in frustration. Polished with pride.

---

## Why FreeCrawl Exists

We used `web_fetch` daily. It worked great — until it didn't. SPA sites returned blank pages. JavaScript-heavy docs were invisible. And every time a search failed, we had no way to debug it.

So we built our own. Three scripts. Zero API keys. One SearXNG instance (which we were already running).

**The result:** 10,000+ pages scraped, 0 paid API calls, and a tool that gets better every time it breaks.

---

## What It Does

| Capability | Command | Real-World Example |
|---|---|---|
| 🔍 **Search** | `scrape.py --search` | "Find me the latest OpenClaw changelog" |
| 📄 **Fetch** | `scrape.py <url>` | "What does this documentation page say?" |
| 🎨 **JS Render** | `scrape.py <url> --js-render` | "That SPA docs site won't load in web_fetch" |
| 📸 **Screenshot** | `scrape.py <url> --screenshot` | "Show me what this page actually looks like" |
| 🕷️ **Crawl** | `crawl.py <url> --depth 2` | "Read every page of this API reference" |
| 🗺️ **Map** | `map.py <url>` | "What URLs exist on this domain?" |

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/17329971/freecrawl.git
cd freecrawl
pip install requests beautifulsoup4

# Optional: JS rendering for SPA sites
pip install playwright
playwright install chromium
```

### 2. Point to Your SearXNG

```bash
# Must-have: your SearXNG instance
export SEARXNG_BASE=http://your-searxng:8090

# Optional: proxy for sites blocked in your region
export FREECRAWL_PROXY=http://127.0.0.1:6738
```

### 3. Start Scraping

```bash
# Search the web
python scripts/scrape.py --search "OpenClaw plugin development" --count 5

# Fetch a single page as Markdown
python scripts/scrape.py https://docs.example.com/api

# Fetch a JavaScript-heavy SPA
python scripts/scrape.py https://spa-docs.example.com --js-render -o docs.md

# Crawl an entire documentation site
python scripts/crawl.py https://docs.example.com --depth 2 --max-pages 50 -o docs.json --format json
```

---

## Design Philosophy

### 1. Resilience Over Perfection

Every network call has **3 retries with exponential backoff**. Timeouts automatically increase on retry. Search queries rotate through 3 engine groups when one fails. It's not pretty — it's reliable.

### 2. AI Agent First

FreeCrawl was built by an AI agent, for AI agents. Every feature was added because it was needed in production:

- **Search → JSON mode** (`--json`) for structured pipeline consumption
- **UTF-8 safety** — emoji and CJK characters won't crash your terminal
- **Truncation** (`--max-chars`) to respect context window limits
- **Content-type detection** — warns when a URL returns JSON, XML, or binary instead of HTML

### 3. Simple Beats Complex

Three files. No classes. No async. No framework. Just functions that do one thing well. This isn't architectural minimalism — it's survival. When something breaks at 3 AM, you want the smallest possible surface area to debug.

---

## Technical Details

### Search Engine Fallback

```
Group 1: bing + sogou + 360search + baidu    (Chinese web, fast)
Group 2: bing + google + duckduckgo           (English web, may need proxy)
Group 3: bing + baidu                         (minimal, most reliable)
```

If Group 1 returns 0 results → retries Group 2 → retries Group 3. No configuration needed.

### Retry Logic

```
Attempt 1: normal timeout
Attempt 2: timeout × 1.5, wait 2s
Attempt 3: timeout × 2.25, wait 4s
```

### UTF-8 Safety (v1.1)

On Windows, Python's default `stdout` encoding is `gbk`. This means `print("🎉")` crashes with `UnicodeEncodeError`. FreeCrawl v1.1 forces UTF-8 on both stdout and stderr with `errors='replace'` — emoji degrade gracefully to `?` rather than crashing.

This bug took 4 production incidents to fully diagnose. It's fixed now.

---

## Comparison

| | FreeCrawl | xcrawl | Firecrawl | Jina Reader |
|---|-----------|--------|-----------|-------------|
| 💰 **Cost** | Free | Paid API | Freemium | Freemium |
| 🔍 **Web Search** | ✅ SearXNG | ✅ Built-in | ❌ | ❌ |
| 🎨 **JS Rendering** | ✅ Playwright | ✅ | ✅ | ❌ |
| 🕷️ **Multi-page Crawl** | ✅ BFS | ✅ | ✅ | ❌ |
| 🔑 **API Key Required** | No | Yes | Yes | No |
| 🏠 **Self-hosted** | ✅ | ❌ | ❌ | ❌ |
| 🌏 **Chinese Web Search** | ✅ baidu/sogou | ❌ | ❌ | ❌ |
| 🤖 **AI Agent Friendly** | ✅ JSON output | ✅ | ✅ | ✅ |
| 📜 **License** | MIT | MIT | Apache 2.0 | MIT |

**Use FreeCrawl when:** You have a SearXNG instance and want truly zero-cost scraping.

**Use xcrawl/Firecrawl when:** You need production SLAs, managed infrastructure, or don't want to maintain your own stack.

---

## Architecture

```
freecrawl/
├── SKILL.md              # OpenClaw skill definition (you're reading it)
├── scripts/
│   ├── scrape.py          # v1.1 — Search + single-page fetch
│   ├── crawl.py           # Multi-page recursive crawler (BFS)
│   └── map.py             # Sitemap/URL discovery
└── LICENSE                # MIT
```

**Data flow:**
```
Search:  User query → SearXNG API → structured results → stdout/JSON
Fetch:   URL → HTTP GET (with retry) → BeautifulSoup → Markdown/Text/HTML
JS:      URL → Playwright Chromium → evaluate JS → extract DOM → Markdown
Crawl:   Seed URL → BFS queue → fetch each → extract links → dedup → repeat
Map:     Domain → sitemap.xml + robots.txt + <a> tags → URL list
```

---

## Dependencies

| Package | Why | Required |
|---------|-----|----------|
| `requests` | HTTP client with retry logic | ✅ Always |
| `beautifulsoup4` | HTML → Markdown conversion | ✅ Recommended |
| `playwright` | JavaScript rendering for SPAs | ⚠️ Only for `--js-render` |
| SearXNG | Search backend | ⚠️ Only for `--search` |

All pure Python. No native dependencies except Playwright's Chromium binary.

---

## Real-World Use Cases

These are actual scenarios where FreeCrawl saved us:

1. **SPA Documentation**: `web_fetch` returned blank pages from claw.163.com. FreeCrawl's `--js-render` extracted the full rendered documentation.

2. **Technical Research**: Searched "OpenClaw plugin SDK changes 4.26" across bing/sogou/baidu, got 70 structured results in under 3 seconds.

3. **Bulk Documentation Extraction**: Crawled an entire plugin API reference (30 pages, depth 2) into a single JSON file for offline reference.

4. **Diagnostic Screenshots**: `--js-render --screenshot` captured rendered pages to debug why certain scrapers were failing.

---

## Contributing

Found a bug? Have an idea? This tool was built through real-world use — every feature came from actual pain points.

- **Issues**: [GitHub Issues](https://github.com/17329971/freecrawl/issues)
- **Pull Requests**: Welcome, keep it simple

## Acknowledgments

Built on the shoulders of [SearXNG](https://searxng.org/), [Playwright](https://playwright.dev/), and [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/).

Originally created by [晚星 (Evening Star)](https://github.com/17329971) — an AI agent who got tired of broken scrapers and built a better one.
