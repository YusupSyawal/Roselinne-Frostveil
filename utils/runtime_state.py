"""
Runtime state persisted locally for guild-level bot controls.

The file is intentionally separate from the conversation database so a
corrupted state file can fail closed for AI without affecting memory.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("roselinne.runtime")


class RuntimeState:
    """Persist AI and member-message settings in a small local JSON file."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()

    async def is_ai_enabled(self, guild_id: int) -> bool:
        """Return the guild AI state; unreadable or missing state fails closed."""
        async with self._lock:
            try:
                state = self._read()
                guilds = state.get("guilds", {})
                if not isinstance(guilds, dict):
                    raise ValueError("runtime state 'guilds' must be an object")
                guild_state = guilds.get(str(guild_id), {})
                if not isinstance(guild_state, dict):
                    raise ValueError("runtime state guild entry must be an object")
                return guild_state.get("ai_enabled") is True
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                log.error("Could not read runtime state at %s: %s", self.path, exc)
                return False

    async def set_ai_enabled(self, guild_id: int, enabled: bool) -> None:
        """Persist the AI state for one guild."""
        async with self._lock:
            state = self._read_for_update()
            guild_state = self._guild_state_for_update(state, guild_id)
            guild_state["ai_enabled"] = enabled
            self._write(state)

    async def get_channel_id(self, guild_id: int, channel_type: str) -> int | None:
        """Return a configured welcome/leave channel, or None when unset."""
        async with self._lock:
            try:
                state = self._read()
                guilds = state.get("guilds", {})
                if not isinstance(guilds, dict):
                    raise ValueError("runtime state 'guilds' must be an object")
                guild_state = guilds.get(str(guild_id), {})
                if not isinstance(guild_state, dict):
                    raise ValueError("runtime state guild entry must be an object")
                value = guild_state.get(f"{channel_type}_channel_id")
                return value if isinstance(value, int) else None
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                log.error("Could not read runtime state at %s: %s", self.path, exc)
                return None

    async def set_channel_id(
        self,
        guild_id: int,
        channel_type: str,
        channel_id: int | None,
    ) -> None:
        """Persist or clear a welcome/leave channel for one guild."""
        if channel_type not in {"welcome", "leave"}:
            raise ValueError(f"Unsupported channel type: {channel_type}")

        async with self._lock:
            state = self._read_for_update()
            guild_state = self._guild_state_for_update(state, guild_id)
            key = f"{channel_type}_channel_id"
            if channel_id is None:
                guild_state.pop(key, None)
            else:
                guild_state[key] = channel_id
            self._write(state)

    def _read(self) -> dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        if not isinstance(state, dict):
            raise ValueError("runtime state root must be a JSON object")
        return state

    def _read_for_update(self) -> dict[str, Any]:
        try:
            state = self._read()
        except FileNotFoundError:
            return {"guilds": {}}
        guilds = state.setdefault("guilds", {})
        if not isinstance(guilds, dict):
            raise ValueError("runtime state 'guilds' must be an object")
        return state

    @staticmethod
    def _guild_state_for_update(
        state: dict[str, Any], guild_id: int
    ) -> dict[str, Any]:
        guilds = state["guilds"]
        guild_state = guilds.setdefault(str(guild_id), {})
        if not isinstance(guild_state, dict):
            raise ValueError("runtime state guild entry must be an object")
        return guild_state

    def _write(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        try:
            with temporary_path.open("w", encoding="utf-8") as state_file:
                json.dump(state, state_file, indent=2)
                state_file.write("\n")
            temporary_path.replace(self.path)
        except OSError:
            if temporary_path.exists():
                temporary_path.unlink()
            raise
