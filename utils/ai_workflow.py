"""Per-bot single-flight state for message-based AI workflows."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass


@dataclass
class WorkflowState:
    workflow_id: str
    completed_at: float | None = None
    send_attempted: bool = False
    send_succeeded: bool = False


class AIWorkflowRegistry:
    """Own one durable workflow state for each Discord message ID."""

    def __init__(self, completed_ttl: float = 300.0):
        self.completed_ttl = completed_ttl
        self._states: dict[int, WorkflowState] = {}
        self._lock = asyncio.Lock()

    async def start(self, message_id: int) -> WorkflowState | None:
        async with self._lock:
            self._remove_expired()
            if message_id in self._states:
                return None
            state = WorkflowState(workflow_id=uuid.uuid4().hex)
            self._states[message_id] = state
            return state

    async def mark_send_attempted(self, message_id: int) -> WorkflowState:
        async with self._lock:
            state = self._states[message_id]
            state.send_attempted = True
            return state

    async def mark_send_succeeded(self, message_id: int) -> WorkflowState:
        async with self._lock:
            state = self._states[message_id]
            state.send_succeeded = True
            state.completed_at = time.monotonic()
            return state

    async def get(self, message_id: int) -> WorkflowState | None:
        async with self._lock:
            return self._states.get(message_id)

    async def finish(self, message_id: int) -> None:
        async with self._lock:
            state = self._states.get(message_id)
            if state is not None and state.completed_at is None:
                state.completed_at = time.monotonic()

    async def discard(self, message_id: int) -> None:
        async with self._lock:
            self._states.pop(message_id, None)

    def _remove_expired(self) -> None:
        now = time.monotonic()
        expired = [
            message_id
            for message_id, state in self._states.items()
            if state.completed_at is not None
            and now - state.completed_at >= self.completed_ttl
        ]
        for message_id in expired:
            del self._states[message_id]
