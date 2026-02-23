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

logger = logging.getLogger(__name__)

_inner_app = FastAPI(title="Mycroft Server", version="0.1.0")
_inner_app.include_router(linear_webhook_router)


@_inner_app.websocket("/ws")
async def ws_endpoint(ws):
    logger.info("WS handler reached!")
    await websocket_endpoint(ws)


@_inner_app.get("/health")
async def _health():
    return {"status": "ok"}


async def app(scope, receive, send):
    """ASGI wrapper that logs every request before FastAPI."""
    logger.info("ASGI scope: type=%s path=%s", scope.get("type"), scope.get("path"))
    if scope["type"] == "websocket":
        headers = dict(scope.get("headers", []))
        logger.info("WS headers: %s", {k.decode(): v.decode() for k, v in headers.items()})
        # Debug: check routes
        for route in _inner_app.routes:
            rtype = type(route).__name__
            rpath = getattr(route, "path", "N/A")
            match_result, _ = route.matches(scope)
            logger.info("Route %s path=%s match=%s", rtype, rpath, match_result)
    async def debug_send(message):
        logger.info("ASGI send: type=%s message=%s", message.get("type"), message)
        await send(message)

    try:
        await _inner_app(scope, receive, debug_send)
    except Exception as e:
        logger.error("ASGI exception: %s: %s", type(e).__name__, e, exc_info=True)
        raise




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
