from __future__ import annotations

from pathlib import Path

from .config import Settings
from .dependencies import DependencyReport


class StreamConfigurationError(ValueError):
    """Raised when the output stream is not fully configured."""


def _tee_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("|", "\\|")


def clear_hls_output(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.iterdir():
        if path.is_file() and (
            path.name == "stream.m3u8"
            or (path.name.startswith("segment_") and path.suffix == ".ts")
        ):
            path.unlink(missing_ok=True)


def build_ffmpeg_command(settings: Settings, report: DependencyReport) -> list[str]:
    if report.issues:
        raise StreamConfigurationError("\n".join(report.issues))
    if not settings.rtmp_output_url:
        raise StreamConfigurationError(
            "Set both RTMP_INGEST_URL and STREAM_KEY before starting the stream."
        )
    if "|" in settings.rtmp_output_url or "\n" in settings.rtmp_output_url:
        raise StreamConfigurationError("The RTMP output URL contains a character not supported by FFmpeg tee.")

    clear_hls_output(settings.hls_output_dir)
    playlist = (settings.hls_output_dir / "stream.m3u8").resolve()
    segment_pattern = (settings.hls_output_dir / "segment_%06d.ts").resolve()
    rtmp_url = _tee_escape(settings.rtmp_output_url)
    segment_pattern_escaped = _tee_escape(str(segment_pattern))
    playlist_escaped = _tee_escape(str(playlist))

    args = [
        report.ffmpeg_path or "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "warning",
        "-stats_period",
        "1",
        "-thread_queue_size",
        "512",
    ]

    if settings.capture_backend == "x11":
        args.extend(
            [
                "-f",
                "x11grab",
                "-draw_mouse",
                "1",
                "-framerate",
                str(settings.fps),
                "-video_size",
                f"{settings.width}x{settings.height}",
                "-i",
                f"{settings.x11_display}{settings.x11_offset}",
            ]
        )
    else:
        args.extend(
            [
                "-f",
                "pipewire",
                "-framerate",
                str(settings.fps),
                "-i",
                settings.pipewire_source,
            ]
        )

    bitrate_value = settings.bitrate
    args.extend(
        [
            # Prevent a stalled RTMP write from keeping FFmpeg alive forever;
            # the supervisor can then restart it and re-establish the stream.
            "-rw_timeout",
            "15000000",
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            (
                f"scale={settings.width}:{settings.height}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={settings.width}:{settings.height}:(ow-iw)/2:(oh-ih)/2"
            ),
            "-c:v",
            settings.encoder,
            "-pix_fmt",
            "yuv420p",
            "-b:v",
            bitrate_value,
            "-maxrate",
            bitrate_value,
            "-bufsize",
            bitrate_value,
            "-g",
            str(settings.fps * 2),
            "-keyint_min",
            str(settings.fps * 2),
            "-sc_threshold",
            "0",
            "-progress",
            "pipe:1",
            "-f",
            "tee",
            (
                f"[f=flv:onfail=abort]{rtmp_url}|"
                "[f=hls:hls_time=2:hls_list_size=6:"
                "hls_flags=delete_segments+independent_segments:"
                f"hls_segment_filename={segment_pattern_escaped}]"
                f"{playlist_escaped}"
            ),
        ]
    )
    return args
