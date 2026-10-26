"""Standalone, secret-free health page for a Render web service."""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Keep Live Health Service")


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Service status</title>
  </head>
  <body>
    <main>
      <h1>Service is running</h1>
      <p>The standalone health service is online.</p>
    </main>
  </body>
</html>"""


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level="info",
    )
