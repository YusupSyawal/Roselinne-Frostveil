"""
utils/cooldown.py
Per-user cooldown tracker backed by a simple in-memory dict.
Thread-safe for asyncio (no locks needed — single-threaded event loop).
"""

import time
from typing import Dict, Optional, Tuple


class CooldownManager:
    """Track per-user, per-command cooldowns."""

    def __init__(self, default_seconds: float = 5.0):
        self.default_seconds = default_seconds
        # { (user_id, command) : last_used_timestamp }
        self._timestamps: Dict[Tuple[int, str], float] = {}

    def check(
        self,
        user_id: int,
        command: str = "global",
        seconds: Optional[float] = None,
    ) -> Optional[float]:
        """
        Return the remaining cooldown in seconds, or None if ready.

        Usage:
            remaining = cooldown.check(user_id, "chat")
            if remaining:
                await ctx.respond(f"Wait {remaining:.1f}s.")
            else:
                cooldown.consume(user_id, "chat")
                # ... do the action
        """
        limit = seconds if seconds is not None else self.default_seconds
        key = (user_id, command)
        last = self._timestamps.get(key)
        if last is None:
            return None
        elapsed = time.monotonic() - last
        if elapsed >= limit:
            return None
        return limit - elapsed

    def consume(self, user_id: int, command: str = "global") -> None:
        """Record that this user just used the command right now."""
        self._timestamps[(user_id, command)] = time.monotonic()

    def reset(self, user_id: int, command: str = "global") -> None:
        """Manually clear a user's cooldown (e.g. admin override)."""
        self._timestamps.pop((user_id, command), None)

    def reset_all(self, user_id: int) -> None:
        """Clear ALL cooldowns for a user."""
        to_delete = [k for k in self._timestamps if k[0] == user_id]
        for k in to_delete:
            del self._timestamps[k]


# Shared singleton — import this everywhere
cooldown_manager = CooldownManager()
