"""
Guild commands for enabling and disabling AI requests.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("roselinne.commands.ai_control")


class AIControlCog(commands.Cog, name="AI Control"):
    """Manage the AI feature without affecting moderator functionality."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _require_guild_and_permission(
        self, interaction: discord.Interaction
    ) -> bool:
        if interaction.guild_id is None or not isinstance(
            interaction.user, discord.Member
        ):
            await interaction.response.send_message(
                "❄️ This command can only be used inside a server.",
                ephemeral=True,
            )
            return False

        permissions = interaction.user.guild_permissions
        if not (permissions.manage_guild or permissions.administrator):
            await interaction.response.send_message(
                "❄️ You need **Manage Server** permission to change AI status.",
                ephemeral=True,
            )
            return False
        return True

    @app_commands.command(name="ai_on", description="Enable Roselinne AI responses.")
    @app_commands.default_permissions(manage_guild=True)
    async def ai_on(self, interaction: discord.Interaction) -> None:
        if not await self._require_guild_and_permission(interaction):
            return
        try:
            await self.bot.runtime_state.set_ai_enabled(interaction.guild_id, True)
        except (OSError, ValueError) as exc:
            log.error("Could not enable AI in guild %s: %s", interaction.guild_id, exc)
            await interaction.response.send_message(
                "❄️ I could not save the AI state locally. AI remains OFF.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "❄️ AI is now **ON**. Roselinne may answer chat and mentions again.",
            ephemeral=True,
        )
        log.info("AI enabled in guild %s by %s", interaction.guild_id, interaction.user)

    @app_commands.command(name="ai_off", description="Disable Roselinne AI requests.")
    @app_commands.default_permissions(manage_guild=True)
    async def ai_off(self, interaction: discord.Interaction) -> None:
        if not await self._require_guild_and_permission(interaction):
            return
        try:
            await self.bot.runtime_state.set_ai_enabled(interaction.guild_id, False)
        except (OSError, ValueError) as exc:
            log.error("Could not disable AI in guild %s: %s", interaction.guild_id, exc)
            await interaction.response.send_message(
                "❄️ I could not save the AI state locally. Check the runtime file permissions.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "❄️ AI is now **OFF**. Moderation and non-AI commands remain available.",
            ephemeral=True,
        )
        log.info("AI disabled in guild %s by %s", interaction.guild_id, interaction.user)

    @app_commands.command(name="ai_status", description="Show the current AI status.")
    @app_commands.default_permissions(manage_guild=True)
    async def ai_status(self, interaction: discord.Interaction) -> None:
        if not await self._require_guild_and_permission(interaction):
            return
        enabled = await self.bot.runtime_state.is_ai_enabled(interaction.guild_id)
        status = "ON" if enabled else "OFF"
        await interaction.response.send_message(
            f"❄️ AI status: **{status}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIControlCog(bot))
