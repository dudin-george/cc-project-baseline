"""FastAPI application and uvicorn startup for Mycroft server."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from mycroft.server.settings import settings
from mycroft.server.ws.handler import websocket_endpoint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="Mycroft Server", version="0.1.0")


@app.websocket("/ws")
async def ws_endpoint(ws):
    await websocket_endpoint(ws)


@app.get("/health")
async def health():
    return {"status": "ok"}


def cli() -> None:
    """Entry point for mycroft-server command."""
    uvicorn.run(
        "mycroft.server.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    cli()
