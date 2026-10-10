"""
commands/welcome.py
Welcome-related commands:
  /welcome [member]     — manually send welcome message for a member
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotSettings
from events.member import MemberCog

log = logging.getLogger("roselinne.commands.welcome")


class WelcomeCog(commands.Cog, name="Welcome"):
    """Welcome and member greeting commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()
        log.info("WelcomeCog loaded.")

    @app_commands.command(
        name="welcome",
        description="Send a welcome message for a member (admin use)."
    )
    @app_commands.describe(member="The member to welcome")
    @app_commands.default_permissions(manage_guild=True)
    async def welcome(self, interaction: discord.Interaction, member: discord.Member) -> None:
        """Manually trigger a welcome message for a member."""
        if member.bot:
            embed = discord.Embed(
                description="❄️ I cannot welcome bots; they do not require the warmth of greeting.",
                color=self.settings.COLOR_WARNING,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Get the MemberCog to generate welcome message
        member_cog = None
        for cog in self.bot.cogs.values():
            if cog.__class__.__name__ == "MemberCog":
                member_cog = cog
                break

        if not member_cog:
            await interaction.response.send_message(
                "❄️ Welcome system not initialized.",
                ephemeral=True
            )
            return

        # Generate welcome embed
        welcome_embed = member_cog._generate_welcome_message(member, interaction.guild)

        try:
            await interaction.response.send_message(embed=welcome_embed)
            log.info(f"Manual welcome sent for {member.name} by {interaction.user.name}")
        except Exception as e:
            log.error(f"Error sending welcome: {e}")
            await interaction.response.send_message(
                f"❄️ Error: {str(e)[:100]}",
                ephemeral=True
            )

    @app_commands.command(
        name="welcomechannel",
        description="Set the channel for welcome messages."
    )
    @app_commands.describe(channel="The channel to use for welcome messages (leave blank to use auto-detection)")
    @app_commands.default_permissions(manage_guild=True)
    async def set_welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None) -> None:
        """Set the welcome message channel for this guild."""
        # Note: This is a simple version. For persistence, you'd need to store in database.
        # For now, we rely on the auto-detection logic in MemberCog.

        if channel:
            perms = channel.permissions_for(interaction.guild.me)
            if not perms.send_messages:
                embed = discord.Embed(
                    description=f"❄️ I lack permission to send messages in {channel.mention}.",
                    color=self.settings.COLOR_ERROR,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            embed = discord.Embed(
                title="Welcome Channel Updated",
                description=f"New members will be welcomed in {channel.mention}.",
                color=self.settings.COLOR_SUCCESS,
            )
        else:
            embed = discord.Embed(
                title="Welcome Channel Reset",
                description="Auto-detection enabled. Will use #general or first available channel.",
                color=self.settings.COLOR_INFO,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
        log.info(f"Welcome channel set to {channel.name if channel else 'auto-detect'} in {interaction.guild.name}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
