"""
commands/ping.py
/ping — latency check.
"""

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotSettings

log = logging.getLogger("roselinne.commands.ping")


class PingCog(commands.Cog, name="Ping"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()

    @app_commands.command(name="ping", description="Check if Roselinne is awake.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)

        if latency_ms < 100:
            mood = "Sharp as ever."
        elif latency_ms < 250:
            mood = "Acceptable, I suppose."
        else:
            mood = "The ether is sluggish today."

        embed = discord.Embed(
            title="❄️  Pong",
            description=f"{mood}\n\n**Gateway latency:** `{latency_ms} ms`",
            color=self.settings.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PingCog(bot))
