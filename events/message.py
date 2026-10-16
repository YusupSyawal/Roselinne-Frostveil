"""
events/message.py
on_message handler — respond to @mentions and slash commands.
"""

import logging
import os
from typing import Optional

import discord
from discord.ext import commands

from ai.ai_client import AIClient
from ai.memory import MemoryManager
from ai.prompt_builder import build_messages, load_system_prompt
from ai.vision_analyzer import VisionAnalyzer
from config.settings import BotSettings
from utils.cooldown import cooldown_manager
from utils.image import ImageHandler
from utils.ai_workflow import AIWorkflowRegistry

log = logging.getLogger("roselinne.events.message")

class MessageCog(commands.Cog, name="Message"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()
        self.ai = AIClient(
            self.settings, getattr(bot, "usage_monitor", None)
        )
        self.vision = VisionAnalyzer(
            self.settings, getattr(bot, "usage_monitor", None)
        )
        self.image_handler = ImageHandler()
        self.memory = MemoryManager(self.settings)
        self.system_prompt = load_system_prompt(self.settings.personality_file)
        registry = getattr(bot, "ai_workflow_registry", None)
        if registry is None:
            registry = AIWorkflowRegistry()
            bot.ai_workflow_registry = registry
        self.workflow_registry: AIWorkflowRegistry = registry

    def _workflow_registry(self) -> AIWorkflowRegistry:
        registry = getattr(self, "workflow_registry", None)
        if not isinstance(registry, AIWorkflowRegistry):
            registry = getattr(self.bot, "ai_workflow_registry", None)
            if not isinstance(registry, AIWorkflowRegistry):
                registry = AIWorkflowRegistry()
                self.bot.ai_workflow_registry = registry
            self.workflow_registry = registry
        return registry

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        correlation: dict[str, object] = {
            "message_id": message.id,
            "guild_id": message.guild.id if message.guild else 0,
            "channel_id": getattr(message.channel, "id", 0),
            "process_id": os.getpid(),
            "instance_id": getattr(self.bot, "instance_id", "unknown"),
            "handler": type(self).__name__,
        }
        log.debug("MESSAGE_RECEIVED %s", correlation)
        if message.author.bot:
            log.debug("MESSAGE_IGNORED reason=bot_author %s", correlation)
            return

        username = getattr(message.author, "name", "") or ""
        display_name = getattr(message.author, "display_name", "") or username
        user_id = message.author.id
        ai_enabled = await self.bot.runtime_state.is_ai_enabled(
            message.guild.id if message.guild else 0
        )
        has_image = any(
            self._is_image_attachment(attachment)
            for attachment in message.attachments
        )
        is_mention = bool(
            self.bot.user
            and message.mentions
            and self.bot.user in message.mentions
        )
        if ai_enabled and (has_image or is_mention):
            workflow = await self._workflow_registry().start(message.id)
            if workflow is None:
                log.warning("DUPLICATE_SUPPRESSED %s", correlation)
                return
            correlation["workflow_id"] = workflow.workflow_id
            log.debug("MESSAGE_ACCEPTED %s", correlation)
        else:
            log.debug("MESSAGE_IGNORED reason=not_ai_route %s", correlation)

        log.debug(
            "HANDLER_ENTER username_present=%s display_name_present=%s %s",
            bool(username),
            bool(display_name),
            correlation,
        )

        # ── Check for images in attachments ────────────────
        if ai_enabled and has_image and not is_mention:
            image_attachments = [
                att for att in message.attachments
                if self._is_image_attachment(att)
            ]
            if image_attachments:
                try:
                    log.debug("ROUTE_SELECTED path=image %s", correlation)
                    async with message.channel.typing():
                        reply = await self._generate_image_reply(
                            image_attachments[0], username, display_name, user_id,
                            message.guild.id if message.guild else 0, str(message.id)
                        )
                    if reply is not None:
                        await self._send_ai_reply(message, reply, correlation)
                        await self.memory.add_message(
                            message.guild.id if message.guild else 0,
                            user_id,
                            "user",
                            f"[Sent an image: {image_attachments[0].filename}]",
                            message.id,
                        )
                        await self.memory.add_message(
                            message.guild.id if message.guild else 0,
                            user_id,
                            "assistant",
                            reply,
                            message.id,
                        )
                    else:
                        await self._workflow_registry().finish(message.id)
                except Exception as exc:
                    await self._finish_with_error(message, correlation, exc)
                return

        # ── Check if bot is mentioned ──────────────────────
        if ai_enabled and is_mention:
            log.debug("ROUTE_SELECTED path=mention %s", correlation)
            # Remove the mention from the message to get the actual content
            content = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
            
            if not content:
                await self._send_ai_reply(
                    message,
                    "Mm. You've called my name, but have nothing to say?",
                    correlation,
                )
                return

            # ── Cooldown check ────────────────────────────
            guild_id = message.guild.id if message.guild else 0
            
            remaining = cooldown_manager.check(user_id, "chat", self.settings.cooldown_seconds)
            if remaining is not None:
                await self._send_ai_reply(
                    message,
                    f"❄️ Patience is a virtue. Try again in **{remaining:.1f}s**.",
                    correlation,
                )
                return
            
            cooldown_manager.consume(user_id, "chat")

            # ── Show typing indicator ─────────────────────
            async with message.channel.typing():
                try:
                    reply = await self._get_reply(
                        message.guild.id if message.guild else 0,
                        user_id,
                        username,
                        display_name,
                        content,
                        message.id,
                        request_id=str(message.id),
                    )
                    await self._send_ai_reply(message, reply, correlation)
                except Exception as exc:
                    await self._finish_with_error(message, correlation, exc)
            return

        # Process prefix commands (kept for admin/debug use)
        await self.bot.process_commands(message)
        log.debug("HANDLER_EXIT outcome=commands %s", correlation)

    async def _send_ai_reply(
        self,
        message: discord.Message,
        reply: str,
        correlation: dict[str, object],
    ) -> None:
        await self._workflow_registry().mark_send_attempted(message.id)
        log.debug("RESPONSE_SEND_START %s send_attempt=1", correlation)
        try:
            await message.reply(reply, mention_author=False)
        except Exception:
            log.exception("RESPONSE_SEND_FAILURE %s", correlation)
            raise
        await self._workflow_registry().mark_send_succeeded(message.id)
        log.info("RESPONSE_SEND_SUCCESS %s send_attempt=1 outcome=sent", correlation)

    async def _finish_with_error(
        self,
        message: discord.Message,
        correlation: dict[str, object],
        exc: Exception,
    ) -> None:
        log.error(
            "WORKFLOW_EXCEPTION %s exception_class=%s",
            correlation,
            type(exc).__name__,
            exc_info=True,
        )
        try:
            state = await self._workflow_registry().get(message.id)
        except KeyError:
            return
        if state is None or state.send_succeeded or state.send_attempted:
            await self._workflow_registry().finish(message.id)
            return
        log.warning("FALLBACK_START %s", correlation)
        try:
            await self._send_ai_reply(
                message,
                "❄️ Sesuatu mengganggu aliran sihirku. Coba lagi nanti.",
                correlation,
            )
        finally:
            await self._workflow_registry().finish(message.id)
            log.info("FALLBACK_END %s", correlation)

    async def _get_reply(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        display_name: str,
        message_text: str,
        source_message_id: int | None = None,
        request_id: str | None = None,
    ) -> str:
        """Fetch AI reply and persist conversation."""
        if not await self.bot.runtime_state.is_ai_enabled(guild_id):
            return "❄️ AI sedang OFF di server ini."

        log.debug("AI_WORKFLOW_START message_id=%s", source_message_id)
        history = await self.memory.get_history(guild_id, user_id)
        messages = build_messages(self.system_prompt, history, message_text)
        log.debug(
            "AI_PROMPT_READY guild_id=%s source_message_id=%s history_messages=%s "
            "user_inputs=%s",
            guild_id,
            source_message_id or "unknown",
            len(history),
            sum(1 for item in messages if item.get("role") == "user"),
        )

        try:
            log.debug("AI_GENERATION_START message_id=%s attempt=1", source_message_id)
            reply = await self.ai.chat(
                messages,
                username=username,
                display_name=display_name,
                user_id=user_id,
                guild_id=guild_id,
                request_id=request_id,
            )
        except RuntimeError as e:
            log.error(f"AI error for user {user_id}: {e}")
            return (
                "Mm. Something has gone awry on my end. "
                "The spirits of the ether are uncooperative today."
            )

        # Persist conversation
        await self.memory.add_message(
            guild_id,
            user_id,
            "user",
            message_text,
            source_message_id,
        )
        await self.memory.add_message(
            guild_id,
            user_id,
            "assistant",
            reply,
            source_message_id,
        )

        log.debug("AI_GENERATION_END message_id=%s outcome=success", source_message_id)
        return reply

    @staticmethod
    def _is_image_attachment(attachment: discord.Attachment) -> bool:
        """Accept Discord image MIME types and common image filename extensions."""
        if attachment.content_type:
            return attachment.content_type.lower().split(";", 1)[0].startswith("image/")
        return attachment.filename.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp")
        )

    async def _generate_image_reply(
        self,
        attachment: discord.Attachment,
        username: str,
        display_name: str,
        user_id: int,
        guild_id: int,
        request_id: str,
    ) -> Optional[str]:
        """Generate one image response; the workflow owner performs the send."""
        if not VisionAnalyzer.is_vision_supported(self.settings.ai_provider):
            log.debug("AI_WORKFLOW_IMAGE_IGNORED reason=unsupported_provider")
            return None
        if not attachment.url:
            return None
        image_data = await self.image_handler.download_image(attachment.url)
        if not image_data or not self.image_handler.validate_image(image_data):
            return None
        compressed = self.image_handler.compress_image(image_data)
        prompt = (
            "You are Roselinne Frostveil, an elegant and slightly sarcastic AI. "
            "RESPOND ONLY IN INDONESIAN (Bahasa Indonesia). "
            f"USER INFORMATION (metadata Discord): Username: {username}; "
            f"Display Name: {display_name}; User ID: {user_id}. "
            "Comment briefly and wittily on this image in 1-2 sentences."
        )
        log.debug("AI_GENERATION_START mode=image attempt=1")
        analysis = await self.vision.analyze_image(
            compressed,
            prompt,
            username=username,
            display_name=display_name,
            user_id=user_id,
            guild_id=guild_id,
            request_id=request_id,
        )
        log.debug("AI_GENERATION_END mode=image outcome=%s", "success" if analysis else "empty")
        return analysis

    async def _analyze_image_react(self, image_data: bytes, attachment_name: str) -> Optional[str]:
        """Generate a witty reaction to an image."""
        prompt = (
            "You are Roselinne Frostveil, an elegant noble of the Winter Court. "
            "Respond ONLY in Indonesian (Bahasa Indonesia). "
            "Look at this image and give a brief, clever comment about it. "
            "Be witty, insightful, but not overly serious. "
            "Keep it to 1-2 sentences. HANYA BAHASA INDONESIA!"
        )

        return await self.vision.analyze_image(image_data, prompt)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        # Re-process edited messages for prefix commands if needed
        if after.author.bot:
            return
        await self.bot.process_commands(after)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Catch prefix-command errors gracefully."""
        if isinstance(error, commands.CommandNotFound):
            return  # silently ignore unknown prefix commands
        log.warning(f"Command error in {ctx.command}: {error}")

    @commands.Cog.listener()
    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Global handler for slash-command errors."""
        log.error(f"App command error [{interaction.command}]: {error}", exc_info=True)

        msg = "Something unexpected happened. My apologies — the frost sometimes interferes."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageCog(bot))
