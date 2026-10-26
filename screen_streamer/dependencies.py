from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True, slots=True)
class DependencyReport:
    ffmpeg_path: str | None
    encoder_available: bool
    capture_available: bool
    issues: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.issues


def _ffmpeg_listing(ffmpeg: str, argument: str) -> str:
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", argument],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return f"{result.stdout}\n{result.stderr}"


def inspect_dependencies(settings: Settings) -> DependencyReport:
    issues: list[str] = []
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return DependencyReport(
            ffmpeg_path=None,
            encoder_available=False,
            capture_available=False,
            issues=(
                "FFmpeg was not found on PATH. Install it, then restart this application. "
                "Ubuntu/Debian: sudo apt install ffmpeg; Fedora: sudo dnf install ffmpeg; "
                "Arch: sudo pacman -S ffmpeg; NixOS: add pkgs.ffmpeg to your system packages.",
            ),
        )

    encoders = _ffmpeg_listing(ffmpeg, "-encoders")
    matching_encoder = next(
        (
            line.split(maxsplit=2)
            for line in encoders.splitlines()
            if len(line.split(maxsplit=2)) == 3
            and line.split(maxsplit=2)[1] == settings.encoder
            and "V" in line.split(maxsplit=2)[0]
        ),
        None,
    )
    encoder_description = matching_encoder[2].casefold() if matching_encoder else ""
    encoder_available = any(
        marker in encoder_description for marker in ("h.264", "h264", "avc")
    )
    if not encoder_available:
        issues.append(
            f"FFmpeg does not list {settings.encoder!r} as an H.264 video encoder. "
            "Check `ffmpeg -encoders` or choose an installed H.264 encoder in VIDEO_ENCODER."
        )

    formats = _ffmpeg_listing(ffmpeg, "-demuxers")
    if settings.capture_backend == "x11":
        capture_available = "x11grab" in formats
        if not capture_available:
            issues.append(
                "This FFmpeg build has no x11grab input. Install an FFmpeg build with X11 capture support."
            )
        if not settings.x11_display:
            issues.append(
                "DISPLAY is not set. Run the app from the logged-in X11 desktop session or set X11_DISPLAY."
            )
    else:
        capture_available = "pipewire" in formats
        if not capture_available:
            issues.append(
                "This FFmpeg build has no PipeWire input. Install an FFmpeg build with PipeWire support "
                "and ensure PipeWire plus the desktop screen-capture portal are running."
            )
        if not settings.pipewire_source:
            issues.append("PIPEWIRE_SOURCE is empty. Set it to the PipeWire screen-capture source ID.")

    return DependencyReport(
        ffmpeg_path=ffmpeg,
        encoder_available=encoder_available,
        capture_available=capture_available,
        issues=tuple(issues),
    )
