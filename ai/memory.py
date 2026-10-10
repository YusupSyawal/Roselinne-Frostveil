"""
ai/memory.py
Per-user conversation memory, persisted in SQLite.
Keeps the last N messages per (guild_id, user_id) pair.
"""

import asyncio
import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict

from config.settings import BotSettings

log = logging.getLogger("roselinne.memory")


class MemoryManager:
    """
    Stores and retrieves conversation history per user per guild.
    Uses SQLite so memory survives bot restarts.
    """

    def __init__(self, settings: BotSettings):
        self.db_path = settings.db_path
        self.max_messages = settings.memory_max_messages
        self._lock = asyncio.Lock()
        self._init_db()

    # ── DB bootstrap ─────────────────────────────────────

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id    TEXT    NOT NULL,
                    user_id     TEXT    NOT NULL,
                    role        TEXT    NOT NULL,
                    content     TEXT    NOT NULL,
                    created_at  REAL    DEFAULT (unixepoch('now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conv_user
                ON conversation(guild_id, user_id, created_at)
            """)
        log.debug(f"Memory DB ready at {self.db_path}")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Public API ───────────────────────────────────────

    async def get_history(self, guild_id: int, user_id: int) -> List[Dict[str, str]]:
        """Return last N messages as a list of {role, content} dicts."""
        async with self._lock:
            return await asyncio.to_thread(self._get_history_sync, str(guild_id), str(user_id))

    async def add_message(self, guild_id: int, user_id: int, role: str, content: str) -> None:
        """Append a message and prune old ones in one transaction."""
        async with self._lock:
            await asyncio.to_thread(
                self._add_message_sync, str(guild_id), str(user_id), role, content
            )

    async def clear_history(self, guild_id: int, user_id: int) -> int:
        """Delete all messages for this user. Returns count deleted."""
        async with self._lock:
            return await asyncio.to_thread(
                self._clear_history_sync, str(guild_id), str(user_id)
            )

    async def get_stats(self, guild_id: int, user_id: int) -> Dict:
        """Return basic stats for /personality command."""
        async with self._lock:
            return await asyncio.to_thread(
                self._get_stats_sync, str(guild_id), str(user_id)
            )

    # ── Sync helpers (run in thread pool) ────────────────

    def _get_history_sync(self, guild_id: str, user_id: str) -> List[Dict[str, str]]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT role, content FROM (
                    SELECT role, content, created_at
                    FROM conversation
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ) ORDER BY created_at ASC
            """, (guild_id, user_id, self.max_messages)).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def _add_message_sync(self, guild_id: str, user_id: str, role: str, content: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversation (guild_id, user_id, role, content) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, role, content),
            )
            # Prune: keep only the most recent max_messages rows
            conn.execute("""
                DELETE FROM conversation
                WHERE guild_id = ? AND user_id = ?
                  AND id NOT IN (
                      SELECT id FROM conversation
                      WHERE guild_id = ? AND user_id = ?
                      ORDER BY created_at DESC
                      LIMIT ?
                  )
            """, (guild_id, user_id, guild_id, user_id, self.max_messages))

    def _clear_history_sync(self, guild_id: str, user_id: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM conversation WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            return cur.rowcount

    def _get_stats_sync(self, guild_id: str, user_id: str) -> Dict:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as total,
                       MIN(created_at) as first_seen,
                       MAX(created_at) as last_seen
                FROM conversation
                WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id)).fetchone()
        return dict(row) if row else {"total": 0, "first_seen": None, "last_seen": None}
