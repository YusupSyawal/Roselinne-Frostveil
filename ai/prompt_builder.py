"""
ai/prompt_builder.py
Assembles the messages list sent to the AI provider.
Loads personality from config/personality.txt so it can be edited without touching code.
"""

import logging
from pathlib import Path
from typing import List, Dict

log = logging.getLogger("roselinne.prompt")


def load_system_prompt(personality_file: Path) -> str:
    """Read personality.txt, falling back to a minimal default."""
    try:
        text = personality_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    except FileNotFoundError:
        log.warning(f"Personality file not found: {personality_file}")
    except OSError as e:
        log.warning(f"Could not read personality file: {e}")

    # Minimal fallback
    return (
        "You are Roselinne Frostveil, an elegant and slightly sarcastic AI assistant. "
        "You are helpful, concise, and carry yourself with quiet dignity."
    )


def build_messages(
    system_prompt: str,
    history: List[Dict[str, str]],
    user_message: str,
) -> List[Dict[str, str]]:
    """
    Construct the full messages list for the chat completion API.

    Structure:
        [ {system}, ...history..., {user: current message} ]
    """
    indonesian_instruction = """ANDA HARUS MENJAWAB HANYA DALAM BAHASA INDONESIA.
JANGAN GUNAKAN BAHASA INGGRIS SAMA SEKALI.
SETIAP RESPONS HARUS DALAM BAHASA INDONESIA.
DO NOT USE ENGLISH. RESPOND ONLY IN INDONESIAN."""
    
    messages = [{"role": "system", "content": indonesian_instruction + "\n\n" + system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message + "\n\n(Jawab dalam Bahasa Indonesia / Answer in Indonesian only)"})
    return messages
