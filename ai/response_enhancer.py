"""
ai/response_enhancer.py
Wraps the AI client to enhance responses with verification and web search.
Provides higher-level response generation with quality assurance.
"""

import logging
from typing import List, Dict, Optional

from ai.ai_client import AIClient
from ai.verifier import ResponseVerifier

log = logging.getLogger("roselinne.enhancer")


class ResponseEnhancer:
    """
    Wraps AIClient to provide enhanced responses with verification.
    Handles verification, error correction, and accuracy checking.
    """

    def __init__(self, ai_client: AIClient):
        self.ai = ai_client
        self.verifier = ResponseVerifier()

    async def generate_verified_response(
        self,
        messages: List[Dict[str, str]],
        question: str,
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> str:
        """
        Generate an AI response and optionally verify it against web sources.

        Steps:
        1. Get initial response from AI
        2. Search the web for the question
        3. Return verified/enhanced response
        """
        # Get initial response
        try:
            initial_response = await self.ai.chat(
                messages,
                username=username,
                display_name=display_name,
                user_id=user_id,
                guild_id=guild_id,
                request_id=request_id,
            )
        except RuntimeError as e:
            log.error(f"Failed to generate response: {e}")
            raise

        # Verify and enhance
        verified_response = await self.verifier.verify_and_enhance(
            question=question,
            initial_response=initial_response,
            ai_client=self.ai,
        )

        return verified_response

    async def generate_with_confidence(
        self,
        messages: List[Dict[str, str]],
        question: str,
    ) -> tuple[str, float]:
        """
        Generate response and return confidence score (0.0-1.0).

        Returns (response, confidence_score).
        Confidence is higher for factual questions with verified sources.
        """
        response = await self.generate_verified_response(messages, question)

        # Check factual accuracy
        is_accurate, correction = await self.verifier.check_factual_accuracy(
            question=question,
            response=response,
        )

        confidence = 1.0 if is_accurate else 0.5
        return (response, confidence)

    def enable_verification(self, enabled: bool) -> None:
        """Toggle web verification on/off."""
        self.verifier.enable_verification(enabled)
        log.info("Response verification %s", "enabled" if enabled else "disabled")
