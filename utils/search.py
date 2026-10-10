"""
utils/search.py
Web search utility using DuckDuckGo (no API key needed).
Helps verify AI responses against real-world data.
"""

import logging
import asyncio
from typing import List, Dict, Optional

import aiohttp

log = logging.getLogger("roselinne.search")


class WebSearch:
    """Search the web using DuckDuckGo API (free, no key required)."""

    def __init__(self):
        self.base_url = "https://api.duckduckgo.com/"
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def search(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
        """
        Search for a query and return top results.
        Returns list of dicts with 'title', 'url', 'snippet'.
        """
        try:
            params = {
                "q": query,
                "format": "json",
                "no_redirect": 1,
                "max_results": max_results,
            }

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(self.base_url, params=params) as resp:
                    if resp.status != 200:
                        log.warning(f"Search failed with status {resp.status}")
                        return []

                    data = await resp.json()
                    results = []

                    # Extract results from DuckDuckGo response
                    if "Results" in data:
                        for item in data["Results"][:max_results]:
                            results.append({
                                "title": item.get("Title", ""),
                                "url": item.get("FirstURL", ""),
                                "snippet": item.get("Text", ""),
                            })

                    return results

        except asyncio.TimeoutError:
            log.warning("Search request timed out")
            return []
        except Exception as e:
            log.error(f"Search error: {e}")
            return []

    async def search_for_verification(self, question: str) -> str:
        """
        Search for information to verify an answer.
        Returns formatted search results as a string.
        """
        results = await self.search(question, max_results=3)

        if not results:
            return ""

        formatted = "\n---SEARCH RESULTS---\n"
        for i, result in enumerate(results, 1):
            formatted += f"\n[{i}] {result['title']}\n"
            if result['snippet']:
                formatted += f"    {result['snippet'][:200]}...\n"
            formatted += f"    Source: {result['url']}\n"

        return formatted
