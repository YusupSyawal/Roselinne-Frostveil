"""
commands/image.py
Slash commands for image analysis and commentary.
  /analyzeimage   — upload and analyze an image
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ai.vision_analyzer import VisionAnalyzer
from config.settings import BotSettings
from utils.cooldown import cooldown_manager
from utils.image import ImageHandler

log = logging.getLogger("roselinne.commands.image")


class ImageCog(commands.Cog, name="Image"):
    """Image analysis and commentary commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()
        self.vision = VisionAnalyzer(self.settings)
        self.image_handler = ImageHandler()
        log.info("ImageCog loaded.")

    @app_commands.command(
        name="analyzeimage",
        description="Upload an image for Roselinne to analyze and comment on."
    )
    @app_commands.describe(
        image="The image file to analyze",
        prompt="Optional: Ask Roselinne something specific about the image"
    )
    async def analyze_image(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        prompt: str = "Describe what you see in this image.",
    ) -> None:
        user_id = interaction.user.id
        if not await self.bot.runtime_state.is_ai_enabled(interaction.guild_id or 0):
            await interaction.response.send_message(
                "❄️ AI sedang OFF di server ini. Analisis gambar dinonaktifkan.",
                ephemeral=True,
            )
            return

        # ── Check if vision is supported ───────────────────
        if not VisionAnalyzer.is_vision_supported(self.settings.ai_provider):
            embed = discord.Embed(
                title="Vision Not Available",
                description=(
                    f"Image analysis requires Groq, OpenAI, or Gemini. "
                    f"Current provider: `{self.settings.ai_provider}`"
                ),
                color=self.settings.COLOR_WARNING,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # ── Validate attachment ────────────────────────────
        content_type = (image.content_type or "").lower().split(";", 1)[0]
        has_image_extension = image.filename.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp")
        )
        if not content_type.startswith("image/") and not has_image_extension:
            embed = discord.Embed(
                title="Invalid File",
                description="Please upload an image file (JPEG, PNG, GIF, WebP).",
                color=self.settings.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # ── Cooldown check ────────────────────────────────
        remaining = cooldown_manager.check(user_id, "image", self.settings.cooldown_seconds * 2)
        if remaining is not None:
            embed = discord.Embed(
                description=f"❄️ Images require more careful consideration. Try again in **{remaining:.1f}s**.",
                color=self.settings.COLOR_WARNING,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        cooldown_manager.consume(user_id, "image")

        # ── Defer to show we're thinking ───────────────────
        await interaction.response.defer(thinking=True)

        # ── Download and process image ─────────────────────
        try:
            image_data = await self.image_handler.download_image(image.url)
            
            if not image_data:
                await interaction.followup.send(
                    "❄️ I could not download the image. Please try again.",
                    ephemeral=True
                )
                return

            # ── Validate image ────────────────────────────
            if not self.image_handler.validate_image(image_data):
                await interaction.followup.send(
                    "❄️ The image appears to be corrupted or unreadable.",
                    ephemeral=True
                )
                return

            # ── Get image dimensions ──────────────────────
            img_info = self.image_handler.get_image_info(image_data)
            if img_info:
                fmt, w, h = img_info
                log.info(f"Analyzing image: {fmt} ({w}x{h}) from {interaction.user.name}")

            # ── Compress for faster processing ────────────
            compressed = self.image_handler.compress_image(image_data)

            # ── Analyze with personality ──────────────────
            analysis_prompt = (
                "You are Roselinne Frostveil, an elegant and slightly sarcastic AI assistant. "
                "RESPOND ONLY IN INDONESIAN (Bahasa Indonesia). "
                "Be witty, insightful, and thoughtful. "
                f"User asks: {prompt}\n"
                "Provide a detailed but concise analysis. HANYA BAHASA INDONESIA!"
            )

            analysis = await self.vision.analyze_image(
                compressed,
                analysis_prompt,
                username=interaction.user.name,
                display_name=interaction.user.display_name,
                user_id=user_id,
            )

            if not analysis:
                await interaction.followup.send(
                    "❄️ I had difficulty analyzing that image. Perhaps the spirits were uncooperative.",
                    ephemeral=True
                )
                return

            # ── Format and send response ──────────────────
            embed = discord.Embed(
                title=f"Image Analysis: {image.filename}",
                description=analysis,
                color=self.settings.COLOR_PRIMARY,
            )
            embed.set_thumbnail(url=image.url)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            log.error(f"Image analysis error for user {user_id}: {e}")
            await interaction.followup.send(
                f"❄️ An error occurred: {str(e)[:100]}",
                ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImageCog(bot))
