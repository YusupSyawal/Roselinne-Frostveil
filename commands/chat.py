"""
commands/chat.py
Slash commands for AI chat interaction:
  /chat          — send a message to Roselinne
  /resetmemory   — clear conversation history
  /personality   — show bot info & memory stats
"""

import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ai.ai_client import AIClient
from ai.memory import MemoryManager
from ai.prompt_builder import build_messages, load_system_prompt
from ai.response_enhancer import ResponseEnhancer
from config.settings import BotSettings
from utils.cooldown import cooldown_manager

log = logging.getLogger("roselinne.commands.chat")


class ChatCog(commands.Cog, name="Chat"):
    """AI chat commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()
        self.ai = AIClient(self.settings)
        self.enhancer = ResponseEnhancer(self.ai)
        self.enhancer.enable_verification(self.settings.enable_verification)
        self.memory = MemoryManager(self.settings)
        self.system_prompt = load_system_prompt(self.settings.personality_file)
        log.info("ChatCog loaded.")

    # ── /chat ─────────────────────────────────────────────

    @app_commands.command(name="chat", description="Speak with Roselinne Frostveil.")
    @app_commands.describe(message="What would you like to say?")
    async def chat(self, interaction: discord.Interaction, message: str) -> None:
        user_id = interaction.user.id
        guild_id = interaction.guild_id or 0
        if not await self.bot.runtime_state.is_ai_enabled(guild_id):
            await interaction.response.send_message(
                "❄️ AI sedang OFF di server ini. Moderator dan command lain tetap aktif.",
                ephemeral=True,
            )
            return

        log.info(
            "[CHATBOT USER]\nUsername: %s\nDisplay Name: %s\nUser ID: %s\nMessage: %s",
            interaction.user.name,
            interaction.user.display_name,
            user_id,
            message,
        )

        # ── Cooldown check ────────────────────────────────
        remaining = cooldown_manager.check(user_id, "chat", self.settings.cooldown_seconds)
        if remaining is not None:
            embed = discord.Embed(
                description=f"❄️  Patience is a virtue. Try again in **{remaining:.1f}s**.",
                color=self.settings.COLOR_WARNING,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        cooldown_manager.consume(user_id, "chat")

        # ── Defer so we can take time ──────────────────────
        await interaction.response.defer(thinking=True)

        # ── Typing simulation (cosmetic, optional) ─────────
        try:
            if interaction.channel and hasattr(interaction.channel, "typing"):
                async with interaction.channel.typing():
                    reply = await self._get_reply(
                        guild_id,
                        user_id,
                        interaction.user.name,
                        interaction.user.display_name,
                        message,
                    )
            else:
                reply = await self._get_reply(
                    guild_id,
                    user_id,
                    interaction.user.name,
                    interaction.user.display_name,
                    message,
                )
        except discord.Forbidden:
            # Bot doesn't have permission to show typing — just get reply
            reply = await self._get_reply(
                guild_id,
                user_id,
                interaction.user.name,
                interaction.user.display_name,
                message,
            )

        # ── Send as plain text (no embed grid) ──────────────
        await interaction.followup.send(reply)

    async def _get_reply(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        display_name: str,
        message: str,
    ) -> str:
        """Fetch AI reply with web verification and persist both turns to memory."""
        if not await self.bot.runtime_state.is_ai_enabled(guild_id):
            return "❄️ AI sedang OFF di server ini."

        history = await self.memory.get_history(guild_id, user_id)
        messages = build_messages(self.system_prompt, history, message)

        try:
            # Use enhanced response generation with web verification
            reply = await self.enhancer.generate_verified_response(
                messages=messages,
                question=message,
                username=username,
                display_name=display_name,
                user_id=user_id,
            )
        except RuntimeError as e:
            log.error(f"AI error for user {user_id}: {e}")
            return (
                "Mm. Something has gone awry on my end. "
                "The spirits of the ether are uncooperative today. "
                f"\n*(Technical detail: {e})*"
            )

        # Persist conversation
        await self.memory.add_message(guild_id, user_id, "user", message)
        await self.memory.add_message(guild_id, user_id, "assistant", reply)

        return reply

    # ── /resetmemory ──────────────────────────────────────

    @app_commands.command(name="resetmemory", description="Erase your conversation history with Roselinne.")
    async def reset_memory(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0
        count = await self.memory.clear_history(guild_id, interaction.user.id)

        embed = discord.Embed(
            title="Memory Cleared",
            description=(
                f"I have set aside our previous exchanges. "
                f"*{count} message{'s' if count != 1 else ''}* have been dissolved into the frost.\n\n"
                "We begin again."
            ),
            color=self.settings.COLOR_INFO,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /personality ──────────────────────────────────────

    @app_commands.command(name="personality", description="Learn about Roselinne and view your conversation stats.")
    async def personality(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or 0
        stats = await self.memory.get_stats(guild_id, interaction.user.id)

        embed = discord.Embed(
            title="Roselinne Frostveil",
            description=(
                "Silver-tongued noble of the Winter Court. Keeper of quiet judgements "
                "and deliberate words. I assist — reluctantly at times, but thoroughly."
            ),
            color=self.settings.COLOR_PRIMARY,
        )
        embed.add_field(
            name="AI Provider",
            value=f"`{self.settings.ai_provider}` / `{self._model_name()}`",
            inline=True,
        )
        embed.add_field(
            name="Your Messages",
            value=str(stats.get("total", 0)),
            inline=True,
        )
        embed.add_field(
            name="Memory Limit",
            value=f"{self.settings.memory_max_messages} messages",
            inline=True,
        )

        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.set_footer(text="Use /resetmemory to clear your history.")
        await interaction.response.send_message(embed=embed)

    def _model_name(self) -> str:
        p = self.settings.ai_provider
        if p == "openai":   return self.settings.openai_model
        if p == "groq":     return self.settings.groq_model
        if p == "gemini":   return self.settings.gemini_model
        if p == "ollama":   return self.settings.ollama_model
        return "unknown"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChatCog(bot))
