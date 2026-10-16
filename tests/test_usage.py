import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from ai.memory import MemoryManager
from ai.ai_client import AIClient
from commands.usage import UsageCog
from utils.usage_monitor import UsageMonitor


class UsageMonitorTests(unittest.IsolatedAsyncioTestCase):
    def test_reset_requires_administrator_or_owner(self):
        owner = SimpleNamespace(id=7, guild_permissions=SimpleNamespace(administrator=False))
        interaction = SimpleNamespace(
            user=owner,
            guild=SimpleNamespace(owner_id=7),
        )
        self.assertTrue(UsageCog._can_reset(interaction))

        regular = SimpleNamespace(
            id=8, guild_permissions=SimpleNamespace(administrator=False)
        )
        interaction.user = regular
        self.assertFalse(UsageCog._can_reset(interaction))

        admin = SimpleNamespace(
            id=8, guild_permissions=SimpleNamespace(administrator=True)
        )
        interaction.user = admin
        self.assertTrue(UsageCog._can_reset(interaction))

    async def test_ai_client_records_provider_metadata_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = UsageMonitor(Path(directory) / "usage.db")
            settings = SimpleNamespace(
                ai_provider="ollama",
                max_tokens=20,
                ollama_model="llama",
            )
            client = AIClient(settings, monitor)

            async def successful_call(_messages, _tokens):
                client._usage_metadata.set({
                    "input_tokens": 11,
                    "output_tokens": 5,
                    "input_source": "actual",
                    "output_source": "actual",
                })
                return "jawaban"

            client._ollama = successful_call
            await client.chat(
                [{"role": "user", "content": "halo"}],
                guild_id=42,
                user_id=7,
                request_id="request-1",
            )

            client._ollama = AsyncMock(side_effect=RuntimeError("offline"))
            with self.assertRaises(RuntimeError):
                await client.chat(
                    [{"role": "user", "content": "lagi"}],
                    guild_id=42,
                    user_id=7,
                    request_id="request-2",
                )
            totals = await monitor.totals(42)

        self.assertEqual(totals.requests, 2)
        self.assertGreaterEqual(totals.input_tokens, 12)
        self.assertEqual(totals.output_tokens, 5)
        self.assertGreater(totals.estimated_input_tokens, 0)

    async def test_actual_and_estimated_usage_are_distinguished(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = UsageMonitor(Path(directory) / "usage.db")
            await monitor.record(
                guild_id=42,
                user_id=7,
                provider="openai",
                model="test-model",
                input_tokens=10,
                output_tokens=4,
                input_token_source="actual",
                output_token_source="actual",
                success=True,
            )
            await monitor.record(
                guild_id=42,
                user_id=7,
                provider="ollama",
                model="test-model",
                input_tokens=8,
                output_tokens=3,
                input_token_source="estimated",
                output_token_source="estimated",
                success=True,
            )

            totals = await monitor.totals(42)

        self.assertEqual(totals.requests, 2)
        self.assertEqual(totals.total_tokens, 25)
        self.assertEqual(totals.estimated_input_tokens, 8)
        self.assertEqual(totals.estimated_output_tokens, 3)

    async def test_failed_request_is_counted_without_affecting_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = MemoryManager(
                SimpleNamespace(db_path=root / "memory.db", memory_max_messages=20)
            )
            monitor = UsageMonitor(root / "usage.db")
            await memory.add_message(42, 7, "user", "halo", 123)
            await memory.add_message(42, 7, "assistant", "Hm.", 123)
            before = await memory.get_history(42, 7)

            await monitor.record(
                guild_id=42,
                user_id=7,
                provider="groq",
                model="test-model",
                input_tokens=5,
                output_tokens=0,
                input_token_source="estimated",
                output_token_source="estimated",
                success=False,
            )
            after = await memory.get_history(42, 7)
            await monitor.reset(42)
            after_reset = await memory.get_history(42, 7)
            usage_after_reset = await monitor.totals(42)

        self.assertEqual(before, after)
        self.assertEqual(before, after_reset)
        self.assertEqual(usage_after_reset.requests, 0)

    async def test_reset_is_scoped_to_guild(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = UsageMonitor(Path(directory) / "usage.db")
            for guild_id in (42, 43):
                await monitor.record(
                    guild_id=guild_id,
                    user_id=7,
                    provider="ollama",
                    model="llama",
                    input_tokens=1,
                    output_tokens=1,
                    input_token_source="estimated",
                    output_token_source="estimated",
                    success=True,
                )
            deleted = await monitor.reset(42)
            remaining = await monitor.totals(43)

        self.assertEqual(deleted, 1)
        self.assertEqual(remaining.requests, 1)

    async def test_same_request_id_is_counted_once(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = UsageMonitor(Path(directory) / "usage.db")
            for output in (2, 3):
                await monitor.record(
                    guild_id=42,
                    user_id=7,
                    provider="ollama",
                    model="llama",
                    input_tokens=4,
                    output_tokens=output,
                    input_token_source="estimated",
                    output_token_source="estimated",
                    success=True,
                    request_id="message-123",
                )
            totals = await monitor.totals(42)

        self.assertEqual(totals.requests, 1)
        self.assertEqual(totals.output_tokens, 2)


if __name__ == "__main__":
    unittest.main()
