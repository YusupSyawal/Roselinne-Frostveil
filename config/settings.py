"""
config/settings.py
Centralised configuration loaded from environment variables.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class BotSettings:
    # ── Discord ───────────────────────────────────────────
    token: str = field(default_factory=lambda: os.getenv("DISCORD_BOT_TOKEN", ""))
    client_id: str = field(default_factory=lambda: os.getenv("DISCORD_CLIENT_ID", ""))

    # ── AI ────────────────────────────────────────────────
    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "openai").lower())

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
    groq_vision_model: str = field(
        default_factory=lambda: os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
    )

    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite"))

    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3"))

    # ── Behaviour ─────────────────────────────────────────
    memory_max_messages: int = field(default_factory=lambda: int(os.getenv("MEMORY_MAX_MESSAGES", "20")))
    cooldown_seconds: int = field(default_factory=lambda: int(os.getenv("COOLDOWN_SECONDS", "5")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("MAX_TOKENS", "1000")))
    
    # ── Response Verification ────────────────────────────
    enable_verification: bool = field(default_factory=lambda: os.getenv("ENABLE_VERIFICATION", "true").lower() in ("true", "1", "yes"))
    verification_timeout: int = field(default_factory=lambda: int(os.getenv("VERIFICATION_TIMEOUT", "10")))

    # ── Paths ─────────────────────────────────────────────
    personality_file: Path = BASE_DIR / "config" / "personality.txt"
    memory_dir: Path = BASE_DIR / "data" / "memory"
    db_path: Path = BASE_DIR / "data" / "memory.db"
    runtime_state_path: Path = BASE_DIR / "data" / "runtime_state.json"
    welcome_channel_id: int | None = field(
        default_factory=lambda: _optional_int_env("WELCOME_CHANNEL_ID")
    )
    leave_channel_id: int | None = field(
        default_factory=lambda: _optional_int_env("LEAVE_CHANNEL_ID")
    )

    # ── Theme colours (frost / silver-blue) ───────────────
    COLOR_PRIMARY: int = 0x7EB8D4      # soft sky blue
    COLOR_SUCCESS: int = 0x5CB8B2      # teal-frost
    COLOR_WARNING: int = 0xC4A882      # warm sand
    COLOR_ERROR: int = 0xC47A7A        # muted rose
    COLOR_INFO: int = 0xA0B4C8         # steel grey-blue

    def __post_init__(self):
        # Ensure data directories exist
        self.memory_dir.mkdir(parents=True, exist_ok=True)


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} must be a Discord channel ID integer.") from None
