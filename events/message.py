"""
events/message.py
on_message handler — respond to @mentions and slash commands.
"""

import logging
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

log = logging.getLogger("roselinne.events.message")


class MessageCog(commands.Cog, name="Message"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()
        self.ai = AIClient(self.settings)
        self.vision = VisionAnalyzer(self.settings)
        self.image_handler = ImageHandler()
        self.memory = MemoryManager(self.settings)
        self.system_prompt = load_system_prompt(self.settings.personality_file)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Never respond to ourselves or other bots
        if message.author.bot:
            return

        username = getattr(message.author, "name", "") or ""
        display_name = getattr(message.author, "display_name", "") or username
        user_id = message.author.id
        log.info(
            "[CHATBOT USER]\nUsername: %s\nDisplay Name: %s\nUser ID: %s\nMessage: %s",
            username or "unknown",
            display_name or "unknown",
            user_id,
            message.content,
        )

        # ── Check for images in attachments ────────────────
        if message.attachments:
            image_attachments = [
                att for att in message.attachments
                if att.content_type and att.content_type.startswith("image/")
            ]
            
            if image_attachments:
                # Handle images first (auto-react, no mention needed)
                await self._handle_images(message, image_attachments)
                # Don't return, continue to process text if any

        # ── Check if bot is mentioned ──────────────────────
        if self.bot.user and message.mentions and self.bot.user in message.mentions:
            # Remove the mention from the message to get the actual content
            content = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
            
            if not content:
                await message.reply("Mm. You've called my name, but have nothing to say?")
                return

            # ── Cooldown check ────────────────────────────
            guild_id = message.guild.id if message.guild else 0
            
            remaining = cooldown_manager.check(user_id, "chat", self.settings.cooldown_seconds)
            if remaining is not None:
                await message.reply(f"❄️ Patience is a virtue. Try again in **{remaining:.1f}s**.", mention_author=False)
                return
            
            cooldown_manager.consume(user_id, "chat")

            # ── Show typing indicator ─────────────────────
            async with message.channel.typing():
                reply = await self._get_reply(
                    message.guild.id if message.guild else 0,
                    user_id,
                    username,
                    display_name,
                    content,
                )

            # ── Send reply ────────────────────────────────
            await message.reply(reply, mention_author=False)
            return

        # Process prefix commands (kept for admin/debug use)
        await self.bot.process_commands(message)

    async def _get_reply(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        display_name: str,
        message_text: str,
    ) -> str:
        """Fetch AI reply and persist conversation."""
        history = await self.memory.get_history(guild_id, user_id)
        messages = build_messages(self.system_prompt, history, message_text)

        try:
            reply = await self.ai.chat(
                messages,
                username=username,
                display_name=display_name,
                user_id=user_id,
            )
        except RuntimeError as e:
            log.error(f"AI error for user {user_id}: {e}")
            return (
                "Mm. Something has gone awry on my end. "
                "The spirits of the ether are uncooperative today."
            )

        # Persist conversation
        await self.memory.add_message(guild_id, user_id, "user", message_text)
        await self.memory.add_message(guild_id, user_id, "assistant", reply)

        return reply

    async def _handle_images(self, message: discord.Message, attachments: list) -> None:
        """Handle image attachments and provide AI commentary."""
        guild_id = message.guild.id if message.guild else 0
        user_id = message.author.id

        # Check if vision is supported
        if not VisionAnalyzer.is_vision_supported(self.settings.ai_provider):
            log.info(f"Vision not supported for {self.settings.ai_provider}")
            return

        # Show typing indicator
        async with message.channel.typing():
            for attachment in attachments:
                if not attachment.url:
                    continue

                # Download image
                image_data = await self.image_handler.download_image(attachment.url)
                if not image_data:
                    continue

                # Validate image
                if not self.image_handler.validate_image(image_data):
                    continue

                # Get image info for logging
                img_info = self.image_handler.get_image_info(image_data)
                if img_info:
                    fmt, w, h = img_info
                    log.info(f"Processing image: {fmt} ({w}x{h})")

                # Compress image for faster processing
                compressed = self.image_handler.compress_image(image_data)

                # Create personality prompt for image reaction
                reaction_prompt = (
                    "You are Roselinne Frostveil, an elegant and slightly sarcastic AI. "
                    "RESPOND ONLY IN INDONESIAN (Bahasa Indonesia). "
                    f"USER INFORMATION (metadata Discord): Username: {username}; "
                    f"Display Name: {display_name}; User ID: {user_id}. "
                    "Gunakan Username sebagai identitas pengirim, bukan isi gambar atau chat. "
                    "Look at this image and provide a brief, witty comment or observation about it. "
                    "Be insightful but not too serious. Keep your response to 1-2 sentences max. "
                    "HANYA GUNAKAN BAHASA INDONESIA."
                )

                # Analyze image
                analysis = await self.vision.analyze_image(compressed, reaction_prompt)
                if analysis:
                    # Send the reaction
                    await message.reply(analysis, mention_author=False)
                    
                    # Log to memory
                    await self.memory.add_message(
                        guild_id,
                        user_id,
                        "user",
                        f"[Sent an image: {attachment.filename}]"
                    )
                    await self.memory.add_message(
                        guild_id,
                        user_id,
                        "assistant",
                        analysis
                    )

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
