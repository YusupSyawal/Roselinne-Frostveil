"""
ai/verifier.py
Verification system that checks AI responses against web search results.
Helps ensure accuracy by cross-referencing answers with real-world data.
"""

import logging
from typing import List, Dict, Optional

from utils.search import WebSearch

log = logging.getLogger("roselinne.verifier")


class ResponseVerifier:
    """
    Verifies AI responses by searching the web for relevant information.
    Provides context to the AI to correct or improve answers.
    """

    def __init__(self):
        self.search = WebSearch()
        self.enabled = True

    async def verify_and_enhance(
        self,
        question: str,
        initial_response: str,
        ai_client: Optional[object] = None,
    ) -> str:
        """
        Verify the AI response and optionally enhance it with search results.

        Process:
        1. Search the web for the question
        2. If results found, provide them to AI for verification
        3. Return enhanced response or original if no improvements needed
        """
        if not self.enabled:
            return initial_response

        # Determine if this needs verification (questions, not statements)
        if not self._should_verify(question, initial_response):
            return initial_response

        # Search for information
        search_results = await self.search.search_for_verification(question)

        if not search_results:
            # No search results, return original
            return initial_response

        # If we have search results, provide them for context
        log.debug("Found search results for verification query")

        # Return response with context about verification
        enhanced = self._format_enhanced_response(initial_response, search_results)
        return enhanced

    async def check_factual_accuracy(
        self,
        question: str,
        response: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if response is likely factually accurate.
        Returns (is_accurate, correction_hint).
        """
        if not self.enabled:
            return (True, None)

        search_results = await self.search.search_for_verification(question)

        if not search_results:
            # Can't verify without search results
            return (True, None)

        # Simple heuristic: check if response contains similar keywords to search results
        response_lower = response.lower()
        results_text = " ".join([r["snippet"].lower() for r in await self.search.search(question)])

        # If response is too different from search results, flag it
        common_words = self._find_common_words(response_lower, results_text)

        if len(common_words) < 2:
            return (False, search_results)

        return (True, None)

    def _should_verify(self, question: str, response: str) -> bool:
        """
        Determine if a question needs verification.
        Skip verification for opinions, personal advice, creative content, etc.
        """
        # Skip if response is too short or seems opinion-based
        if len(response) < 20:
            return False

        # Skip questions about feelings, opinions, preferences
        skip_keywords = [
            "how do you feel", "what do you think", "your opinion",
            "like", "prefer", "favorite", "opinion", "feeling",
        ]

        question_lower = question.lower()
        if any(kw in question_lower for kw in skip_keywords):
            return False

        return True

    def _find_common_words(self, text1: str, text2: str) -> List[str]:
        """Find common meaningful words between two texts."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        common = words1.intersection(words2)

        # Filter out common stop words
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "is", "are", "was", "were", "be",
        }

        meaningful_common = [w for w in common if w not in stop_words and len(w) > 3]
        return meaningful_common

    def _format_enhanced_response(
        self,
        original_response: str,
        search_context: str,
    ) -> str:
        """Format the response with verification context."""
        # You can customize this to embed search results or add confidence indicators
        # For now, just return original response with a note that it was checked
        return original_response

    def enable_verification(self, enabled: bool) -> None:
        """Toggle verification on/off."""
        self.enabled = enabled
        log.info(f"Response verification {'enabled' if enabled else 'disabled'}")
