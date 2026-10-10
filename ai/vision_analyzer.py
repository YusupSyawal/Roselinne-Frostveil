"""
ai/vision_analyzer.py
Analyze images using Groq, OpenAI, or Google Gemini vision models.
"""

import asyncio
import base64
import logging
from typing import List, Optional

import aiohttp

from config.settings import BotSettings

log = logging.getLogger("roselinne.vision")


class VisionAnalyzer:
    """Analyze image bytes and return a concise response without crashing the bot."""

    MAX_IMAGE_SIZE = 20 * 1024 * 1024
    REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10)

    def __init__(self, settings: BotSettings):
        self.settings = settings
        self.provider = settings.ai_provider

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: str = "Describe this image briefly.",
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Optional[str]:
        """Analyze an image, returning None for unsupported or failed requests."""
        if not image_data or len(image_data) > self.MAX_IMAGE_SIZE:
            log.warning("Vision image is empty or exceeds the 20 MB request limit")
            return None

        prompt = f"{prompt}\n\n{self._identity_prompt(username, display_name, user_id)}"
        if self.provider == "groq":
            return await self._analyze_groq(image_data, prompt)
        if self.provider == "openai":
            return await self._analyze_openai(image_data, prompt)
        if self.provider == "gemini":
            return await self._analyze_gemini(image_data, prompt)

        log.warning("Vision not supported for provider: %s", self.provider)
        return None

    @staticmethod
    def _identity_prompt(
        username: Optional[str],
        display_name: Optional[str],
        user_id: Optional[int],
    ) -> str:
        """Keep Discord identity metadata separate from the image content."""
        resolved_username = (username or "").strip() or "unknown"
        resolved_display_name = (display_name or "").strip() or resolved_username
        resolved_user_id = str(user_id) if user_id is not None else "unknown"
        if resolved_username.casefold() == "yusupjawir":
            personality = (
                "Pengirim adalah yusupjawir, kekasih Roselinne. Tetap singkat, "
                "sedikit lebih hangat, dan boleh menggoda secara halus."
            )
        else:
            personality = (
                "Gunakan persona Roselinne yang dingin, elegan, sedikit sarkastik, "
                "dan ringkas. Jangan romantis atau memakai panggilan sayang."
            )
        return (
            "METADATA PENGIRIM DISCORD (bukan isi gambar): "
            f"Username: {resolved_username}; Display Name: {resolved_display_name}; "
            f"User ID: {resolved_user_id}. {personality} "
            "Jawab hanya dalam Bahasa Indonesia."
        )

    @staticmethod
    def _image_data_url(image_data: bytes) -> str:
        """Build the data URL required by Groq's OpenAI-compatible API."""
        encoded = base64.b64encode(image_data).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    async def _analyze_groq(self, image_data: bytes, prompt: str) -> Optional[str]:
        """Use Groq chat completions with one text and one image content part."""
        if not self.settings.groq_api_key:
            log.error("GROQ_API_KEY is not set")
            return None

        payload = {
            "model": self.settings.groq_vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": self._image_data_url(image_data)},
                        },
                    ],
                }
            ],
            "temperature": 0.8,
            "max_completion_tokens": 512,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession(timeout=self.REQUEST_TIMEOUT) as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status == 429:
                        log.warning("Groq vision rate limit reached")
                        return None
                    if response.status in (400, 404):
                        log.error(
                            "Groq vision request rejected with HTTP %s; "
                            "check GROQ_VISION_MODEL and image format",
                            response.status,
                        )
                        return None
                    if response.status >= 400:
                        log.error("Groq vision API returned HTTP %s", response.status)
                        return None
                    data = await response.json()
        except asyncio.TimeoutError:
            log.warning("Groq vision request timed out")
            return None
        except aiohttp.ClientError as exc:
            log.error("Groq vision network error: %s", exc)
            return None
        except (TypeError, ValueError) as exc:
            log.error("Invalid Groq vision response: %s", exc)
            return None

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            log.error("Groq vision response had an unexpected shape: %s", exc)
            return None
        return content.strip() if isinstance(content, str) and content.strip() else None

    async def _analyze_openai(self, image_data: bytes, prompt: str) -> Optional[str]:
        """Analyze an image using OpenAI's multimodal chat completions."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            log.error("openai package not installed")
            return None

        if not self.settings.openai_api_key:
            log.error("OPENAI_API_KEY not set")
            return None

        try:
            client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": self._image_data_url(image_data),
                                },
                            },
                        ],
                    }
                ],
                max_tokens=1000,
                temperature=0.8,
            )
            return response.choices[0].message.content or None
        except Exception as exc:
            log.error("OpenAI vision error: %s", exc)
            return None

    async def _analyze_gemini(self, image_data: bytes, prompt: str) -> Optional[str]:
        """Analyze an image using Google Gemini Vision."""
        try:
            import google.generativeai as genai
        except ImportError:
            log.error("google-generativeai package not installed")
            return None

        if not self.settings.gemini_api_key:
            log.error("GEMINI_API_KEY not set")
            return None

        try:
            genai.configure(api_key=self.settings.gemini_api_key)
            model = genai.GenerativeModel(self.settings.gemini_model)
            from io import BytesIO
            from PIL import Image

            image = Image.open(BytesIO(image_data))
            response = model.generate_content(
                [prompt, image],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=1000,
                    temperature=0.8,
                ),
            )
            return response.text or None
        except Exception as exc:
            log.error("Gemini vision error: %s", exc)
            return None

    @staticmethod
    def is_vision_supported(provider: str) -> bool:
        """Return whether the configured provider has a vision implementation."""
        return provider.lower() in ("groq", "openai", "gemini")

    @staticmethod
    def get_vision_providers() -> List[str]:
        return ["groq", "openai", "gemini"]
