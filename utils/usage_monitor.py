"""Local, isolated AI usage accounting.

This database is intentionally separate from conversation memory. Provider
limits are not inferred from these local counters.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UsageTotals:
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_input_tokens: int
    estimated_output_tokens: int


class UsageMonitor:
    """Persist one row per provider request in a dedicated SQLite database."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    request_id TEXT,
                    guild_id TEXT,
                    user_id TEXT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    input_token_source TEXT NOT NULL,
                    output_token_source TEXT NOT NULL,
                    success INTEGER NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(ai_usage)").fetchall()
            }
            if "request_id" not in columns:
                conn.execute("ALTER TABLE ai_usage ADD COLUMN request_id TEXT")
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_usage_request
                ON ai_usage(request_id) WHERE request_id IS NOT NULL
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage(created_at)"
            )

    @contextmanager
    def _conn(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    async def record(
        self,
        *,
        guild_id: int | None,
        user_id: int | None,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        input_token_source: str,
        output_token_source: str,
        success: bool,
        request_id: str | None = None,
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._record_sync,
                guild_id,
                user_id,
                provider,
                model,
                max(0, input_tokens),
                max(0, output_tokens),
                input_token_source,
                output_token_source,
                success,
                request_id,
            )

    def _record_sync(
        self,
        guild_id: int | None,
        user_id: int | None,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        input_token_source: str,
        output_token_source: str,
        success: bool,
        request_id: str | None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO ai_usage (
                    created_at, request_id, guild_id, user_id, provider, model,
                    input_tokens, output_tokens, input_token_source,
                    output_token_source, success
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    request_id,
                    str(guild_id) if guild_id is not None else None,
                    str(user_id) if user_id is not None else None,
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    input_token_source,
                    output_token_source,
                    int(success),
                ),
            )

    async def totals(self, guild_id: int | None = None) -> UsageTotals:
        async with self._lock:
            return await asyncio.to_thread(self._totals_sync, guild_id, None)

    async def period_totals(
        self, guild_id: int | None, start: float, end: float
    ) -> UsageTotals:
        async with self._lock:
            return await asyncio.to_thread(self._totals_sync, guild_id, (start, end))

    async def by_provider_model(self, guild_id: int | None) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._by_provider_model_sync, guild_id)

    async def reset(self, guild_id: int) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._reset_sync, guild_id)

    def _where(self, guild_id: int | None, period: tuple[float, float] | None):
        clauses: list[str] = []
        params: list[Any] = []
        if guild_id is not None:
            clauses.append("guild_id = ?")
            params.append(str(guild_id))
        if period is not None:
            clauses.append("created_at >= ? AND created_at < ?")
            params.extend(period)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def _totals_sync(
        self, guild_id: int | None, period: tuple[float, float] | None
    ) -> UsageTotals:
        where, params = self._where(guild_id, period)
        with self._conn() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) requests,
                       COALESCE(SUM(input_tokens), 0) input_tokens,
                       COALESCE(SUM(output_tokens), 0) output_tokens,
                       COALESCE(SUM(
                           CASE WHEN input_token_source = 'estimated'
                           THEN input_tokens ELSE 0 END
                       ), 0) estimated_input_tokens,
                       COALESCE(SUM(
                           CASE WHEN output_token_source = 'estimated'
                           THEN output_tokens ELSE 0 END
                       ), 0) estimated_output_tokens
                FROM ai_usage{where}
                """,
                params,
            ).fetchone()
        return UsageTotals(
            requests=row["requests"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["input_tokens"] + row["output_tokens"],
            estimated_input_tokens=row["estimated_input_tokens"],
            estimated_output_tokens=row["estimated_output_tokens"],
        )

    def _by_provider_model_sync(self, guild_id: int | None) -> list[dict[str, Any]]:
        where, params = self._where(guild_id, None)
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT provider, model, COUNT(*) requests,
                       SUM(input_tokens) input_tokens,
                       SUM(output_tokens) output_tokens,
                       SUM(input_tokens + output_tokens) total_tokens
                FROM ai_usage{where}
                GROUP BY provider, model
                ORDER BY total_tokens DESC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def _reset_sync(self, guild_id: int) -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM ai_usage WHERE guild_id = ?", (str(guild_id),)
            )
            return cursor.rowcount


def estimate_tokens(text: str) -> int:
    """Conservative dependency-free estimate, clearly labelled by callers."""
    return max(0, (len(text) + 3) // 4)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    return estimate_tokens("\n".join(str(item.get("content", "")) for item in messages))


def utc_period_bounds(now: float | None = None) -> tuple[tuple[float, float], tuple[float, float]]:
    import datetime as dt

    current = dt.datetime.fromtimestamp(now or time.time(), dt.timezone.utc)
    day = current.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    if month.month == 12:
        next_month = month.replace(year=month.year + 1, month=1)
    else:
        next_month = month.replace(month=month.month + 1)
    return (
        (day.timestamp(), (day + dt.timedelta(days=1)).timestamp()),
        (month.timestamp(), next_month.timestamp()),
    )
