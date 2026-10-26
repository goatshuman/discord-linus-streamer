from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when the environment contains an invalid setting."""


def _positive_int(name: str, default: int, *, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        result = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a whole number; got {raw!r}.") from exc
    if result <= 0 or (maximum is not None and result > maximum):
        limit = f" and no greater than {maximum}" if maximum else ""
        raise ConfigurationError(f"{name} must be greater than zero{limit}.")
    return result


def _id_set(name: str) -> frozenset[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return frozenset()
    values: set[int] = set()
    for item in raw.split(","):
        try:
            value = int(item.strip())
        except ValueError as exc:
            raise ConfigurationError(f"{name} must be a comma-separated list of numeric IDs.") from exc
        if value <= 0:
            raise ConfigurationError(f"{name} must contain positive numeric IDs.")
        values.add(value)
    return frozenset(values)


def _optional_id(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a numeric Discord user ID.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive numeric Discord user ID.")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    host: str
    port: int
    public_view_url: str
    hls_playback_url: str
    capture_backend: str
    x11_display: str
    x11_offset: str
    pipewire_source: str
    width: int
    height: int
    fps: int
    bitrate: str
    encoder: str
    rtmp_ingest_url: str
    stream_key: str
    hls_output_dir: Path
    reconnect_base_seconds: int
    reconnect_max_seconds: int
    discord_bot_token: str
    screen1_discord_user_id: int | None
    screen2_discord_user_id: int | None
    discord_allowed_user_ids: frozenset[int]
    discord_allowed_guild_ids: frozenset[int]

    @classmethod
    def from_env(cls, *, load_file: bool = True) -> "Settings":
        if load_file:
            load_dotenv(override=False)

        backend = os.getenv("CAPTURE_BACKEND", "auto").strip().lower()
        if backend == "auto":
            is_wayland = (
                os.getenv("XDG_SESSION_TYPE", "").lower() == "wayland"
                or bool(os.getenv("WAYLAND_DISPLAY", "").strip())
            )
            backend = "pipewire" if is_wayland else "x11"
        if backend not in {"x11", "pipewire"}:
            raise ConfigurationError("CAPTURE_BACKEND must be auto, x11, or pipewire.")

        bitrate = os.getenv("VIDEO_BITRATE", "4500k").strip()
        if not re.fullmatch(r"[1-9]\d*(?:k|M)?", bitrate, re.IGNORECASE):
            raise ConfigurationError("VIDEO_BITRATE must look like 4500k or 5M.")

        encoder = os.getenv("VIDEO_ENCODER", "libx264").strip()
        if not re.fullmatch(r"[A-Za-z0-9_]+", encoder):
            raise ConfigurationError("VIDEO_ENCODER must be an FFmpeg encoder name.")

        offset = os.getenv("X11_OFFSET", "+0,0").strip()
        if not re.fullmatch(r"[+-]\d+,[+-]?\d+", offset):
            raise ConfigurationError("X11_OFFSET must look like +0,0.")

        base_url = os.getenv("RTMP_INGEST_URL", "").strip().rstrip("/")
        if base_url and not base_url.startswith(("rtmp://", "rtmps://")):
            raise ConfigurationError("RTMP_INGEST_URL must start with rtmp:// or rtmps://.")

        stream_key = os.getenv("STREAM_KEY", "").strip()
        if any(character in stream_key for character in ("\n", "\r")):
            raise ConfigurationError("STREAM_KEY cannot contain newline characters.")

        reconnect_base = _positive_int("RECONNECT_BASE_SECONDS", 2, maximum=300)
        reconnect_max = _positive_int("RECONNECT_MAX_SECONDS", 30, maximum=3600)
        if reconnect_max < reconnect_base:
            raise ConfigurationError("RECONNECT_MAX_SECONDS must be at least RECONNECT_BASE_SECONDS.")

        screen1_discord_user_id = _optional_id("SCREEN1_DISCORD_USER_ID")
        screen2_discord_user_id = _optional_id("SCREEN2_DISCORD_USER_ID")
        if (
            screen1_discord_user_id is not None
            and screen1_discord_user_id == screen2_discord_user_id
        ):
            raise ConfigurationError(
                "SCREEN1_DISCORD_USER_ID and SCREEN2_DISCORD_USER_ID must identify different users."
            )

        return cls(
            host=os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=_positive_int("APP_PORT", 8000, maximum=65535),
            public_view_url=os.getenv("PUBLIC_VIEW_URL", "").strip(),
            hls_playback_url=os.getenv("HLS_PLAYBACK_URL", "").strip(),
            capture_backend=backend,
            x11_display=os.getenv("X11_DISPLAY", "").strip() or os.getenv("DISPLAY", "").strip(),
            x11_offset=offset,
            pipewire_source=os.getenv("PIPEWIRE_SOURCE", "0").strip(),
            width=_positive_int("VIDEO_WIDTH", 1920, maximum=7680),
            height=_positive_int("VIDEO_HEIGHT", 1080, maximum=4320),
            fps=_positive_int("VIDEO_FPS", 30, maximum=120),
            bitrate=bitrate,
            encoder=encoder,
            rtmp_ingest_url=base_url,
            stream_key=stream_key,
            hls_output_dir=Path(os.getenv("HLS_OUTPUT_DIR", "./var/hls")).expanduser(),
            reconnect_base_seconds=reconnect_base,
            reconnect_max_seconds=reconnect_max,
            discord_bot_token=os.getenv("DISCORD_BOT_TOKEN", "").strip(),
            screen1_discord_user_id=screen1_discord_user_id,
            screen2_discord_user_id=screen2_discord_user_id,
            discord_allowed_user_ids=_id_set("DISCORD_ALLOWED_USER_IDS"),
            discord_allowed_guild_ids=_id_set("DISCORD_ALLOWED_GUILD_IDS"),
        )

    def validate_discord(self) -> None:
        if (
            self.discord_bot_token
            and self.screen1_discord_user_id is None
            and not self.discord_allowed_user_ids
        ):
            raise ConfigurationError(
                "Discord control is enabled but SCREEN1_DISCORD_USER_ID and "
                "DISCORD_ALLOWED_USER_IDS are empty. Set the screen1 account ID "
                "or configure an additional bot admin."
            )

    @property
    def effective_hls_url(self) -> str:
        return self.hls_playback_url or "/hls/stream.m3u8"

    @property
    def rtmp_output_url(self) -> str:
        if not self.rtmp_ingest_url or not self.stream_key:
            return ""
        return f"{self.rtmp_ingest_url}/{self.stream_key}"
