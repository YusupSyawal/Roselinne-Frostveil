"""Mini Music commands and per-guild playback management."""

from __future__ import annotations

import asyncio
import ipaddress
import threading
import logging
import re
import socket
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotSettings

log = logging.getLogger("roselinne.commands.music")

IDLE_TIMEOUT_SECONDS = 5 * 60
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
SPOTIFY_HOSTS = {"open.spotify.com", "play.spotify.com", "spotify.com"}


class MusicInputError(ValueError):
    """Raised when a media URL cannot be accepted or resolved."""


class _FFmpegDiagnosticSink:
    """Bounded stderr sink; never stores URLs, cookies, or signed query values."""

    def __init__(self, limit: int = 8192):
        self._limit = limit
        self._buffer = bytearray()
        self._lock = threading.Lock()

    def write(self, data: bytes) -> int:
        with self._lock:
            self._buffer.extend(data[-self._limit:])
            del self._buffer[:-self._limit]
        return len(data)

    def flush(self) -> None:
        return None

    def snapshot(self) -> str:
        with self._lock:
            return bytes(self._buffer).decode("utf-8", errors="replace").strip()


def _safe_diagnostic_text(value: object) -> str:
    """Keep diagnostics useful without logging URLs or query credentials."""
    return re.sub(r"https?://\S+", "<redacted-url>", str(value))


def validate_media_url(raw_url: str) -> str:
    """Validate URL syntax and reject local/internal destinations."""
    value = raw_url.strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise MusicInputError("URL harus menggunakan HTTP atau HTTPS yang valid.")
    if parsed.username or parsed.password:
        raise MusicInputError("URL dengan kredensial tertanam tidak didukung.")

    host = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local
                                or address.is_reserved or address.is_multicast or address.is_unspecified):
        raise MusicInputError("Alamat lokal, privat, metadata cloud, atau internal tidak diizinkan.")
    if host in {"localhost", "localhost.localdomain", "metadata.google.internal", "instance-data"}:
        raise MusicInputError("Host internal tidak diizinkan.")

    if host not in YOUTUBE_HOSTS and host not in SPOTIFY_HOSTS:
        raise MusicInputError("Sumber yang didukung hanya URL YouTube atau Spotify.")
    if host in YOUTUBE_HOSTS and "list" in parse_qs(parsed.query):
        raise MusicInputError("Playlist YouTube belum didukung; kirim URL satu video.")
    if host in SPOTIFY_HOSTS:
        resource_type = parsed.path.strip("/").split("/", 1)[0].lower()
        if resource_type != "track":
            raise MusicInputError("Playlist, album, dan episode Spotify belum didukung.")
    return value


async def validate_public_media_url(raw_url: str) -> str:
    """Validate syntax and DNS-resolve hostnames away from the event loop."""
    value = validate_media_url(raw_url)
    host = urlparse(value).hostname
    if host is None:
        raise MusicInputError("URL tidak memiliki host.")
    try:
        addresses = await asyncio.to_thread(
            lambda: {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        )
    except socket.gaierror as exc:
        raise MusicInputError("Host URL tidak dapat ditemukan.") from exc
    for address_text in addresses:
        address = ipaddress.ip_address(address_text)
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast or address.is_unspecified):
            raise MusicInputError("URL mengarah ke alamat lokal, privat, metadata cloud, atau internal.")
    return value


@dataclass(slots=True)
class Track:
    title: str
    webpage_url: str
    stream_url: str
    duration: int | None = None
    uploader: str | None = None


class YouTubeResolver:
    """Resolve one public YouTube video to a temporary audio stream URL."""

    def __init__(self, ffmpeg_path: str):
        self.ffmpeg_path = ffmpeg_path

    def _extract(self, url: str) -> Track:
        try:
            import yt_dlp
        except ImportError as exc:
            raise MusicInputError("Extractor YouTube belum terpasang. Instal dependency yt-dlp.") from exc

        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "format": "bestaudio[acodec!=none]/best[acodec!=none]",
        }
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=False)
        except Exception as exc:
            log.warning("YouTube extraction failed (%s)", type(exc).__name__)
            raise MusicInputError("Video YouTube tidak dapat diputar atau tidak tersedia.") from exc

        stream_url = info.get("url")
        title = info.get("title")
        if not stream_url or not title:
            raise MusicInputError("YouTube tidak menyediakan stream audio yang dapat diputar.")
        if not str(stream_url).lower().startswith(("http://", "https://")):
            raise MusicInputError("YouTube tidak menyediakan URL stream audio HTTP yang didukung.")
        log.info(
            "Resolved YouTube audio: ext=%s acodec=%s abr=%s tbr=%s protocol=%s",
            info.get("ext", "unknown"),
            info.get("acodec", "unknown"),
            info.get("abr", "unknown"),
            info.get("tbr", "unknown"),
            info.get("protocol", "unknown"),
        )
        return Track(
            title=str(title),
            webpage_url=str(info.get("webpage_url") or url),
            stream_url=str(stream_url),
            duration=info.get("duration"),
            uploader=info.get("uploader"),
        )

    async def resolve(self, url: str) -> Track:
        return await asyncio.to_thread(self._extract, url)


class SpotifyResolver:
    """Explicitly report the unsupported legitimate Spotify resolution path."""

    async def resolve(self, url: str) -> Track:
        del url
        raise MusicInputError(
            "URL Spotify diterima, tetapi resolver Spotify yang sah belum tersedia. "
            "Bot tidak dapat mencocokkan metadata ke sumber audio tanpa resolver resmi."
        )


@dataclass
class GuildPlayer:
    queue: deque[Track]
    current: Track | None = None
    idle_task: asyncio.Task | None = None
    playback_token: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    owns_voice_connection: bool = False
    last_text_channel: discord.abc.Messageable | None = None
    idle_notification_sent: bool = False
    idle_generation: int = 0


class MusicManager:
    """Owns guild queues and all playback state."""

    def __init__(self, bot: commands.Bot, settings: BotSettings):
        self.bot = bot
        self.settings = settings
        self.players: dict[int, GuildPlayer] = {}
        self.youtube = YouTubeResolver(settings.ffmpeg_path)
        self.spotify = SpotifyResolver()

    def player_for(self, guild_id: int) -> GuildPlayer:
        return self.players.setdefault(guild_id, GuildPlayer(deque()))

    async def resolve(self, url: str) -> Track:
        validated = await validate_public_media_url(url)
        host = urlparse(validated).hostname.rstrip(".").lower()  # type: ignore[union-attr]
        if host in SPOTIFY_HOSTS:
            return await self.spotify.resolve(validated)
        return await self.youtube.resolve(validated)

    async def enqueue(
        self,
        guild: discord.Guild,
        channel: discord.VoiceChannel,
        track: Track,
        text_channel: discord.abc.Messageable | None = None,
    ) -> bool:
        state = self.player_for(guild.id)
        async with state.lock:
            voice_client = guild.voice_client
            if voice_client is None or not voice_client.is_connected():
                state.playback_token += 1
                state.current = None
                self._cancel_idle(state)
                voice_client = await channel.connect(timeout=10.0, reconnect=True)
                state.owns_voice_connection = True
                log.info("Music voice connected in guild %s", guild.id)
            elif voice_client.channel and voice_client.channel.id != channel.id:
                await voice_client.move_to(channel)

            self._cancel_idle(state)
            state.idle_notification_sent = False
            if text_channel is not None:
                state.last_text_channel = text_channel
            state.queue.append(track)
            if not voice_client.is_playing() and not voice_client.is_paused():
                await self._play_next_locked(guild, state)
                return True
            return False

    async def play_next(self, guild: discord.Guild) -> None:
        state = self.player_for(guild.id)
        async with state.lock:
            await self._play_next_locked(guild, state)

    async def _play_next_locked(self, guild: discord.Guild, state: GuildPlayer) -> None:
        """Start one queued track; caller must hold state.lock."""
        voice_client = guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            return
        if voice_client.is_playing() or voice_client.is_paused():
            return
        if not state.queue:
            state.current = None
            self._schedule_idle(guild, state)
            return

        state.current = state.queue.popleft()
        state.playback_token += 1
        token = state.playback_token
        stderr_sink: _FFmpegDiagnosticSink | None = None
        try:
            stderr_sink = _FFmpegDiagnosticSink()
            source = discord.FFmpegPCMAudio(
                state.current.stream_url,
                executable=self.settings.ffmpeg_path,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
                stderr=stderr_sink,
            )
            loop = asyncio.get_running_loop()
            channel_bitrate = getattr(getattr(voice_client, "channel", None), "bitrate", None)
            bitrate = self.settings.music_opus_bitrate
            if isinstance(channel_bitrate, int):
                bitrate = max(16, min(bitrate, channel_bitrate))
            voice_client.play(
                source,
                after=self._make_after_callback(loop, guild, token, state, stderr_sink),
                application="audio",
                bitrate=bitrate,
                fec=self.settings.music_opus_fec,
                expected_packet_loss=self.settings.music_expected_packet_loss,
                bandwidth="full",
                signal_type="music",
            )
            log.info(
                "Playback started in guild %s: connected=%s playing=%s paused=%s bitrate=%s",
                guild.id,
                voice_client.is_connected(),
                voice_client.is_playing(),
                voice_client.is_paused(),
                bitrate,
            )
        except (discord.DiscordException, OSError, RuntimeError) as exc:
            log.error(
                "Could not start playback in guild %s: %s: %s",
                guild.id,
                type(exc).__name__,
                str(exc),
            )
            state.current = None
            if state.queue and guild.voice_client is not None and guild.voice_client.is_connected():
                await self._play_next_locked(guild, state)
            elif guild.voice_client is not None and guild.voice_client.is_connected():
                self._schedule_idle(guild, state)
            raise MusicInputError(
                "FFmpeg atau koneksi voice tidak dapat memulai audio. Pastikan FFmpeg terpasang."
            ) from exc

    def _make_after_callback(
        self,
        loop: asyncio.AbstractEventLoop,
        guild: discord.Guild,
        token: int,
        state: GuildPlayer,
        stderr_sink: _FFmpegDiagnosticSink,
    ):
        def after(error: Exception | None) -> None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._playback_finished(guild, token, error, state, stderr_sink),
                    loop,
                )
                future.add_done_callback(self._log_transition_failure)
            except RuntimeError as exc:
                log.warning(
                    "Playback callback could not reach event loop in guild %s: %s",
                    guild.id,
                    type(exc).__name__,
                )

        return after

    @staticmethod
    def _log_transition_failure(future: asyncio.Future) -> None:
        try:
            future.result()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("Unhandled Mini Music playback transition failure")

    async def _playback_finished(
        self,
        guild: discord.Guild,
        token: int,
        error: BaseException | None,
        state: GuildPlayer | None = None,
        stderr_sink: _FFmpegDiagnosticSink | None = None,
    ) -> None:
        state = state or self.players.get(guild.id)
        if state is None or self.players.get(guild.id) is not state:
            return
        async with state.lock:
            await self._advance_after_playback_locked(guild, state, token, error, stderr_sink)

    async def _advance_after_playback_locked(
        self,
        guild: discord.Guild,
        state: GuildPlayer,
        token: int,
        error: BaseException | None,
        stderr_sink: _FFmpegDiagnosticSink | None,
    ) -> None:
        """Finish the current track and advance; caller must hold state.lock."""
        if token != state.playback_token:
            return
        # Invalidate this callback before starting the next track. Discord may
        # deliver the same audio callback more than once during stop/reconnect.
        state.playback_token += 1
        if error:
            log.warning(
                "Playback ended in guild %s: %s: %s; ffmpeg_stderr=%s",
                guild.id,
                type(error).__name__,
                _safe_diagnostic_text(error),
                _safe_diagnostic_text(stderr_sink.snapshot()) if stderr_sink else "<unavailable>",
            )
        else:
            log.info("Playback finished normally in guild %s", guild.id)
        state.current = None
        voice_client = guild.voice_client
        if voice_client is not None and voice_client.is_connected() and state.queue:
            self._cancel_idle(state)
            await self._play_next_locked(guild, state)
        elif voice_client is not None and voice_client.is_connected():
            self._schedule_idle(guild, state)

    async def pause(self, guild: discord.Guild) -> bool:
        voice_client = guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            return True
        return False

    async def resume(self, guild: discord.Guild) -> bool:
        voice_client = guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            return True
        return False

    async def skip(self, guild: discord.Guild) -> bool:
        state = self.players.get(guild.id)
        if state is None:
            return False
        async with state.lock:
            voice_client = guild.voice_client
            if (
                voice_client
                and state.current is not None
                and (voice_client.is_playing() or voice_client.is_paused())
            ):
                try:
                    voice_client.stop()
                except (discord.DiscordException, RuntimeError, OSError) as exc:
                    log.warning(
                        "Could not stop playback in guild %s: %s",
                        guild.id,
                        type(exc).__name__,
                    )
                    return False
                # Do not rely on VoiceClient.stop() delivering its audio-thread
                # callback: it is asynchronous and can be lost during a
                # reconnect. The token invalidation above makes a later
                # callback harmless, so this is exactly one transition.
                await self._advance_after_playback_locked(
                    guild,
                    state,
                    state.playback_token,
                    None,
                    None,
                )
                return True
            return False

    async def stop(self, guild: discord.Guild) -> None:
        state = self.player_for(guild.id)
        async with state.lock:
            state.queue.clear()
            voice_client = guild.voice_client
            if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
                voice_client.stop()
            else:
                state.current = None
                if voice_client and voice_client.is_connected():
                    self._schedule_idle(guild, state)

    async def leave(self, guild: discord.Guild) -> None:
        state = self.player_for(guild.id)
        async with state.lock:
            state.queue.clear()
            self._cancel_idle(state)
            state.playback_token += 1
            voice_client = guild.voice_client
            if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
                voice_client.stop()
            if state.owns_voice_connection and voice_client and voice_client.is_connected():
                await voice_client.disconnect()
            state.current = None
            self.players.pop(guild.id, None)

    def _cancel_idle(self, state: GuildPlayer) -> None:
        state.idle_generation += 1
        if state.idle_task and not state.idle_task.done():
            state.idle_task.cancel()
        state.idle_task = None

    def _schedule_idle(self, guild: discord.Guild, state: GuildPlayer) -> None:
        if not state.owns_voice_connection:
            return
        self._cancel_idle(state)
        state.idle_notification_sent = False
        generation = state.idle_generation
        state.idle_task = asyncio.create_task(self._idle_disconnect(guild, state, generation))

    async def _idle_disconnect(
        self,
        guild: discord.Guild,
        state: GuildPlayer,
        generation: int | None = None,
    ) -> None:
        generation = state.idle_generation if generation is None else generation
        try:
            await asyncio.sleep(IDLE_TIMEOUT_SECONDS)
            async with state.lock:
                if (
                    self.players.get(guild.id) is not state
                    or state.idle_task is not asyncio.current_task()
                    or state.idle_generation != generation
                ):
                    return
                voice_client = guild.voice_client
                if (
                    not state.owns_voice_connection
                    or state.queue
                    or state.current is not None
                    or voice_client is None
                    or not voice_client.is_connected()
                    or voice_client.is_playing()
                    or voice_client.is_paused()
                ):
                    return
                state.idle_notification_sent = True
                await voice_client.disconnect()
                self.players.pop(guild.id, None)
                await self._notify_idle(state)
        except asyncio.CancelledError:
            raise
        except (discord.DiscordException, OSError) as exc:
            log.warning("Idle voice cleanup failed in guild %s: %s", guild.id, type(exc).__name__)

    async def _notify_idle(self, state: GuildPlayer) -> None:
        if not state.last_text_channel:
            return
        try:
            await state.last_text_channel.send("❄️ Saya keluar dari voice channel karena tidak ada musik selama 5 menit.")
        except (discord.DiscordException, OSError, AttributeError) as exc:
            log.debug("Could not send music idle notification: %s", type(exc).__name__)

    async def shutdown(self) -> None:
        """Cancel music timers without sending notifications or disconnecting manually-owned voice."""
        for state in tuple(self.players.values()):
            async with state.lock:
                self._cancel_idle(state)
                state.queue.clear()
                state.current = None
                if state.owns_voice_connection:
                    voice_client = next(
                        (client for client in self.bot.voice_clients if client.guild.id == self._guild_id(state)),
                        None,
                    )
                    if voice_client and voice_client.is_connected():
                        await voice_client.disconnect(force=True)
        self.players.clear()

    def _guild_id(self, state: GuildPlayer) -> int:
        for guild_id, candidate in self.players.items():
            if candidate is state:
                return guild_id
        raise RuntimeError("Music player state is no longer registered.")


class MusicCog(commands.Cog, name="Music"):
    music = app_commands.Group(name="music", description="Play music in your voice channel.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = BotSettings()
        self.manager = MusicManager(bot, self.settings)

    async def _voice_context(self, interaction: discord.Interaction) -> discord.VoiceChannel | None:
        if interaction.guild is None:
            await interaction.response.send_message("❄️ Musik hanya tersedia di dalam server.", ephemeral=True)
            return None
        state = getattr(interaction.user, "voice", None)
        channel = getattr(state, "channel", None)
        if channel is None:
            await interaction.response.send_message("❄️ Masuklah ke voice channel terlebih dahulu.", ephemeral=True)
            return None
        me = interaction.guild.me
        if me is None:
            await interaction.response.send_message("❄️ Saya belum dapat memeriksa permission voice.", ephemeral=True)
            return None
        permissions = channel.permissions_for(me)
        if not permissions.connect or not permissions.speak:
            await interaction.response.send_message(
                "❄️ Saya membutuhkan permission **Connect** dan **Speak**.", ephemeral=True
            )
            return None
        return channel

    @music.command(name="play", description="Putar satu video YouTube dari URL.")
    @app_commands.describe(url="URL satu video YouTube atau satu track Spotify (resolver Spotify belum tersedia)")
    async def play(self, interaction: discord.Interaction, url: str) -> None:
        channel = await self._voice_context(interaction)
        if channel is None:
            return
        await interaction.response.defer()
        try:
            track = await self.manager.resolve(url)
            started = await self.manager.enqueue(
                interaction.guild,
                channel,
                track,
                interaction.channel,
            )  # type: ignore[arg-type]
        except (MusicInputError, discord.Forbidden, asyncio.TimeoutError, discord.ClientException, OSError) as exc:
            log.warning("Music play failed in guild %s: %s", interaction.guild.id, type(exc).__name__)
            await interaction.followup.send(f"❄️ {exc}")
            return
        embed = discord.Embed(title="❄️ Ditambahkan ke antrean", description=track.title, color=self.settings.COLOR_SUCCESS)
        embed.add_field(name="Status", value="Sedang diputar" if started else "Menunggu antrean")
        await interaction.followup.send(embed=embed)

    @music.command(name="queue", description="Tampilkan antrean musik.")
    async def queue(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("❄️ Musik hanya tersedia di dalam server.", ephemeral=True)
            return
        state = self.manager.players.get(interaction.guild.id)
        lines = [f"**Sedang diputar:** {state.current.title}" if state and state.current else "Tidak ada audio aktif."]
        if state and state.queue:
            lines.append("\n".join(f"{index}. {track.title}" for index, track in enumerate(state.queue, 1)))
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @music.command(name="nowplaying", description="Tampilkan lagu yang sedang diputar.")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        state = self.manager.players.get(interaction.guild.id) if interaction.guild else None
        title = state.current.title if state and state.current else "Tidak ada lagu yang sedang diputar."
        await interaction.response.send_message(f"❄️ **Now playing:** {title}", ephemeral=True)

    @music.command(name="pause", description="Jeda audio.")
    async def pause(self, interaction: discord.Interaction) -> None:
        await self._control(interaction, self.manager.pause, "Audio dijeda.")

    @music.command(name="resume", description="Lanjutkan audio.")
    async def resume(self, interaction: discord.Interaction) -> None:
        await self._control(interaction, self.manager.resume, "Audio dilanjutkan.")

    @music.command(name="skip", description="Lewati lagu saat ini.")
    async def skip(self, interaction: discord.Interaction) -> None:
        await self._control(interaction, self.manager.skip, "Lagu dilewati.")

    @music.command(name="stop", description="Hentikan audio dan kosongkan antrean.")
    async def stop(self, interaction: discord.Interaction) -> None:
        if interaction.guild:
            await self.manager.stop(interaction.guild)
        await interaction.response.send_message("❄️ Audio dihentikan dan antrean dikosongkan.", ephemeral=True)

    @music.command(name="leave", description="Hentikan musik dan tinggalkan voice channel.")
    async def leave(self, interaction: discord.Interaction) -> None:
        if interaction.guild:
            await self.manager.leave(interaction.guild)
        await interaction.response.send_message("❄️ Saya meninggalkan voice channel.", ephemeral=True)

    async def _control(self, interaction: discord.Interaction, action, success: str) -> None:
        changed = bool(interaction.guild and await action(interaction.guild))
        await interaction.response.send_message(
            f"❄️ {success}" if changed else "❄️ Tidak ada audio yang dapat dikontrol.",
            ephemeral=True,
        )

    async def cog_unload(self) -> None:
        for state in self.manager.players.values():
            self.manager._cancel_idle(state)

    async def shutdown(self) -> None:
        await self.manager.shutdown()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
