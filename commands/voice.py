"""
commands/voice.py
/voice join   — connect to the invoking member's voice channel.
/voice leave  — disconnect Roselinne from this guild's voice channel.
"""

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotSettings

log = logging.getLogger("roselinne.commands.voice")


class VoiceCog(commands.Cog, name="Voice"):
    """Silent voice presence commands."""

    voice = app_commands.Group(name="voice", description="Manage Roselinne's silent voice presence.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()
        log.info("VoiceCog loaded.")

    @voice.command(name="join", description="Join your current voice channel silently.")
    async def join(self, interaction: discord.Interaction) -> None:
        """Join or move to the invoking member's voice channel without audio."""
        if interaction.guild is None:
            await self._respond(
                interaction,
                "❄️ Voice presence is only available within a server.",
            )
            return

        voice_state = getattr(interaction.user, "voice", None)
        channel = voice_state.channel if voice_state else None
        if channel is None:
            await self._respond(
                interaction,
                "❄️ You are not in a voice channel. Even I cannot follow someone into thin air.",
            )
            return

        bot_member = interaction.guild.me
        if bot_member is None:
            await self._respond(
                interaction,
                "❄️ I cannot verify my server permissions yet. Please try again shortly.",
            )
            return

        permissions = channel.permissions_for(bot_member)
        if not permissions.connect:
            await self._respond(
                interaction,
                f"❄️ I lack the **Connect** permission for {channel.mention}.",
            )
            return

        voice_client = interaction.guild.voice_client
        try:
            if voice_client is not None and voice_client.is_connected():
                if voice_client.channel and voice_client.channel.id == channel.id:
                    await self._respond(
                        interaction,
                        f"❄️ I am already in {channel.mention}. Silent, as requested.",
                    )
                    return

                await voice_client.move_to(channel)
                await self._respond(
                    interaction,
                    f"❄️ I have moved my quiet presence to {channel.mention}.",
                )
                return

            await channel.connect(timeout=10.0, reconnect=True)
            await self._respond(
                interaction,
                f"❄️ I have joined {channel.mention}. No music, no recording—only presence.",
            )
        except discord.Forbidden:
            log.warning(
                "Voice permission denied in guild %s for channel %s",
                interaction.guild.id,
                channel.id,
            )
            await self._respond(
                interaction,
                f"❄️ Discord denied my connection to {channel.mention}. Check my **Connect** permission.",
            )
        except (asyncio.TimeoutError, discord.HTTPException, discord.ClientException, OSError, RuntimeError) as exc:
            log.error(
                "Could not establish voice presence in guild %s, channel %s: %s",
                interaction.guild.id,
                channel.id,
                exc,
            )
            await self._respond(
                interaction,
                "❄️ I could not establish a voice presence this time. "
                "The connection spirits are being particularly uncooperative.",
            )

    @voice.command(name="leave", description="Leave the voice channel in this server.")
    async def leave(self, interaction: discord.Interaction) -> None:
        """Disconnect only this guild's voice client."""
        if interaction.guild is None:
            await self._respond(
                interaction,
                "❄️ Voice presence is only available within a server.",
            )
            return

        voice_client = interaction.guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            await self._respond(
                interaction,
                "❄️ I am not connected to a voice channel in this server.",
            )
            return

        try:
            await voice_client.disconnect()
            await self._respond(
                interaction,
                "❄️ I have left the voice channel. The silence is restored.",
            )
        except (asyncio.TimeoutError, discord.HTTPException, discord.ClientException, OSError) as exc:
            log.error(
                "Could not leave voice channel in guild %s: %s",
                interaction.guild.id,
                exc,
            )
            await self._respond(
                interaction,
                "❄️ I could not leave cleanly. Discord seems reluctant to release me.",
            )

    @staticmethod
    async def _respond(interaction: discord.Interaction, message: str) -> None:
        await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceCog(bot))
