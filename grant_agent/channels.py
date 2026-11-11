"""Search channels. Each returns a list of Lead dicts with the same keys."""
import datetime as dt
import html
import json
import urllib.request

from composio import Composio

from . import config

composio = Composio(toolkit_versions={"composio_search": "latest", "gmail": "latest"})


def run_tool(slug, args, user_id=None):
    """Run one Composio tool directly and return its data (raise on failure)."""
    result = composio.tools.execute(
        slug,
        args,
        user_id=user_id or config.USER_ID,
        dangerously_skip_version_check=True,
    )
    if not result.get("successful"):
        raise RuntimeError(f"{slug} failed: {result.get('error')}")
    return result["data"]


def lead(title, url, snippet, channel, deadline=None, funder=""):
    return {
        "title": " ".join(html.unescape(title or "").split()),
        "url": url,
        "snippet": (snippet or "")[:500],
        "channel": channel,
        "deadline": deadline,
        "funder": funder,
    }


def search_grants_gov(query, rows=10):
    """Grants.gov public API: posted grants open to 501(c)(3) nonprofits."""
    body = json.dumps(
        {"keyword": query, "oppStatuses": "posted", "eligibilities": "12", "rows": rows}
    ).encode()
    req = urllib.request.Request(
        "https://api.grants.gov/v1/api/search2",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        hits = json.load(resp)["data"]["oppHits"]
    leads = []
    for h in hits:
        close = h.get("closeDate")
        deadline = dt.datetime.strptime(close, "%m/%d/%Y").date() if close else None
        leads.append(
            lead(
                h["title"],
                f"https://www.grants.gov/search-results-detail/{h['id']}",
                f"{h['agency']} | {h['number']}",
                "grants_gov",
                deadline=deadline,
                funder=h["agency"],
            )
        )
    return leads


def search_tavily(query, max_results=8):
    data = run_tool(
        "COMPOSIO_SEARCH_TAVILY",
        {"query": query, "max_results": max_results, "include_answer": False},
    )
    return [
        lead(r["title"], r["url"], r.get("content"), "tavily")
        for r in data.get("results", [])
    ]


def search_duckduckgo(query):
    data = run_tool("COMPOSIO_SEARCH_DUCK_DUCK_GO", {"query": query})
    return [
        lead(r["title"], r["link"], r.get("snippet"), "duckduckgo")
        for r in data.get("results", [])
    ]


def search_news(query, when="1m"):
    data = run_tool("COMPOSIO_SEARCH_NEWS", {"query": query, "when": when})
    return [
        lead(r.get("title"), r.get("link"), r.get("snippet") or r.get("source"), "news")
        for r in data.get("news_results") or []
        if r.get("link")
    ]


def find_similar(url, num_results=5):
    """Exa 'find similar pages': the dig-deeper move from one good grant page."""
    data = run_tool(
        "COMPOSIO_SEARCH_EXA_SIMILARLINK", {"url": url, "numResults": num_results}
    )
    results = data.get("results", {})
    if isinstance(results, dict):
        results = results.get("results", [])
    return [lead(r.get("title"), r["url"], "", "exa_similar") for r in results]


def fetch_page(url, max_characters=8000):
    """Read a page as clean text (Exa fetch through Composio, no summary)."""
    data = run_tool(
        "COMPOSIO_SEARCH_FETCH_URL_CONTENT",
        {"urls": [url], "text": True, "max_characters": max_characters},
    )
    results = data.get("results") or [{}]
    return results[0].get("text") or ""


# Query templates per channel. {topic} is filled from the chosen angle.
CHANNELS = {
    "grants_gov": (search_grants_gov, ["{kw}"]),
    "tavily": (
        search_tavily,
        ["{topic} applications due 2027", "{topic} apply now deadline nonprofit"],
    ),
    "duckduckgo": (
        search_duckduckgo,
        ["{topic} 2027 deadline", "{topic} grant application open nonprofit"],
    ),
    "news": (search_news, ["{topic} now accepting applications"]),
}

# Short keyword per angle for Grants.gov (its search wants keywords, not sentences).
GRANTS_GOV_KEYWORDS = {
    "youth_education": "youth",
    "food_security": "food",
    "community_foundation": "community",
    "corporate": "nonprofit capacity",
}
