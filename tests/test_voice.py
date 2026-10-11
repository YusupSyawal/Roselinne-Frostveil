import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from commands.voice import VoiceCog


class VoiceCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.cog = VoiceCog(self.bot)
        self.interaction = MagicMock()
        self.interaction.response.send_message = AsyncMock()

        self.guild = MagicMock()
        self.guild.id = 123
        self.guild.voice_client = None
        self.guild.me = MagicMock()
        self.interaction.guild = self.guild
        self.interaction.user = MagicMock()
        self.interaction.user.voice = SimpleNamespace(channel=None)

    async def test_join_without_voice_state(self):
        await self.cog.join.callback(self.cog, self.interaction)

        self.interaction.response.send_message.assert_awaited_once()
        self.assertTrue(self.interaction.response.send_message.await_args.kwargs["ephemeral"])

    async def test_join_rejects_direct_messages(self):
        self.interaction.guild = None

        await self.cog.join.callback(self.cog, self.interaction)

        self.interaction.response.send_message.assert_awaited_once()

    async def test_join_success(self):
        channel = MagicMock()
        channel.id = 456
        channel.mention = "<#456>"
        channel.permissions_for.return_value.connect = True
        channel.connect = AsyncMock()
        self.interaction.user.voice.channel = channel

        await self.cog.join.callback(self.cog, self.interaction)

        channel.connect.assert_awaited_once_with(timeout=10.0, reconnect=True)

    async def test_join_when_already_connected(self):
        channel = MagicMock()
        channel.id = 456
        channel.mention = "<#456>"
        channel.permissions_for.return_value.connect = True
        voice_client = MagicMock()
        voice_client.is_connected.return_value = True
        voice_client.channel = channel
        self.guild.voice_client = voice_client
        self.interaction.user.voice.channel = channel

        await self.cog.join.callback(self.cog, self.interaction)

        voice_client.move_to.assert_not_called()
        channel.connect.assert_not_called()

    async def test_leave_disconnects_current_guild(self):
        voice_client = MagicMock()
        voice_client.is_connected.return_value = True
        voice_client.disconnect = AsyncMock()
        self.guild.voice_client = voice_client

        await self.cog.leave.callback(self.cog, self.interaction)

        voice_client.disconnect.assert_awaited_once_with()

    async def test_leave_when_not_connected(self):
        await self.cog.leave.callback(self.cog, self.interaction)

        self.interaction.response.send_message.assert_awaited_once()

    async def test_join_denies_missing_connect_permission(self):
        channel = MagicMock()
        channel.mention = "<#456>"
        channel.permissions_for.return_value.connect = False
        channel.connect = AsyncMock()
        self.interaction.user.voice.channel = channel

        await self.cog.join.callback(self.cog, self.interaction)

        channel.connect.assert_not_called()

    async def test_join_handles_connection_error(self):
        channel = MagicMock()
        channel.id = 456
        channel.mention = "<#456>"
        channel.permissions_for.return_value.connect = True
        channel.connect = AsyncMock(side_effect=asyncio.TimeoutError)
        self.interaction.user.voice.channel = channel

        await self.cog.join.callback(self.cog, self.interaction)

        self.interaction.response.send_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
