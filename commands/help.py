"""
commands/help.py
/help — lists all available slash commands.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotSettings

log = logging.getLogger("roselinne.commands.help")


COMMANDS_INFO = [
    ("/chat",          "Start or continue a conversation with me."),
    ("/resetmemory",   "Erase your conversation history."),
    ("/personality",   "Learn about me and view your chat stats."),
    ("/ping",          "Check if I am present and attentive."),
    ("/help",          "You are already here."),
    ("/ai_on",         "Enable AI responses (Manage Server)."),
    ("/ai_off",        "Disable AI requests (Manage Server)."),
    ("/ai_status",     "Show the current AI status (Manage Server)."),
    ("/usage",         "Show local AI usage; choose summary, limits, or reset."),
    ("/welcomechannel", "Configure the welcome message channel (Manage Server)."),
    ("/leavechannel",  "Configure the leave message channel (Manage Server)."),
    ("/voice join",    "Join your current voice channel silently."),
    ("/voice leave",   "Leave the voice channel in this server."),
    ("/music play",     "Play one YouTube video URL in your voice channel."),
    ("/music queue",    "Show the guild music queue."),
    ("/music nowplaying", "Show the current track."),
    ("/music pause/resume", "Pause or resume playback."),
    ("/music skip/stop/leave", "Control playback or leave voice."),
]


class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()

    @app_commands.command(name="help", description="Display all available commands.")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Command Compendium",
            description=(
                "What you need. Nothing more, nothing less.\n"
                "All commands are slash-based — simply type `/` to begin."
            ),
            color=self.settings.COLOR_PRIMARY,
        )

        for cmd, desc in COMMANDS_INFO:
            embed.add_field(name=cmd, value=desc, inline=False)

        embed.set_footer(
            text="Roselinne Frostveil  •  Winter Court AI",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
