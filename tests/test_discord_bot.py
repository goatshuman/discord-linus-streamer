from __future__ import annotations

import unittest
from pathlib import Path

from screen_streamer.config import Settings
from screen_streamer.controller import StreamController
from screen_streamer.discord_bot import create_bot, is_authorized


class DiscordBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_expected_slash_commands_are_registered(self) -> None:
        settings = Settings(
            host="127.0.0.1",
            port=8000,
            public_view_url="https://stream.example.invalid/",
            hls_playback_url="",
            capture_backend="x11",
            x11_display=":0",
            x11_offset="+0,0",
            pipewire_source="0",
            width=1920,
            height=1080,
            fps=30,
            bitrate="4500k",
            encoder="libx264",
            rtmp_ingest_url="rtmp://ingest.example.invalid/live",
            stream_key="test-key",
            hls_output_dir=Path("/tmp/streamer-test-hls"),
            reconnect_base_seconds=2,
            reconnect_max_seconds=30,
            discord_bot_token="test-token",
            screen1_discord_user_id=123456789,
            screen2_discord_user_id=987654321,
            discord_allowed_user_ids=frozenset({555555555}),
            discord_allowed_guild_ids=frozenset(),
        )
        bot = create_bot(settings, StreamController(settings))
        try:
            self.assertEqual(
                {command.name for command in bot.tree.get_commands()},
                {"start", "stop", "status", "share"},
            )
            self.assertEqual(bot.intents.value, 0)
        finally:
            await bot.close()

    def test_screen1_can_control_and_share(self) -> None:
        settings = self._settings()
        for command in ("start", "stop", "status", "share"):
            with self.subTest(command=command):
                self.assertTrue(
                    is_authorized(
                        settings,
                        user_id=123456789,
                        guild_id=10,
                        command_name=command,
                    )
                )

    def test_screen2_can_view_and_share_but_cannot_control(self) -> None:
        settings = self._settings()
        for command in ("status", "share"):
            with self.subTest(command=command):
                self.assertTrue(
                    is_authorized(
                        settings,
                        user_id=987654321,
                        guild_id=10,
                        command_name=command,
                    )
                )
        for command in ("start", "stop"):
            with self.subTest(command=command):
                self.assertFalse(
                    is_authorized(
                        settings,
                        user_id=987654321,
                        guild_id=10,
                        command_name=command,
                    )
                )

    def test_legacy_admin_has_full_command_access(self) -> None:
        settings = self._settings()
        self.assertTrue(
            is_authorized(
                settings,
                user_id=555555555,
                guild_id=10,
                command_name="start",
            )
        )

    def test_guild_allowlist_applies_to_participants_and_admins(self) -> None:
        settings = self._settings(discord_allowed_guild_ids=frozenset({20}))
        self.assertFalse(
            is_authorized(
                settings,
                user_id=123456789,
                guild_id=10,
                command_name="start",
            )
        )
        self.assertTrue(
            is_authorized(
                settings,
                user_id=123456789,
                guild_id=20,
                command_name="start",
            )
        )

    @staticmethod
    def _settings(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "host": "127.0.0.1",
            "port": 8000,
            "public_view_url": "https://stream.example.invalid/",
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
            "rtmp_ingest_url": "rtmp://ingest.example.invalid/live",
            "stream_key": "test-key",
            "hls_output_dir": Path("/tmp/streamer-test-hls"),
            "reconnect_base_seconds": 2,
            "reconnect_max_seconds": 30,
            "discord_bot_token": "test-token",
            "screen1_discord_user_id": 123456789,
            "screen2_discord_user_id": 987654321,
            "discord_allowed_user_ids": frozenset({555555555}),
            "discord_allowed_guild_ids": frozenset(),
        }
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
