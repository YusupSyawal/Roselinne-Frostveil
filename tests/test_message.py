import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from events.message import MessageCog
from utils.ai_workflow import AIWorkflowRegistry


class MessageHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.user = SimpleNamespace(id=999)
        self.bot.process_commands = AsyncMock()
        self.bot.runtime_state.is_ai_enabled = AsyncMock(return_value=True)

        self.cog = MessageCog.__new__(MessageCog)
        self.cog.bot = self.bot
        self.cog.settings = SimpleNamespace(cooldown_seconds=5)
        self.cog._ai_message_claims = {}
        self.cog._ai_message_claims_lock = asyncio.Lock()
        self.bot.ai_workflow_registry = AIWorkflowRegistry()
        self.cog._get_reply = AsyncMock(return_value="Baik, Yusup.")
        self.cog._handle_images = AsyncMock()
        self.cog.memory = MagicMock()

        self.author = SimpleNamespace(
            bot=False,
            id=123,
            name="yusupjawir",
            display_name="Yusup",
        )

    def _message(self, message_id: int, *, mention: bool = True):
        channel = MagicMock()
        typing_context = MagicMock()
        typing_context.__aenter__ = AsyncMock(return_value=None)
        typing_context.__aexit__ = AsyncMock(return_value=None)
        channel.typing.return_value = typing_context
        return SimpleNamespace(
            id=message_id,
            author=self.author,
            guild=SimpleNamespace(id=42),
            content="<@999> halo" if mention else "halo",
            mentions=[self.bot.user] if mention else [],
            attachments=[],
            channel=channel,
            reply=AsyncMock(),
        )

    async def test_one_message_id_produces_one_ai_reply(self):
        message = self._message(100)
        with patch("events.message.cooldown_manager.check", return_value=None), \
                patch("events.message.cooldown_manager.consume"):
            await self.cog.on_message(message)
            await self.cog.on_message(message)

        message.reply.assert_awaited_once_with("Baik, Yusup.", mention_author=False)
        self.cog._get_reply.assert_awaited_once()
        self.assertEqual(self.cog._get_reply.await_args.args[-1], 100)

    async def test_two_message_ids_are_both_processed(self):
        first = self._message(100)
        second = self._message(101)
        with patch("events.message.cooldown_manager.check", return_value=None), \
                patch("events.message.cooldown_manager.consume"):
            await self.cog.on_message(first)
            await self.cog.on_message(second)

        first.reply.assert_awaited_once()
        second.reply.assert_awaited_once()
        self.assertEqual(self.cog._get_reply.await_count, 2)

    async def test_message_without_mention_does_not_create_ai_reply(self):
        message = self._message(100, mention=False)
        await self.cog.on_message(message)

        message.reply.assert_not_awaited()
        self.cog._get_reply.assert_not_awaited()
        self.bot.process_commands.assert_awaited_once_with(message)

    async def test_ai_off_does_not_create_ai_reply(self):
        self.bot.runtime_state.is_ai_enabled.return_value = False
        message = self._message(100)
        await self.cog.on_message(message)

        message.reply.assert_not_awaited()
        self.cog._get_reply.assert_not_awaited()
        self.bot.process_commands.assert_awaited_once_with(message)

    async def test_mention_with_image_has_one_ai_response_path(self):
        message = self._message(100)
        message.attachments = [SimpleNamespace(content_type="image/png", filename="image.png")]
        with patch("events.message.cooldown_manager.check", return_value=None), \
                patch("events.message.cooldown_manager.consume"):
            await self.cog.on_message(message)

        self.cog._handle_images.assert_not_awaited()
        message.reply.assert_awaited_once_with("Baik, Yusup.", mention_author=False)

    async def test_generator_error_sends_one_fallback(self):
        message = self._message(100)
        self.cog._get_reply.side_effect = RuntimeError("provider unavailable")
        with patch("events.message.cooldown_manager.check", return_value=None), \
                patch("events.message.cooldown_manager.consume"):
            await self.cog.on_message(message)

        message.reply.assert_awaited_once()
        self.assertIn("Sesuatu mengganggu", message.reply.await_args.args[0])

    async def test_duplicate_listener_instances_share_one_workflow(self):
        duplicate = copy.copy(self.cog)
        first = self._message(100)
        second = self._message(100)
        with patch("events.message.cooldown_manager.check", return_value=None), \
                patch("events.message.cooldown_manager.consume"):
            await asyncio.gather(
                self.cog.on_message(first),
                duplicate.on_message(second),
            )

        self.assertEqual(first.reply.await_count + second.reply.await_count, 1)
        self.assertEqual(self.cog._get_reply.await_count, 1)


if __name__ == "__main__":
    unittest.main()
