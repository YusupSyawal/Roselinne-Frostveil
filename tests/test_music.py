import asyncio
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from commands.music import (
    _FFmpegDiagnosticSink,
    GuildPlayer,
    MusicInputError,
    MusicManager,
    Track,
    validate_media_url,
)


class MusicValidationTests(unittest.TestCase):
    def test_accepts_single_youtube_video(self):
        self.assertEqual(validate_media_url("https://youtu.be/video-id"), "https://youtu.be/video-id")

    def test_rejects_non_http_and_playlist(self):
        with self.assertRaises(MusicInputError):
            validate_media_url("file:///tmp/audio.mp3")
        with self.assertRaises(MusicInputError):
            validate_media_url("https://www.youtube.com/watch?v=abc&list=playlist")

    def test_rejects_private_destinations(self):
        for url in ("http://127.0.0.1/video", "https://192.168.1.20/video", "https://localhost/video"):
            with self.assertRaises(MusicInputError):
                validate_media_url(url)

    def test_rejects_unsupported_spotify_resource(self):
        with self.assertRaises(MusicInputError):
            validate_media_url("https://open.spotify.com/playlist/example")


class MusicManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.settings = SimpleNamespace(
            ffmpeg_path="ffmpeg",
            music_opus_bitrate=160,
            music_opus_fec=True,
            music_expected_packet_loss=0.15,
        )
        self.manager = MusicManager(self.bot, self.settings)
        self.guild = MagicMock()
        self.guild.id = 42
        self.guild.voice_client = MagicMock()
        self.voice_client = self.guild.voice_client
        self.voice_client.is_connected.return_value = True
        self.voice_client.is_playing.return_value = True
        self.voice_client.is_paused.return_value = False
        self.voice_client.channel = SimpleNamespace(id=1, bitrate=128)
        self.voice_client.disconnect = AsyncMock()
        self.voice_client.guild = self.guild
        self.bot.voice_clients = [self.voice_client]
        self.text_channel = MagicMock()
        self.text_channel.send = AsyncMock()

    async def test_queue_isolated_per_guild(self):
        first = self.manager.player_for(1)
        second = self.manager.player_for(2)
        first.queue.append(Track("one", "https://youtu.be/1", "stream"))
        self.assertEqual(len(first.queue), 1)
        self.assertEqual(len(second.queue), 0)

    async def test_pause_resume_skip_controls(self):
        state = self.manager.player_for(self.guild.id)
        state.current = Track("current", "https://youtu.be/current", "stream")
        self.voice_client.is_playing.return_value = True
        self.assertTrue(await self.manager.pause(self.guild))
        self.voice_client.pause.assert_called_once_with()
        self.voice_client.is_playing.return_value = False
        self.voice_client.is_paused.return_value = True
        self.assertTrue(await self.manager.resume(self.guild))
        self.voice_client.resume.assert_called_once_with()
        self.voice_client.is_playing.return_value = True
        self.voice_client.is_paused.return_value = False
        self.assertTrue(await self.manager.skip(self.guild))
        self.voice_client.stop.assert_called_once_with()

    async def test_stop_clears_queue(self):
        state = self.manager.player_for(self.guild.id)
        state.queue.append(Track("one", "https://youtu.be/1", "stream"))
        await self.manager.stop(self.guild)
        self.assertEqual(len(state.queue), 0)
        self.voice_client.stop.assert_called_once_with()

    async def test_playback_uses_natural_opus_settings_and_channel_cap(self):
        state = self.manager.player_for(self.guild.id)
        state.queue.append(Track("one", "https://youtu.be/1", "stream"))
        self.voice_client.is_playing.return_value = False
        self.voice_client.is_paused.return_value = False
        with patch("commands.music.discord.FFmpegPCMAudio") as ffmpeg_source:
            await self.manager.play_next(self.guild)
        ffmpeg_source.assert_called_once_with(
            "stream",
            executable="ffmpeg",
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn",
            stderr=unittest.mock.ANY,
        )
        play_kwargs = self.voice_client.play.call_args.kwargs
        self.assertEqual(play_kwargs["bitrate"], 128)
        self.assertEqual(play_kwargs["application"], "audio")
        self.assertEqual(play_kwargs["bandwidth"], "full")
        self.assertEqual(play_kwargs["signal_type"], "music")
        self.assertTrue(play_kwargs["fec"])
        self.assertEqual(play_kwargs["expected_packet_loss"], 0.15)

    def test_ffmpeg_diagnostic_sink_is_bounded_and_safe(self):
        sink = _FFmpegDiagnosticSink(limit=8)
        sink.write(b"secret-signed-url?token=never-log")
        self.assertLessEqual(len(sink.snapshot().encode()), 8)

    async def test_playback_after_error_logs_ffmpeg_diagnostics(self):
        state = self.manager.player_for(self.guild.id)
        state.current = Track("one", "https://youtu.be/1", "stream")
        state.playback_token = 1
        sink = _FFmpegDiagnosticSink()
        sink.write(b"Invalid data found when processing input")
        with patch("commands.music.log.warning") as warning:
            await self.manager._playback_finished(
                self.guild,
                1,
                RuntimeError("decoder failed"),
                state,
                sink,
            )
        warning.assert_called_once()
        self.assertIn("Invalid data found", warning.call_args.args[-1])

    def test_diagnostic_text_redacts_urls(self):
        from commands.music import _safe_diagnostic_text

        result = _safe_diagnostic_text("https://example.test/audio?sig=secret")
        self.assertNotIn("sig=secret", result)
        self.assertIn("<redacted-url>", result)

    async def test_spotify_reports_missing_legitimate_resolver(self):
        with patch("commands.music.validate_public_media_url", new=AsyncMock(
            return_value="https://open.spotify.com/track/example"
        )):
            with self.assertRaisesRegex(MusicInputError, "resolver Spotify"):
                await self.manager.resolve("https://open.spotify.com/track/example")

    async def test_playback_callback_advances_queue(self):
        state = GuildPlayer(deque())
        state.current = Track("current", "https://youtu.be/1", "stream")
        state.queue.append(Track("next", "https://youtu.be/2", "stream"))
        state.playback_token = 1
        self.manager.players[self.guild.id] = state
        self.voice_client.is_playing.return_value = False
        self.voice_client.is_paused.return_value = False
        with patch.object(self.manager, "_play_next_locked", new=AsyncMock()) as play_next:
            await self.manager._playback_finished(self.guild, 1, None)
        play_next.assert_awaited_once_with(self.guild, state)
        self.assertIsNone(state.current)

    async def test_audio_after_callback_advances_queue_on_event_loop(self):
        state = self.manager.player_for(self.guild.id)
        state.queue.extend((
            Track("one", "https://youtu.be/1", "stream-1"),
            Track("two", "https://youtu.be/2", "stream-2"),
        ))
        self.voice_client.is_playing.return_value = False
        self.voice_client.is_paused.return_value = False
        with patch("commands.music.discord.FFmpegPCMAudio"):
            await self.manager.play_next(self.guild)
            first_after = self.voice_client.play.call_args.kwargs["after"]
            first_after(None)
            await asyncio.sleep(0.05)
        self.assertEqual(self.voice_client.play.call_count, 2)
        self.assertEqual(state.current.title, "two")

    async def test_skip_stops_once_and_callback_starts_next_track(self):
        state = self.manager.player_for(self.guild.id)
        state.queue.extend((
            Track("one", "https://youtu.be/1", "stream-1"),
            Track("two", "https://youtu.be/2", "stream-2"),
        ))
        self.voice_client.is_playing.return_value = False
        self.voice_client.is_paused.return_value = False
        with patch("commands.music.discord.FFmpegPCMAudio"):
            await self.manager.play_next(self.guild)
            first_after = self.voice_client.play.call_args.kwargs["after"]
            self.voice_client.is_playing.return_value = True
            self.voice_client.stop.side_effect = lambda: self.voice_client.is_playing.configure_mock(return_value=False)
            self.assertTrue(await self.manager.skip(self.guild))
            first_after(None)
            await asyncio.sleep(0.05)
        self.voice_client.stop.assert_called_once_with()
        self.assertEqual(self.voice_client.play.call_count, 2)
        self.assertEqual(state.current.title, "two")

    async def test_skip_advances_when_stop_callback_is_delayed(self):
        state = self.manager.player_for(self.guild.id)
        state.queue.extend((
            Track("one", "https://youtu.be/1", "stream-1"),
            Track("two", "https://youtu.be/2", "stream-2"),
        ))
        self.voice_client.is_playing.return_value = False
        self.voice_client.is_paused.return_value = False
        with patch("commands.music.discord.FFmpegPCMAudio"):
            await self.manager.play_next(self.guild)
            self.voice_client.is_playing.return_value = True
            self.voice_client.stop.side_effect = lambda: self.voice_client.is_playing.configure_mock(return_value=False)
            self.assertTrue(await self.manager.skip(self.guild))
        self.voice_client.stop.assert_called_once_with()
        self.assertEqual(self.voice_client.play.call_count, 2)
        self.assertEqual(state.current.title, "two")

    async def test_duplicate_playback_callback_advances_only_once(self):
        state = self.manager.player_for(self.guild.id)
        state.queue.extend((
            Track("one", "https://youtu.be/1", "stream-1"),
            Track("two", "https://youtu.be/2", "stream-2"),
            Track("three", "https://youtu.be/3", "stream-3"),
        ))
        self.voice_client.is_playing.return_value = False
        self.voice_client.is_paused.return_value = False
        with patch("commands.music.discord.FFmpegPCMAudio"):
            await self.manager.play_next(self.guild)
            first_after = self.voice_client.play.call_args.kwargs["after"]
            first_after(None)
            await asyncio.sleep(0.05)
            first_after(None)
            await asyncio.sleep(0.05)
        self.assertEqual(self.voice_client.play.call_count, 2)
        self.assertEqual(state.current.title, "two")
        self.assertEqual(list(state.queue)[0].title, "three")

    async def test_skip_without_active_track_does_not_change_queue(self):
        state = self.manager.player_for(self.guild.id)
        queued = Track("queued", "https://youtu.be/queued", "stream")
        state.queue.append(queued)
        self.voice_client.is_playing.return_value = False
        self.assertFalse(await self.manager.skip(self.guild))
        self.voice_client.stop.assert_not_called()
        self.assertEqual(list(state.queue), [queued])

    async def test_reconnect_invalidates_old_callback_and_uses_new_voice_client(self):
        state = self.manager.player_for(self.guild.id)
        state.current = Track("old", "https://youtu.be/old", "stream-old")
        state.playback_token = 4
        old_client = self.voice_client
        old_client.is_connected.return_value = False
        new_client = MagicMock()
        new_client.is_connected.return_value = True
        new_client.is_playing.return_value = False
        new_client.is_paused.return_value = False
        new_client.channel = SimpleNamespace(id=7, bitrate=128)
        new_client.play = MagicMock()
        channel = MagicMock()
        channel.id = 7
        async def connect_new_client(**_kwargs):
            self.guild.voice_client = new_client
            return new_client

        channel.connect = AsyncMock(side_effect=connect_new_client)
        self.guild.voice_client = old_client
        with patch("commands.music.discord.FFmpegPCMAudio"):
            await self.manager.enqueue(
                self.guild,
                channel,
                Track("new", "https://youtu.be/new", "stream-new"),
                self.text_channel,
            )
            await self.manager._playback_finished(self.guild, 4, None, state)
        self.assertIs(self.guild.voice_client, new_client)
        new_client.play.assert_called_once()
        self.assertEqual(state.current.title, "new")

    async def test_leave_disconnects_and_removes_player(self):
        state = self.manager.player_for(self.guild.id)
        state.owns_voice_connection = True
        self.voice_client.is_playing.return_value = False
        await self.manager.leave(self.guild)
        self.voice_client.disconnect.assert_awaited_once_with()
        self.assertNotIn(self.guild.id, self.manager.players)

    async def test_idle_disconnects_owned_connection_and_notifies_once(self):
        state = self.manager.player_for(self.guild.id)
        state.owns_voice_connection = True
        state.last_text_channel = self.text_channel
        self.voice_client.is_playing.return_value = False
        self.voice_client.is_paused.return_value = False
        state.idle_task = asyncio.current_task()
        with patch("commands.music.asyncio.sleep", new=AsyncMock()):
            state.idle_task = asyncio.create_task(self.manager._idle_disconnect(self.guild, state))
            await state.idle_task
        self.voice_client.disconnect.assert_awaited_once_with()
        self.text_channel.send.assert_awaited_once_with(
            "❄️ Saya keluar dari voice channel karena tidak ada musik selama 5 menit."
        )
        self.assertNotIn(self.guild.id, self.manager.players)

    async def test_idle_timer_is_cancelled_when_track_is_enqueued(self):
        state = self.manager.player_for(self.guild.id)
        state.owns_voice_connection = True
        state.idle_task = asyncio.create_task(asyncio.sleep(60))
        track = Track("new", "https://youtu.be/new", "stream")
        self.voice_client.is_playing.return_value = True
        self.voice_client.move_to = AsyncMock()
        channel = MagicMock()
        channel.id = 1
        await self.manager.enqueue(self.guild, channel, track, self.text_channel)
        self.assertTrue(state.idle_task is None or state.idle_task.cancelled())
        self.assertEqual(list(state.queue), [track])

    async def test_manual_voice_connection_is_not_auto_left(self):
        state = self.manager.player_for(self.guild.id)
        state.owns_voice_connection = False
        state.current = None
        state.idle_task = asyncio.create_task(self.manager._idle_disconnect(self.guild, state))
        with patch("commands.music.asyncio.sleep", new=AsyncMock()):
            await state.idle_task
        self.voice_client.disconnect.assert_not_awaited()
        self.assertIn(self.guild.id, self.manager.players)

    async def test_stale_idle_timer_cannot_disconnect_new_generation(self):
        state = self.manager.player_for(self.guild.id)
        state.owns_voice_connection = True
        state.idle_task = asyncio.current_task()
        with patch("commands.music.asyncio.sleep", new=AsyncMock()):
            await self.manager._idle_disconnect(self.guild, state, state.idle_generation - 1)
        self.voice_client.disconnect.assert_not_awaited()
        self.assertIn(self.guild.id, self.manager.players)

    async def test_idle_notification_failure_is_safe_and_once_only(self):
        state = self.manager.player_for(self.guild.id)
        state.owns_voice_connection = True
        state.last_text_channel = self.text_channel
        self.voice_client.is_playing.return_value = False
        self.voice_client.is_paused.return_value = False
        self.text_channel.send.side_effect = discord.Forbidden(MagicMock(), "denied")
        with patch("commands.music.asyncio.sleep", new=AsyncMock()):
            state.idle_task = asyncio.create_task(self.manager._idle_disconnect(self.guild, state))
            await state.idle_task
        self.text_channel.send.assert_awaited_once()
        self.assertTrue(state.idle_notification_sent)

    async def test_shutdown_cancels_timer_and_disconnects_owned_only(self):
        state = self.manager.player_for(self.guild.id)
        state.owns_voice_connection = True
        idle_task = asyncio.create_task(asyncio.sleep(60))
        state.idle_task = idle_task
        await self.manager.shutdown()
        await asyncio.sleep(0)
        self.assertTrue(idle_task.cancelled())
        self.voice_client.disconnect.assert_awaited_once_with(force=True)
        self.assertEqual(self.manager.players, {})

    async def test_stale_playback_callback_does_not_recreate_state_after_leave(self):
        state = self.manager.player_for(self.guild.id)
        state.playback_token = 3
        self.manager.players.pop(self.guild.id)
        await self.manager._playback_finished(self.guild, 3, None, state)
        self.assertNotIn(self.guild.id, self.manager.players)


if __name__ == "__main__":
    unittest.main()
