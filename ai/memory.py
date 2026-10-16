"""
ai/memory.py
Per-user conversation memory, persisted in SQLite.
Keeps the last N messages per (guild_id, user_id) pair.
"""

import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from typing import Dict, List

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
                    source_message_id TEXT,
                    created_at  REAL    DEFAULT (unixepoch('now'))
                )
            """)
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(conversation)").fetchall()
            }
            if "source_message_id" not in columns:
                conn.execute("ALTER TABLE conversation ADD COLUMN source_message_id TEXT")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conv_user
                ON conversation(guild_id, user_id, created_at)
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_source_message
                ON conversation(guild_id, user_id, role, source_message_id)
                WHERE source_message_id IS NOT NULL
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

    async def add_message(
        self,
        guild_id: int,
        user_id: int,
        role: str,
        content: str,
        source_message_id: int | None = None,
    ) -> None:
        """Append a message and prune old ones in one transaction."""
        async with self._lock:
            await asyncio.to_thread(
                self._add_message_sync,
                str(guild_id),
                str(user_id),
                role,
                content,
                str(source_message_id) if source_message_id is not None else None,
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
                SELECT role, content, created_at, source_message_id FROM (
                    SELECT role, content, created_at, source_message_id, id
                    FROM conversation
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                ) ORDER BY created_at ASC, id ASC
            """, (guild_id, user_id, self.max_messages)).fetchall()
        history = [
            {
                "role": r["role"],
                "content": r["content"],
                "_created_at": r["created_at"],
                "_source_message_id": r["source_message_id"],
            }
            for r in rows
        ]
        history = self._remove_legacy_duplicate_turns(history)
        for message in history:
            message.pop("_created_at", None)
            message.pop("_source_message_id", None)
        return history

    @staticmethod
    def _remove_legacy_duplicate_turns(
        history: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """Remove duplicate legacy turns while preserving identified message IDs."""
        collapsed: List[Dict[str, str]] = []
        for message in history:
            if (
                message.get("role") == "user"
                and message.get("_source_message_id") is None
                and len(collapsed) >= 2
                and collapsed[-2].get("role") == "user"
                and collapsed[-2].get("content") == message.get("content")
                and collapsed[-2].get("_source_message_id") is None
                and float(message.get("_created_at", 0)) - float(
                    collapsed[-2].get("_created_at", 0)
                ) <= 1.0
                and collapsed[-1].get("role") == "assistant"
            ):
                collapsed.pop()
                collapsed.pop()
            collapsed.append(message)
        return collapsed

    def _add_message_sync(
        self,
        guild_id: str,
        user_id: str,
        role: str,
        content: str,
        source_message_id: str | None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO conversation
                    (guild_id, user_id, role, content, source_message_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, role, content, source_message_id),
            )
            # Prune: keep only the most recent max_messages rows
            conn.execute("""
                DELETE FROM conversation
                WHERE guild_id = ? AND user_id = ?
                  AND id NOT IN (
                      SELECT id FROM conversation
                      WHERE guild_id = ? AND user_id = ?
                      ORDER BY created_at DESC, id DESC
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
