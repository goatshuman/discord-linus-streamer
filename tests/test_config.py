from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from screen_streamer.config import ConfigurationError, Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_select_x11_without_session_type(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env(load_file=False)
        self.assertEqual(settings.capture_backend, "x11")
        self.assertEqual((settings.width, settings.height, settings.fps), (1920, 1080, 30))
        self.assertFalse(settings.discord_bot_token)
        self.assertIsNone(settings.screen1_discord_user_id)
        self.assertIsNone(settings.screen2_discord_user_id)

    def test_auto_selects_pipewire_for_wayland(self) -> None:
        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland"}, clear=True):
            settings = Settings.from_env(load_file=False)
        self.assertEqual(settings.capture_backend, "pipewire")

    def test_auto_detects_wayland_display_variable(self) -> None:
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=True):
            settings = Settings.from_env(load_file=False)
        self.assertEqual(settings.capture_backend, "pipewire")

    def test_bad_bitrate_is_rejected(self) -> None:
        with patch.dict(os.environ, {"VIDEO_BITRATE": "fast"}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "VIDEO_BITRATE"):
                Settings.from_env(load_file=False)

    def test_screen_participants_load_as_distinct_discord_ids(self) -> None:
        env = {
            "SCREEN1_DISCORD_USER_ID": "123456789",
            "SCREEN2_DISCORD_USER_ID": "987654321",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env(load_file=False)
        self.assertEqual(settings.screen1_discord_user_id, 123456789)
        self.assertEqual(settings.screen2_discord_user_id, 987654321)

    def test_screen_participant_ids_must_be_different(self) -> None:
        env = {
            "SCREEN1_DISCORD_USER_ID": "123456789",
            "SCREEN2_DISCORD_USER_ID": "123456789",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "must identify different users"):
                Settings.from_env(load_file=False)

    def test_bot_token_requires_screen1_or_admin_id(self) -> None:
        with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "not-a-real-token"}, clear=True):
            settings = Settings.from_env(load_file=False)
        with self.assertRaisesRegex(ConfigurationError, "SCREEN1_DISCORD_USER_ID"):
            settings.validate_discord()

    def test_legacy_admin_allowlist_remains_supported(self) -> None:
        env = {
            "DISCORD_BOT_TOKEN": "not-a-real-token",
            "DISCORD_ALLOWED_USER_IDS": "123456789",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env(load_file=False)
        settings.validate_discord()


if __name__ == "__main__":
    unittest.main()
