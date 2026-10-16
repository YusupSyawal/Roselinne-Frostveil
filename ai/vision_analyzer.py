"""
ai/vision_analyzer.py
Analyze images using Groq, OpenAI, or Google Gemini vision models.
"""

import asyncio
import base64
import logging
from contextvars import ContextVar
from typing import List, Optional

import aiohttp

from config.settings import BotSettings
from utils.usage_monitor import UsageMonitor, estimate_tokens

log = logging.getLogger("roselinne.vision")


class VisionAnalyzer:
    """Analyze image bytes and return a concise response without crashing the bot."""

    MAX_IMAGE_SIZE = 20 * 1024 * 1024
    REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10)

    def __init__(
        self,
        settings: BotSettings,
        usage_monitor: UsageMonitor | None = None,
    ):
        self.settings = settings
        self.provider = settings.ai_provider
        self.usage_monitor = usage_monitor
        self._usage_metadata: ContextVar[dict[str, int]] = ContextVar(
            "vision_usage_metadata", default={}
        )

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: str = "Describe this image briefly.",
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> Optional[str]:
        """Analyze an image, returning None for unsupported or failed requests."""
        if not image_data or len(image_data) > self.MAX_IMAGE_SIZE:
            log.warning("Vision image is empty or exceeds the 20 MB request limit")
            return None

        prompt = f"{prompt}\n\n{self._identity_prompt(username, display_name, user_id)}"
        self._usage_metadata.set({})
        if self.provider == "groq":
            result = await self._analyze_groq(image_data, prompt)
        elif self.provider == "openai":
            result = await self._analyze_openai(image_data, prompt)
        elif self.provider == "gemini":
            result = await self._analyze_gemini(image_data, prompt)
        else:
            log.warning("Vision not supported for provider: %s", self.provider)
            result = None
        if self.usage_monitor is not None:
            metadata = self._usage_metadata.get()
            try:
                await self.usage_monitor.record(
                    guild_id=guild_id,
                    user_id=user_id,
                    provider=self.provider,
                    model=self._active_model,
                    input_tokens=metadata.get("input_tokens", estimate_tokens(prompt)),
                    output_tokens=metadata.get("output_tokens", estimate_tokens(result or "")),
                    input_token_source="actual" if "input_tokens" in metadata else "estimated",
                    output_token_source="actual" if "output_tokens" in metadata else "estimated",
                    success=result is not None,
                    request_id=request_id,
                )
            except Exception:
                log.exception("Could not persist local vision usage request_id=%s", request_id)
        return result

    @property
    def _active_model(self) -> str:
        return {
            "groq": self.settings.groq_vision_model,
            "openai": self.settings.openai_model,
            "gemini": self.settings.gemini_model,
        }.get(self.provider, "Tidak tersedia")

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
        usage = data.get("usage", {})
        if usage:
            self._usage_metadata.set({
                "input_tokens": usage.get("prompt_tokens", 0) or 0,
                "output_tokens": usage.get("completion_tokens", 0) or 0,
            })
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
            usage = getattr(response, "usage", None)
            if usage is not None:
                self._usage_metadata.set({
                    "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                })
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
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                self._usage_metadata.set({
                    "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                    "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
                })
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
