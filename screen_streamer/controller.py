from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .dependencies import DependencyReport, inspect_dependencies
from .ffmpeg import StreamConfigurationError, build_ffmpeg_command, clear_hls_output

logger = logging.getLogger(__name__)

_ERROR_MARKERS = (
    "error",
    "failed",
    "failure",
    "unable",
    "refused",
    "denied",
    "invalid",
    "not found",
    "timed out",
)


class StreamController:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = "stopped"
        self.last_error: str | None = None
        self.reconnect_count = 0
        self.started_at: str | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._stop_requested = False
        self._last_progress_at: str | None = None
        self._dependency_cache: DependencyReport | None = None
        self._dependency_cache_time = 0.0

    def dependency_report(self, *, refresh: bool = False) -> DependencyReport:
        now = time.monotonic()
        if (
            not refresh
            and self._dependency_cache is not None
            and now - self._dependency_cache_time < 30
        ):
            return self._dependency_cache
        self._dependency_cache = inspect_dependencies(self.settings)
        self._dependency_cache_time = now
        return self._dependency_cache

    async def start(self) -> tuple[bool, str]:
        async with self._lock:
            if self._task and not self._task.done():
                return False, "The stream is already starting or running."

            report = self.dependency_report(refresh=True)
            if report.issues:
                self.last_error = "\n".join(report.issues)
                self.state = "error"
                return False, self.last_error

            if not self.settings.rtmp_output_url:
                self.last_error = "Set RTMP_INGEST_URL and STREAM_KEY before starting."
                self.state = "error"
                return False, self.last_error

            try:
                build_ffmpeg_command(self.settings, report)
            except (OSError, StreamConfigurationError) as exc:
                self.last_error = str(exc)
                self.state = "error"
                return False, self.last_error

            self._stop_requested = False
            self.last_error = None
            self.reconnect_count = 0
            self.started_at = datetime.now(timezone.utc).isoformat()
            self.state = "connecting"
            self._task = asyncio.create_task(self._run_loop(), name="ffmpeg-stream-supervisor")
            logger.info(
                "Stream start requested: backend=%s, output=%sx%s@%s, encoder=%s",
                self.settings.capture_backend,
                self.settings.width,
                self.settings.height,
                self.settings.fps,
                self.settings.encoder,
            )
            return True, "Capture starting. Use /stop to end the live stream."

    async def stop(self) -> tuple[bool, str]:
        async with self._lock:
            task = self._task
            if not task or task.done():
                self.state = "stopped"
                clear_hls_output(self.settings.hls_output_dir)
                return False, "The stream is already stopped."
            self._stop_requested = True
            self.state = "stopping"
            process = self._process
            if process and process.returncode is None:
                process.terminate()

        try:
            await asyncio.wait_for(task, timeout=8)
        except asyncio.TimeoutError:
            process = self._process
            if process and process.returncode is None:
                process.kill()
            await task

        self.state = "stopped"
        self.started_at = None
        clear_hls_output(self.settings.hls_output_dir)
        logger.info("Stream stopped by an authorized control request.")
        return True, "The live stream has stopped."

    def status(self) -> dict[str, Any]:
        report = self.dependency_report()
        return {
            "state": self.state,
            "captureBackend": self.settings.capture_backend,
            "resolution": f"{self.settings.width}x{self.settings.height}",
            "fps": self.settings.fps,
            "bitrate": self.settings.bitrate,
            "encoder": self.settings.encoder,
            "startedAt": self.started_at,
            "lastProgressAt": self._last_progress_at,
            "reconnectCount": self.reconnect_count,
            "lastError": self._redact(self.last_error) if self.last_error else None,
            "dependenciesReady": report.ready,
            "dependencyIssues": list(report.issues),
            "hlsPlaybackUrl": self.settings.effective_hls_url,
            "audioEnabled": False,
        }

    def _redact(self, text: str | None) -> str | None:
        if not text:
            return text
        for secret in (self.settings.stream_key, self.settings.discord_bot_token):
            if secret:
                text = text.replace(secret, "[redacted]")
        if self.settings.rtmp_output_url:
            text = text.replace(self.settings.rtmp_output_url, "[redacted RTMP output]")
        text = re.sub(r"(rtmps?://)[^\s]+", r"\1[redacted]", text)
        return text

    async def _read_progress(self, stream: asyncio.StreamReader) -> None:
        while line := await stream.readline():
            text = line.decode("utf-8", errors="replace").strip()
            if text.startswith("frame="):
                self._last_progress_at = datetime.now(timezone.utc).isoformat()
                if self.state in {"connecting", "reconnecting"}:
                    self.state = "live"
                    self.last_error = None
                    logger.info("FFmpeg video progress detected; stream is live.")

    async def _read_stderr(self, stream: asyncio.StreamReader) -> None:
        while line := await stream.readline():
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            safe_text = self._redact(text) or text
            logger.warning("ffmpeg: %s", safe_text)
            lowered = text.lower()
            if any(marker in lowered for marker in _ERROR_MARKERS):
                self.last_error = safe_text[-1000:]

    async def _run_loop(self) -> None:
        delay = self.settings.reconnect_base_seconds
        while not self._stop_requested:
            report = self.dependency_report()
            try:
                command = build_ffmpeg_command(self.settings, report)
            except (OSError, StreamConfigurationError) as exc:
                self.last_error = self._redact(str(exc))
                self.state = "error"
                logger.error("Cannot launch FFmpeg: %s", self.last_error)
                return

            self.state = "connecting" if self.reconnect_count == 0 else "reconnecting"
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                self.last_error = self._redact(f"Could not start FFmpeg: {exc}")
                self.state = "error"
                logger.exception("Unable to launch FFmpeg.")
                return

            self._process = process
            assert process.stdout is not None and process.stderr is not None
            progress_task = asyncio.create_task(self._read_progress(process.stdout))
            stderr_task = asyncio.create_task(self._read_stderr(process.stderr))
            return_code = await process.wait()
            await asyncio.gather(progress_task, stderr_task, return_exceptions=True)
            self._process = None

            if self._stop_requested:
                break

            self.reconnect_count += 1
            if return_code and not self.last_error:
                self.last_error = f"FFmpeg exited with code {return_code}; reconnecting."
            logger.warning(
                "FFmpeg exited with code %s; reconnecting in %s seconds (attempt %s).",
                return_code,
                delay,
                self.reconnect_count,
            )
            self.state = "reconnecting"
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
            delay = min(delay * 2, self.settings.reconnect_max_seconds)

        self.state = "stopped"
        self.started_at = None
