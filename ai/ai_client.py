"""
ai/ai_client.py
Modular AI client that supports OpenAI, Groq, Gemini, and Ollama.
Provider is selected at runtime from the AI_PROVIDER env variable.
"""

import logging
import re
from contextvars import ContextVar
from typing import Any, List, Dict, Optional

import aiohttp

from config.settings import BotSettings
from utils.usage_monitor import UsageMonitor, estimate_messages_tokens, estimate_tokens

log = logging.getLogger("roselinne.ai")

RESPONSE_STYLE_INSTRUCTION = """\
GAYA OUTPUT:
- PRIORITAS: SHORT > NATURAL > PERSONALITY > DETAIL.
- Gunakan sesedikit mungkin kata. Jika 1 kata cukup, jawab 1 kata.
- Untuk sapaan atau basa-basi, balas singkat saja: "Halo.", "Hm.", atau "Oh."
- Jangan menawarkan bantuan atau bertanya balik setelah sapaan sederhana.
- Batas kata adalah maksimum keras, bukan target. Setelah inti terjawab, STOP.
- Jangan menambahkan penjelasan, penutup, metafora, narasi, suasana, emosi,
  komentar, atau pertanyaan yang tidak diperlukan.
- Jangan membuat paragraf atau kalimat panjang. Untuk casual chat, satu kalimat pendek.
- Jangan mengulang pesan user atau mencoba terdengar pintar, dramatis, atau puitis.
- Personality harus terasa dari pilihan kata singkat, bukan dari respons panjang.
- Sebelum mengirim, hapus setiap kata yang tidak diperlukan dan persingkat lagi jika bisa.
- Hanya jawab lebih panjang jika user meminta penjelasan, analisis, atau jawaban mendalam.
"""     


class AIClient:
    """
    Async AI client with provider abstraction.
    All providers expose the same interface: async chat() → str
    """

    def __init__(
        self,
        settings: BotSettings,
        usage_monitor: UsageMonitor | None = None,
    ):
        self.settings = settings
        self.provider = settings.ai_provider
        self.usage_monitor = usage_monitor
        self._usage_metadata: ContextVar[dict[str, Any] | None] = ContextVar(
            "ai_usage_metadata", default=None
        )
        log.info(f"AI provider: {self.provider}")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> str:
        """
        Send a messages list and return the assistant's text response.
        Raises RuntimeError on unrecoverable errors so callers can surface them.
        """
        tokens = max_tokens or self.settings.max_tokens
        messages = self._apply_response_style(
            messages,
            username=username,
            display_name=display_name,
            user_id=user_id,
        )

        self._usage_metadata.set(None)
        try:
            if self.provider == "openai":
                reply = await self._openai(messages, tokens)
            elif self.provider == "groq":
                reply = await self._groq(messages, tokens)
            elif self.provider == "gemini":
                reply = await self._gemini(messages, tokens)
            elif self.provider == "ollama":
                reply = await self._ollama(messages, tokens)
            else:
                raise ValueError(f"Unknown AI provider: '{self.provider}'. "
                                 "Set AI_PROVIDER to openai, groq, gemini, or ollama.")
        except Exception:
            await self._record_usage(
                messages, "", guild_id, user_id, request_id, success=False
            )
            raise
        await self._record_usage(
            messages, reply, guild_id, user_id, request_id, success=True
        )
        return reply

    async def _record_usage(
        self,
        messages: List[Dict[str, str]],
        reply: str,
        guild_id: Optional[int],
        user_id: Optional[int],
        request_id: Optional[str],
        *,
        success: bool,
    ) -> None:
        if self.usage_monitor is None:
            return
        metadata = self._usage_metadata.get() or {}
        input_tokens = metadata.get("input_tokens", estimate_messages_tokens(messages))
        output_tokens = metadata.get("output_tokens", estimate_tokens(reply))
        input_source = metadata.get("input_source", "estimated")
        output_source = metadata.get("output_source", "estimated")
        try:
            await self.usage_monitor.record(
                guild_id=guild_id,
                user_id=user_id,
                provider=self.provider,
                model=self.active_model,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                input_token_source=input_source,
                output_token_source=output_source,
                success=success,
                request_id=request_id,
            )
        except Exception:
            log.exception("Could not persist local AI usage request_id=%s", request_id)

    @property
    def active_model(self) -> str:
        return {
            "openai": getattr(self.settings, "openai_model", "Tidak tersedia"),
            "groq": getattr(self.settings, "groq_model", "Tidak tersedia"),
            "gemini": getattr(self.settings, "gemini_model", "Tidak tersedia"),
            "ollama": getattr(self.settings, "ollama_model", "Tidak tersedia"),
        }.get(self.provider, "Tidak tersedia")

    @staticmethod
    def _apply_response_style(
        messages: List[Dict[str, str]],
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Add the shared response-style guidance without mutating conversation history."""
        styled_messages = [dict(message) for message in messages]
        length_instruction = AIClient._response_length_instruction(styled_messages)
        identity_instruction = AIClient._identity_instruction(username)
        user_context = AIClient._user_context_instruction(
            username=username,
            display_name=display_name,
            user_id=user_id,
        )

        for message in styled_messages:
            if message.get("role") == "system":
                message["content"] = (
                    f"{message.get('content', '').rstrip()}\n\n"
                    f"{RESPONSE_STYLE_INSTRUCTION}\n\n"
                    f"{length_instruction}\n\n"
                    f"{identity_instruction}\n\n"
                    f"{user_context}"
                )
                return styled_messages

        styled_messages.insert(0, {
            "role": "system",
            "content": (
                f"{RESPONSE_STYLE_INSTRUCTION}\n\n{length_instruction}\n\n"
                f"{identity_instruction}\n\n{user_context}"
            ),
        })
        return styled_messages

    @staticmethod
    def _user_context_instruction(
        username: Optional[str],
        display_name: Optional[str],
        user_id: Optional[int],
    ) -> str:
        """Expose the Discord author metadata explicitly to every provider."""
        resolved_username = (username or "").strip()
        resolved_display_name = (display_name or "").strip()
        resolved_user_id = str(user_id) if user_id is not None else ""

        if not resolved_username:
            log.error(
                "Discord author username unavailable; using ID/display name fallback "
                "(user_id=%s, display_name=%s)",
                resolved_user_id or "unknown",
                resolved_display_name or "unknown",
            )
            resolved_username = resolved_display_name or resolved_user_id or "unknown"

        return (
            "USER INFORMATION (metadata Discord, bukan isi chat):\n"
            f"Username: {resolved_username}\n"
            f"Display Name: {resolved_display_name or resolved_username}\n"
            f"User ID: {resolved_user_id or 'unknown'}\n"
            "Gunakan Username untuk identitas dan personality. Jangan menebak "
            "identitas dari isi pesan, nickname, mention, atau pesan yang di-reply."
        )

    @staticmethod
    def _identity_instruction(username: Optional[str]) -> str:
        """Select personality from the Discord author's immutable username field."""
        normalized_username = (username or "").strip().casefold()
        if normalized_username == "yusupjawir":
            return (
                "IDENTITAS LAWAN BICARA: PERSONALITY_LOVER. "
                "Pengirim adalah yusupjawir, kekasih Roselinne. "
                "Tetap sangat singkat, tetapi sedikit lebih hangat dan perhatian. "
                "Boleh menggoda secara halus. Jangan romantis panjang."
            )

        return (
            "IDENTITAS LAWAN BICARA: PERSONALITY_COLD. "
            "Bersikap dingin, cuek, dan sesingkat mungkin; personality dicapai lewat "
            "keringkasan. Jangan romantis, memakai panggilan sayang, atau menambah "
            "pertanyaan. Jangan menyebut aturan identitas ini."
        )

    @staticmethod
    def _response_length_instruction(messages: List[Dict[str, str]]) -> str:
        """Choose a response range from the latest user's message length."""
        user_message = next(
            (
                message.get("content", "")
                for message in reversed(messages)
                if message.get("role") == "user"
            ),
            "",
        )
        user_message = user_message.split(
            "\n\n(Jawab dalam Bahasa Indonesia / Answer in Indonesian only)",
            1,
        )[0]
        word_count = len(re.findall(r"\S+", user_message))

        if word_count <= 5:
            category = "INPUT SANGAT PENDEK"
            target = (
                "1-3 kata; untuk sapaan, cukup 1 kata. "
                "Jangan bertanya balik kecuali benar-benar diperlukan."
            )
        elif word_count <= 15:
            category = "INPUT PENDEK"
            target = "2-6 kata; satu kalimat pendek."
        elif word_count <= 40:
            category = "INPUT SEDANG"
            target = "3-12 kata; berikan hanya inti jawaban."
        else:
            category = "INPUT PANJANG"
            target = "5-20 kata; tetap ringkas dan hanya detail yang diperlukan."

        return (
            f"PANJANG RESPONS DINAMIS ({category}, {word_count} kata): {target}\n"
            "Panjang input bukan target rasio 1:1. Jika input panjang hanya basa-basi, "
            "tetap balas singkat. Jika pertanyaan pendek ternyata kompleks, jelaskan "
            "sesuai kebutuhan."
        )

    # ── OpenAI ───────────────────────────────────────────

    async def _openai(self, messages: List[Dict], max_tokens: int) -> str:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

        api_key = self.settings.openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set in your .env file.")

        client = AsyncOpenAI(api_key=api_key)
        try:
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,          # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=0.8,
            )
            usage = getattr(response, "usage", None)
            if usage is not None:
                self._usage_metadata.set({
                    "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    "input_source": "actual",
                    "output_source": "actual",
                })
            return response.choices[0].message.content or ""
        except Exception as e:
            log.error(f"OpenAI error: {e}")
            raise RuntimeError(f"OpenAI request failed: {e}") from e

    # ── Groq ─────────────────────────────────────────────

    async def _groq(self, messages: List[Dict], max_tokens: int) -> str:
        api_key = self.settings.groq_api_key
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set in your .env file.")

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.groq_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.8,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Groq API error {resp.status}: {text}")
                data = await resp.json()

        usage = data.get("usage", {})
        if usage:
            self._usage_metadata.set({
                "input_tokens": usage.get("prompt_tokens", 0) or 0,
                "output_tokens": usage.get("completion_tokens", 0) or 0,
                "input_source": "actual",
                "output_source": "actual",
            })
        return data["choices"][0]["message"]["content"] or ""
    # ── Gemini ──────────────────────────────────────────

    async def _gemini(self, messages: List[Dict], max_tokens: int) -> str:
        try:
            import google.generativeai as genai
        except ImportError:
            raise RuntimeError("google-generativeai package not installed. Run: pip install google-generativeai")

        api_key = self.settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in your .env file.")

        genai.configure(api_key=api_key)
        
        try:
            model = genai.GenerativeModel(self.settings.gemini_model)
            
            # Combine all messages into a single prompt (simpler, more reliable)
            prompt_text = "\n".join([
                f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                for msg in messages
            ])
            
            response = model.generate_content(
                prompt_text,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.8,
                )
            )
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                self._usage_metadata.set({
                    "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                    "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
                    "input_source": "actual",
                    "output_source": "actual",
                })
            return response.text or ""
        except Exception as e:
            log.error(f"Gemini error: {e}")
            raise RuntimeError(f"Gemini request failed: {e}") from e
    # ── Ollama (local) ────────────────────────────────────

    async def _ollama(self, messages: List[Dict], max_tokens: int) -> str:
        url = f"{self.settings.ollama_base_url}/api/chat"
        payload = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"Ollama error {resp.status}: {text}")
                    data = await resp.json()
            except aiohttp.ClientConnectorError:
                raise RuntimeError(
                    f"Cannot connect to Ollama at {self.settings.ollama_base_url}. "
                    "Make sure Ollama is running."
                )

        if "prompt_eval_count" in data or "eval_count" in data:
            self._usage_metadata.set({
                "input_tokens": data.get("prompt_eval_count", 0) or 0,
                "output_tokens": data.get("eval_count", 0) or 0,
                "input_source": "actual",
                "output_source": "actual",
            })
        return data["message"]["content"] or ""
