"""FastAPI application and uvicorn startup for Mycroft server."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from mycroft.server.settings import settings
from mycroft.server.ws.handler import websocket_endpoint
from mycroft.server.linear.webhook import router as linear_webhook_router
import mycroft.server.linear.blocker_webhook  # noqa: F401 — registers handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="Mycroft Server", version="0.1.0")
app.include_router(linear_webhook_router)

logger = logging.getLogger(__name__)


@app.middleware("http")
async def debug_middleware(request, call_next):
    logger.info("HTTP request: %s %s headers=%s", request.method, request.url.path, dict(request.headers))
    return await call_next(request)


@app.websocket("/ws")
async def ws_endpoint(ws):
    logger.info("WS handler reached! scope=%s", {k: v for k, v in ws.scope.items() if k in ("type", "path", "scheme", "headers")})
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
