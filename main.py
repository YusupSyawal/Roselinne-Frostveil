"""
Roselinne Frostveil — Discord AI Bot
Entry point / main launcher
"""

import asyncio
import logging
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config.settings import BotSettings
from utils.logger import setup_logger
from utils.runtime_state import RuntimeState

# ─────────────────────────────────────────────
# Bootstrap
# ─────────────────────────────────────────────
load_dotenv()
setup_logger()
log = logging.getLogger("roselinne")


# ─────────────────────────────────────────────
# Bot setup
# ─────────────────────────────────────────────
class RoselinneBot(commands.Bot):
    """Main bot class with lifecycle hooks."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True          # Required for member join/leave events

        super().__init__(
            command_prefix="!",          # prefix kept for fallback; slash cmds are primary
            intents=intents,
            help_command=None,           # we have our own /help
            case_insensitive=True,
        )

        self.settings = BotSettings()
        self.runtime_state = RuntimeState(self.settings.runtime_state_path)

    async def setup_hook(self) -> None:
        """Called once before the bot connects. Load all extensions here."""
        extensions = [
            "commands.chat",
            "commands.ai_control",
            "commands.image",
            "commands.ping",
            "commands.welcome",
            "commands.help",
            "events.ready",
            "events.message",
            "events.member",
        ]

        for ext in extensions:
            try:
                await self.load_extension(ext)
                log.info(f"  ✓ Loaded extension: {ext}")
            except Exception as e:
                log.error(f"  ✗ Failed to load {ext}: {e}", exc_info=True)

        # Sync slash commands globally (or to a test guild if set)
        guild_id = os.getenv("TEST_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info(f"Synced {len(synced)} command(s) to test guild {guild_id}")
        else:
            synced = await self.tree.sync()
            log.info(f"Synced {len(synced)} command(s) globally")

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        log.exception(f"Unhandled error in event '{event_method}'")


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────
async def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        log.critical("DISCORD_BOT_TOKEN is not set. Check your .env file.")
        sys.exit(1)

    bot = RoselinneBot()

    async with bot:
        try:
            await bot.start(token)
        except discord.LoginFailure:
            log.critical("Invalid Discord token. Please verify DISCORD_BOT_TOKEN.")
            sys.exit(1)
        except KeyboardInterrupt:
            log.info("Shutdown requested.")
        finally:
            if not bot.is_closed():
                await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
