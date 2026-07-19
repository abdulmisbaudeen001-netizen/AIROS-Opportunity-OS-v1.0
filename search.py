"""
AIROS Opportunity OS v1.0
Search Engine — discovers opportunities across all categories.
Provider is abstracted: swap the backend without touching the Planner.
"""

import logging
from typing import Optional
import httpx
from browser import browser
from config import config
from llm import llm
from prompts import prompts
from utils import Result, opportunity_hash, clean_text

logger = logging.getLogger("airos.search")

TIMEOUT = 30


class SearchProvider:
    """Base interface for all search providers."""

    def search(self, query: str, category: str) -> list[dict]:
        raise NotImplementedError


class BraveSearchProvider(SearchProvider):
    """Brave Search API provider."""

    def search(self, query: str, category: str) -> list[dict]:
        if not config.brave_api_key:
            return []
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                r = client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": 10},
                    headers={"Accept": "application/json", "X-Subscription-Token": config.brave_api_key},
                )
            if r.status_code != 200:
                logger.warning(f"Brave search failed: {r.status_code}")
                return []
            results = r.json().get("web", {}).get("results", [])
            return [{"title": i.get("title", ""), "url": i.get("url", ""), "snippet": i.get("description", "")} for i in results]
        except Exception as e:
            logger.error(f"Brave search error: {e}")
            return []


class TavilySearchProvider(SearchProvider):
    """Tavily Search API provider."""

    def search(self, query: str, category: str) -> list[dict]:
        if not config.tavily_api_key:
            return []
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                r = client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": config.tavily_api_key, "query": query, "max_results": 10},
                    headers={"Content-Type": "application/json"},
                )
            if r.status_code != 200:
                return []
            results = r.json().get("results", [])
            return [{"title": i.get("title", ""), "url": i.get("url", ""), "snippet": i.get("content", "")} for i in results]
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return []


class BrowserSearchProvider(SearchProvider):
    """Fallback: use Browserless to search Google/Bing."""

    def search(self, query: str, category: str) -> list[dict]:
        import urllib.parse
        q = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={q}&num=10"
        result = browser.get_page_content(url, wait_ms=2000)
        if not result.ok():
            return []
        text = result.data.get("text", "")
        # LLM extracts structured results from raw page text
        extracted = llm.generate_json(
            prompt=f"Extract the top search results from this Google search page text. Return JSON with key 'results' containing a list of {{title, url, snippet}} objects.\n\nPage text:\n{text[:3000]}",
        )
        if extracted:
            return extracted.get("results", [])
        return []


class SearchEngine:
    """
    Provider-abstracted search engine.
    Tries providers in priority order, merges and deduplicates results.
    """

    def __init__(self):
        self._providers: list[SearchProvider] = []
        self._init_providers()

    def _init_providers(self):
        if config.brave_api_key:
            self._providers.append(BraveSearchProvider())
            logger.info("Search: Brave provider enabled")
        if config.tavily_api_key:
            self._providers.append(TavilySearchProvider())
            logger.info("Search: Tavily provider enabled")
        self._providers.append(BrowserSearchProvider())
        logger.info("Search: Browser fallback provider enabled")

    def search(self, query: str, category: str = "job") -> list[dict]:
        """Search using available providers, return merged raw results."""
        all_results = []
        seen_urls = set()

        for provider in self._providers:
            try:
                results = provider.search(query, category)
                for r in results:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        r["category"] = category
                        all_results.append(r)
                if all_results:
                    break  # First provider with results wins
            except Exception as e:
                logger.warning(f"Search provider {type(provider).__name__} failed: {e}")
                continue

        return all_results

    def search_all_categories(self, profile_summary: str, intent: str) -> list[dict]:
        """
        Generate smart queries from profile and run searches across all opportunity types.
        Returns merged raw search results.
        """
        query_data = llm.generate_json(
            prompt=prompts.SEARCH_QUERIES.format(
                profile_summary=profile_summary,
                intent=intent,
            )
        )
        if not query_data or "queries" not in query_data:
            logger.warning("Failed to generate search queries from LLM.")
            return []

        all_results = []
        seen_urls = set()

        for q in query_data["queries"]:
            query = q.get("query", "")
            category = q.get("category", "job")
            if not query:
                continue
            logger.info(f"Searching: [{category}] {query}")
            results = self.search(query, category)
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)

        logger.info(f"Search complete: {len(all_results)} raw results")
        return all_results

    def fetch_opportunity_detail(self, url: str) -> Result:
        """Fetch and extract full opportunity details from a URL."""
        result = browser.get_page_content(url, wait_ms=2000)
        if not result.ok():
            return Result.failed(f"Failed to load {url}")

        text = clean_text(result.data.get("text", ""))[:5000]
        parsed = llm.generate_json(
            prompt=prompts.OPPORTUNITY_PARSE.format(text=text),
            temperature=0.1,
        )
        if not parsed:
            return Result.failed("Failed to parse opportunity details")

        parsed["url"] = url
        parsed["hash"] = opportunity_hash(
            parsed.get("title", ""),
            parsed.get("organization", ""),
            url,
        )
        return Result.success(parsed)

    def search_specific_sources(self, category: str, profile_summary: str) -> list[dict]:
        """Search category-specific portals."""
        SOURCE_MAP = {
            "scholarship": [
                "site:scholarshipportal.com",
                "site:opportunitydesk.org scholarships",
                "fully funded scholarship",
            ],
            "fellowship": [
                "site:opportunitydesk.org fellowship",
                "fully funded fellowship program",
            ],
            "grant": [
                "research grant application open",
                "startup grant program",
            ],
            "competition": [
                "AI competition 2024 prize",
                "hackathon prize money",
            ],
            "bootcamp": [
                "fully funded coding bootcamp",
                "free tech bootcamp application",
            ],
            "conference": [
                "conference travel grant",
                "free conference ticket researcher",
            ],
        }
        queries = SOURCE_MAP.get(category, [f"{category} opportunities"])
        results = []
        for q in queries:
            results.extend(self.search(q, category))
        return results


# Singleton
search_engine = SearchEngine()
