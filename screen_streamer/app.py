from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .config import ConfigurationError, Settings
from .controller import StreamController
from .discord_bot import create_bot

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent / "web"


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    controller = StreamController(config)
    bot = None
    bot_task: asyncio.Task[None] | None = None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal bot, bot_task
        if config.discord_bot_token:
            try:
                bot = create_bot(config, controller)
            except ConfigurationError:
                logger.exception("Discord configuration is invalid; bot was not started.")
            else:
                async def run_bot() -> None:
                    try:
                        await bot.start(config.discord_bot_token)
                    except Exception:
                        logger.error(
                            "Discord bot connection failed. Check DISCORD_BOT_TOKEN "
                            "and network connectivity; credential values are not logged."
                        )

                bot_task = asyncio.create_task(run_bot(), name="discord-bot")
        else:
            logger.warning(
                "Discord bot is disabled. Set DISCORD_BOT_TOKEN and SCREEN1_DISCORD_USER_ID "
                "to enable participant controls."
            )
        yield
        await controller.stop()
        if bot:
            await bot.close()
        if bot_task:
            try:
                await asyncio.wait_for(bot_task, timeout=5)
            except asyncio.TimeoutError:
                bot_task.cancel()
                with suppress(asyncio.CancelledError):
                    await bot_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(
        title="Discord Linux Screen Streamer",
        description="Video-only Linux desktop streaming with RTMP, HLS, and allowlisted Discord controls.",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.controller = controller

    @app.get("/", response_class=HTMLResponse)
    async def player() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/health")
    async def health() -> JSONResponse:
        status = controller.status()
        return JSONResponse(
            {
                "ok": True,
                "streamState": status["state"],
                "dependenciesReady": status["dependenciesReady"],
                "dependencyIssues": status["dependencyIssues"],
            }
        )

    @app.get("/api/status")
    async def stream_status() -> dict:
        return controller.status()

    @app.get("/hls/{filename}")
    async def hls_file(filename: str) -> Response:
        if filename != "stream.m3u8" and not (
            filename.startswith("segment_") and filename.endswith(".ts")
        ):
            raise HTTPException(status_code=404, detail="HLS file not found.")
        path = config.hls_output_dir / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="HLS playlist is not ready yet.")
        headers = {"Cache-Control": "no-store"} if filename.endswith(".m3u8") else {
            "Cache-Control": "public, max-age=2"
        }
        media_type = "application/vnd.apple.mpegurl" if filename.endswith(".m3u8") else "video/mp2t"
        return FileResponse(path, media_type=media_type, headers=headers)

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    return app
