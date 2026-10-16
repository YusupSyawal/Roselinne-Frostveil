"""Local AI token and request usage commands."""

from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotSettings
from utils.usage_monitor import UsageMonitor, utc_period_bounds


class UsageCog(commands.Cog, name="Usage"):
    """Show local accounting without claiming provider quota visibility."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()
        self.monitor: UsageMonitor = bot.usage_monitor

    @app_commands.command(name="usage", description="Show local AI usage statistics.")
    @app_commands.describe(
        section="Choose summary, limits, or reset",
        confirm="Required for reset; this only deletes local usage rows",
    )
    @app_commands.choices(
        section=[
            app_commands.Choice(name="summary", value="summary"),
            app_commands.Choice(name="limits", value="limits"),
            app_commands.Choice(name="reset", value="reset"),
        ]
    )
    async def usage(
        self,
        interaction: discord.Interaction,
        section: Literal["summary", "limits", "reset"] = "summary",
        confirm: bool = False,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "❄️ Usage statistics are available inside a server only.",
                ephemeral=True,
            )
            return
        if section == "limits":
            await self._show_limits(interaction)
        elif section == "reset":
            await self._reset(interaction, confirm)
        else:
            await self._show_summary(interaction)

    async def _show_summary(self, interaction: discord.Interaction) -> None:
        day, month = utc_period_bounds()
        guild_id = interaction.guild_id
        totals = await self.monitor.totals(guild_id)
        today = await self.monitor.period_totals(guild_id, *day)
        this_month = await self.monitor.period_totals(guild_id, *month)
        breakdown = await self.monitor.by_provider_model(guild_id)

        embed = discord.Embed(
            title="AI Usage",
            description=(
                f"Provider aktif: `{self.settings.ai_provider}`\n"
                f"Model aktif: `{self._active_model()}`\n"
                "Angka berikut adalah statistik lokal Roselinne, bukan kuota resmi provider."
            ),
            color=self.settings.COLOR_PRIMARY,
        )
        embed.add_field(
            name="Total",
            value=self._format_totals(totals),
            inline=False,
        )
        embed.add_field(name="Hari ini (UTC)", value=self._format_totals(today), inline=True)
        embed.add_field(name="Bulan ini (UTC)", value=self._format_totals(this_month), inline=True)
        if breakdown:
            lines = [
                f"`{row['provider']}/{row['model']}`: "
                f"{row['requests']} req, {row['total_tokens']:,} token"
                for row in breakdown[:5]
            ]
            embed.add_field(name="Provider / model", value="\n".join(lines), inline=False)
        embed.set_footer(text="Token estimasi ditandai; request gagal tetap dihitung sebagai request.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _show_limits(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="AI Provider Limits",
            description=(
                f"Provider aktif: `{self.settings.ai_provider}`\n"
                "Tidak tersedia: kuota akun resmi atau persentase kuota yang dapat "
                "diverifikasi dari API/response header yang saat ini disimpan proyek."
            ),
            color=self.settings.COLOR_WARNING,
        )
        embed.add_field(
            name="Batas resmi",
            value="Tidak tersedia melalui adapter provider saat ini.",
            inline=False,
        )
        embed.add_field(
            name="Catatan",
            value=(
                "Statistik lokal tidak dibandingkan dengan limit provider. "
                "Peringatan 70%/85%/95% dinonaktifkan agar tidak menghasilkan "
                "persentase yang menyesatkan."
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _reset(self, interaction: discord.Interaction, confirm: bool) -> None:
        if not self._can_reset(interaction):
            await interaction.response.send_message(
                "❄️ Hanya administrator atau server owner yang dapat mereset statistik.",
                ephemeral=True,
            )
            return
        if not confirm:
            await interaction.response.send_message(
                "Konfirmasi diperlukan. Jalankan `/usage section:reset confirm:true`.\n"
                "Ini hanya menghapus statistik lokal; tidak mereset kuota "
                "Groq/OpenAI/Gemini dan tidak menyentuh memory percakapan.",
                ephemeral=True,
            )
            return
        deleted = await self.monitor.reset(interaction.guild_id or 0)
        await interaction.response.send_message(
            f"❄️ {deleted} catatan penggunaan lokal dihapus. "
            "Memory percakapan dan kuota provider tidak berubah.",
            ephemeral=True,
        )

    @staticmethod
    def _can_reset(interaction: discord.Interaction) -> bool:
        user = interaction.user
        if interaction.guild is not None and interaction.guild.owner_id == user.id:
            return True
        permissions = getattr(user, "guild_permissions", None)
        return bool(permissions and permissions.administrator)

    def _active_model(self) -> str:
        return {
            "openai": self.settings.openai_model,
            "groq": self.settings.groq_model,
            "gemini": self.settings.gemini_model,
            "ollama": self.settings.ollama_model,
        }.get(self.settings.ai_provider, "Tidak tersedia")

    @staticmethod
    def _format_totals(totals) -> str:
        estimated = totals.estimated_input_tokens + totals.estimated_output_tokens
        token_label = f"{totals.total_tokens:,}"
        if estimated:
            token_label += f" (estimasi {estimated:,})"
        return (
            f"Request: `{totals.requests:,}`\n"
            f"Input: `{totals.input_tokens:,}`\n"
            f"Output: `{totals.output_tokens:,}`\n"
            f"Total token: `{token_label}`"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UsageCog(bot))
