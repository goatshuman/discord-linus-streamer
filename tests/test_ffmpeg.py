from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from screen_streamer.config import Settings
from screen_streamer.dependencies import DependencyReport
from screen_streamer.ffmpeg import StreamConfigurationError, build_ffmpeg_command


class FfmpegCommandTests(unittest.TestCase):
    def settings(self, directory: Path, **overrides: object) -> Settings:
        defaults: dict[str, object] = {
            "host": "127.0.0.1",
            "port": 8000,
            "public_view_url": "",
            "hls_playback_url": "",
            "capture_backend": "x11",
            "x11_display": ":0",
            "x11_offset": "+0,0",
            "pipewire_source": "0",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "bitrate": "4500k",
            "encoder": "libx264",
            "rtmp_ingest_url": "rtmp://example.invalid/live",
            "stream_key": "test-key",
            "hls_output_dir": directory,
            "reconnect_base_seconds": 2,
            "reconnect_max_seconds": 30,
            "discord_bot_token": "",
            "screen1_discord_user_id": None,
            "screen2_discord_user_id": None,
            "discord_allowed_user_ids": frozenset(),
            "discord_allowed_guild_ids": frozenset(),
        }
        defaults.update(overrides)
        return Settings(**defaults)  # type: ignore[arg-type]

    def test_x11_command_is_video_only_and_writes_rtmp_and_hls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.settings(Path(tmp))
            report = DependencyReport("/usr/bin/ffmpeg", True, True, ())
            command = build_ffmpeg_command(settings, report)
        joined = " ".join(command)
        self.assertIn("x11grab", command)
        self.assertIn("-an", command)
        self.assertIn("rtmp\\://example.invalid/live/test-key", joined)
        self.assertIn("-rw_timeout", command)
        self.assertIn("stream.m3u8", joined)
        self.assertIn("1920x1080", joined)

    def test_pipewire_uses_configured_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.settings(Path(tmp), capture_backend="pipewire", pipewire_source="42")
            report = DependencyReport("/usr/bin/ffmpeg", True, True, ())
            command = build_ffmpeg_command(settings, report)
        self.assertIn("pipewire", command)
        self.assertIn("42", command)

    def test_unconfigured_rtmp_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.settings(Path(tmp), stream_key="")
            report = DependencyReport("/usr/bin/ffmpeg", True, True, ())
            with self.assertRaisesRegex(StreamConfigurationError, "STREAM_KEY"):
                build_ffmpeg_command(settings, report)

    def test_audio_is_not_added_for_either_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for backend in ("x11", "pipewire"):
                settings = self.settings(Path(tmp), capture_backend=backend)
                report = DependencyReport("/usr/bin/ffmpeg", True, True, ())
                command = build_ffmpeg_command(settings, report)
                self.assertIn("-an", command)
                self.assertEqual(command.count("-i"), 1)
                self.assertIn("0:v:0", command)
                self.assertNotIn("0:a", " ".join(command))


if __name__ == "__main__":
    unittest.main()
