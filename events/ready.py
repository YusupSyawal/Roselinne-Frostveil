"""
events/ready.py
on_ready event — fires once the bot has connected and cached guilds.
"""

import logging
import os

import discord
from discord.ext import commands

log = logging.getLogger("roselinne.events.ready")


class ReadyCog(commands.Cog, name="Ready"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self.bot.user is None:
            return

        guild_count = len(self.bot.guilds)
        log.info("─" * 55)
        log.info(f"  Roselinne Frostveil is awake.")
        log.info(f"  Logged in as : {self.bot.user} (ID: {self.bot.user.id})")
        log.info(f"  Guilds       : {guild_count}")
        log.info(f"  Latency      : {round(self.bot.latency * 1000)} ms")
        log.info(
            "BOT_GATEWAY_READY process_id=%s instance_id=%s",
            os.getpid(),
            getattr(self.bot, "instance_id", "unknown"),
        )
        log.info("─" * 55)

        # Set a presence fitting the character
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="the silence between words",
            ),
            status=discord.Status.online,
        )

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info(f"Joined guild: {guild.name} (ID: {guild.id})")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.info(f"Removed from guild: {guild.name} (ID: {guild.id})")

    @commands.Cog.listener()
    async def on_disconnect(self) -> None:
        log.warning("Bot disconnected from Discord. Attempting reconnect…")

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        log.info("Connection resumed.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReadyCog(bot))
