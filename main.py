"""
Roselinne Frostveil — Discord AI Bot
Entry point / main launcher
"""

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config.settings import BotSettings
from utils.logger import setup_logger
from utils.runtime_state import RuntimeState
from utils.single_instance import SingleInstanceLock
from utils.usage_monitor import UsageMonitor

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
        self.usage_monitor = UsageMonitor(self.settings.usage_db_path)
        self.instance_id = uuid.uuid4().hex
        log.info(
            "BOT_INSTANCE_START process_id=%s instance_id=%s",
            os.getpid(),
            self.instance_id,
        )

    async def setup_hook(self) -> None:
        """Called once before the bot connects. Load all extensions here."""
        extensions = [
            "commands.chat",
            "commands.ai_control",
            "commands.image",
            "commands.ping",
            "commands.welcome",
            "commands.help",
            "commands.usage",
            "commands.voice",
            "commands.music",
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

        local_commands = self._application_command_names()
        log.info(
            "APPLICATION_COMMAND_TREE_LOCAL count=%s has_usage=%s names=%s",
            len(local_commands),
            "usage" in local_commands,
            ",".join(local_commands),
        )

        # Sync slash commands globally (or to a test guild if set)
        guild_id = os.getenv("TEST_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            scope = f"guild:{guild_id}"
            log.info(
                "APPLICATION_COMMAND_SYNC scope=%s count=%s names=%s",
                scope,
                len(synced),
                ",".join(sorted(command.name for command in synced)),
            )
            await self._log_remote_command_state(guild, scope)
        else:
            synced = await self.tree.sync()
            scope = "global"
            log.info(
                "APPLICATION_COMMAND_SYNC scope=%s count=%s names=%s",
                scope,
                len(synced),
                ",".join(sorted(command.name for command in synced)),
            )
            await self._log_remote_command_state(None, scope)

    def _application_command_names(self) -> list[str]:
        """Return local root command names without exposing command details."""
        return sorted(command.name for command in self.tree.get_commands())

    async def _log_remote_command_state(
        self,
        guild: discord.abc.Snowflake | None,
        scope: str,
    ) -> None:
        """Compare Discord's registered names with the local tree after sync."""
        try:
            remote = await self.tree.fetch_commands(guild=guild)
        except discord.HTTPException:
            log.exception(
                "APPLICATION_COMMAND_REMOTE_CHECK_FAILED scope=%s",
                scope,
            )
            return

        remote_names = sorted(command.name for command in remote)
        local_names = self._application_command_names()
        log.info(
            "APPLICATION_COMMAND_REMOTE scope=%s count=%s has_usage=%s names=%s",
            scope,
            len(remote_names),
            "usage" in remote_names,
            ",".join(remote_names),
        )
        missing = sorted(set(local_names) - set(remote_names))
        unexpected = sorted(set(remote_names) - set(local_names))
        if missing or unexpected:
            log.warning(
                "APPLICATION_COMMAND_SCOPE_MISMATCH scope=%s missing=%s unexpected=%s",
                scope,
                ",".join(missing) or "none",
                ",".join(unexpected) or "none",
            )
        if "usage" not in remote_names:
            log.warning(
                "APPLICATION_COMMAND_USAGE_NOT_VISIBLE scope=%s "
                "global_commands_may_need_propagation_or_guild_scope_may_differ",
                scope,
            )

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        log.exception(f"Unhandled error in event '{event_method}'")

    async def close(self) -> None:
        """Disconnect voice clients before closing the Discord connection."""
        music_cog = self.get_cog("Music")
        if music_cog is not None and hasattr(music_cog, "shutdown"):
            await music_cog.shutdown()
        for voice_client in tuple(self.voice_clients):
            try:
                await voice_client.disconnect(force=True)
            except (asyncio.TimeoutError, discord.DiscordException, OSError) as exc:
                log.error("Could not disconnect voice client during shutdown: %s", exc)
        await super().close()


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────
async def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        log.critical("DISCORD_BOT_TOKEN is not set. Check your .env file.")
        sys.exit(1)

    lock = SingleInstanceLock(Path(__file__).resolve().parent / "data" / "roselinne.lock")
    if not lock.acquire():
        log.critical("Another Roselinne process is already running; exiting.")
        return

    try:
        bot = RoselinneBot()
        log.info(
            "BOT_PROCESS_LOCK_ACQUIRED process_id=%s instance_id=%s",
            os.getpid(),
            bot.instance_id,
        )
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
    finally:
        lock.release()


if __name__ == "__main__":
    asyncio.run(main())
