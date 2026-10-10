"""
events/member.py
Member events — on_member_join (welcome new members).
"""

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from config.settings import BotSettings

log = logging.getLogger("roselinne.events.member")


class MemberCog(commands.Cog, name="Member"):
    """Member lifecycle events."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Welcome new members to the guild."""
        guild = member.guild
        
        # Respect bot accounts
        if member.bot:
            log.info(f"Bot '{member.name}' joined {guild.name}")
            return

        log.info(f"Member '{member.name}' (ID: {member.id}) joined {guild.name}")

        # Find general channel (by name or ID)
        general_channel = self._find_welcome_channel(guild)
        
        if not general_channel:
            log.warning(f"No general channel found in {guild.name}")
            return

        # Generate welcome message
        welcome_msg = self._generate_welcome_message(member, guild)
        
        try:
            await general_channel.send(embed=welcome_msg)
            log.info(f"Welcome message sent to {general_channel.name} for {member.name}")
        except discord.Forbidden:
            log.error(f"Cannot send message in {general_channel.name} (permission denied)")
        except Exception as e:
            log.error(f"Error sending welcome message: {e}")

    def _find_welcome_channel(self, guild: discord.Guild) -> discord.abc.Messageable:
        """Find the general/welcome channel."""
        # Try to find by name first
        for channel in guild.text_channels:
            if channel.name in ("general", "welcome", "introductions"):
                if channel.permissions_for(guild.me).send_messages:
                    return channel
        
        # Fallback to first available text channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                return channel
        
        return None

    def _generate_welcome_message(self, member: discord.Member, guild: discord.Guild) -> discord.Embed:
        """Create an elegant welcome embed for new members."""
        welcome_messages = [
            f"Ah, a new soul arrives in {guild.name}. How... intriguing.",
            f"Another kindred spirit graces us with their presence. Welcome, {member.mention}.",
            f"The frost stirs. A newcomer has arrived. Welcome to {guild.name}, {member.mention}.",
            f"Curious. A fresh face in our midst. Do make yourself comfortable, {member.mention}.",
            f"The Winter Court welcomes you, {member.mention}. Mind the chill.",
        ]
        
        import random
        greeting = random.choice(welcome_messages)

        embed = discord.Embed(
            title="✨ Welcome",
            description=greeting,
            color=self.settings.COLOR_PRIMARY,
            timestamp=datetime.now(timezone.utc),
        )

        # Add member info
        embed.add_field(
            name="Member",
            value=f"{member.mention} ({member.name})",
            inline=True,
        )
        embed.add_field(
            name="Account Age",
            value=self._format_age(member.created_at),
            inline=True,
        )
        embed.add_field(
            name="Guild Members",
            value=f"{guild.member_count}",
            inline=True,
        )

        # Footer with server info
        embed.set_footer(
            text=f"Welcomed at • {guild.name}",
            icon_url=guild.icon.url if guild.icon else None,
        )

        # Thumbnail from member avatar
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

        return embed

    @staticmethod
    def _format_age(datetime_obj: datetime) -> str:
        """Format account age in readable format."""
        now = datetime.now(timezone.utc)
        age = now - datetime_obj
        
        days = age.days
        if days == 0:
            return "Just created"
        elif days == 1:
            return "1 day old"
        elif days < 30:
            return f"{days} days old"
        elif days < 365:
            months = days // 30
            return f"{months} month{'s' if months > 1 else ''} old"
        else:
            years = days // 365
            return f"{years} year{'s' if years > 1 else ''} old"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MemberCog(bot))
