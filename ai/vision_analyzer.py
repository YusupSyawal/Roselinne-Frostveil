"""
ai/vision_analyzer.py
Analyze images using AI vision capabilities.
Supports OpenAI GPT-4 Vision and Google Gemini Vision.
"""

import logging
import base64
from typing import Optional, List, Dict

from config.settings import BotSettings

log = logging.getLogger("roselinne.vision")


class VisionAnalyzer:
    """
    Analyze images using AI providers with vision capabilities.
    Supports: OpenAI (GPT-4V), Gemini (multimodal)
    Not supported: Groq, Ollama (text-only)
    """

    def __init__(self, settings: BotSettings):
        self.settings = settings
        self.provider = settings.ai_provider

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: str = "Describe this image briefly.",
    ) -> Optional[str]:
        """
        Analyze image and return AI description/analysis.
        
        Args:
            image_data: Raw image bytes
            prompt: What to ask about the image
            
        Returns:
            Analysis text or None if failed
        """
        if self.provider == "openai":
            return await self._analyze_openai(image_data, prompt)
        elif self.provider == "gemini":
            return await self._analyze_gemini(image_data, prompt)
        else:
            log.warning(f"Vision not supported for provider: {self.provider}")
            return None

    async def _analyze_openai(self, image_data: bytes, prompt: str) -> Optional[str]:
        """Analyze image using OpenAI GPT-4 Vision."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            log.error("openai package not installed")
            return None

        api_key = self.settings.openai_api_key
        if not api_key:
            log.error("OPENAI_API_KEY not set")
            return None

        try:
            client = AsyncOpenAI(api_key=api_key)
            
            # Convert image to base64
            image_b64 = base64.b64encode(image_data).decode("utf-8")
            
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=1000,
                temperature=0.8,
            )

            return response.choices[0].message.content or None

        except Exception as e:
            log.error(f"OpenAI vision error: {e}")
            return None

    async def _analyze_gemini(self, image_data: bytes, prompt: str) -> Optional[str]:
        """Analyze image using Google Gemini Vision."""
        try:
            import google.generativeai as genai
        except ImportError:
            log.error("google-generativeai package not installed")
            return None

        api_key = self.settings.gemini_api_key
        if not api_key:
            log.error("GEMINI_API_KEY not set")
            return None

        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(self.settings.gemini_model)
            
            # Convert image to PIL Image
            from PIL import Image
            from io import BytesIO
            
            img = Image.open(BytesIO(image_data))
            
            response = model.generate_content(
                [prompt, img],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=1000,
                    temperature=0.8,
                )
            )

            return response.text or None

        except Exception as e:
            log.error(f"Gemini vision error: {e}")
            return None

    @staticmethod
    def is_vision_supported(provider: str) -> bool:
        """Check if provider supports image vision analysis."""
        return provider.lower() in ("openai", "gemini")

    @staticmethod
    def get_vision_providers() -> List[str]:
        """Get list of providers that support vision."""
        return ["openai", "gemini"]
