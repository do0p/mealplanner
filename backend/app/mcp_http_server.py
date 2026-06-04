"""HTTP transport for the MCP server — no authentication (LAN-only deployment)."""

import contextlib
import logging
from collections.abc import AsyncIterator

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from .mcp_server import server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session_manager = StreamableHTTPSessionManager(app=server, stateless=True)


async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
    await session_manager.handle_request(scope, receive, send)


async def health(request: Request) -> Response:
    return Response('{"status": "ok"}', media_type="application/json")


@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    async with session_manager.run():
        logger.info("Mealplanner MCP server started")
        yield


starlette_app = Starlette(
    routes=[
        Route("/health", endpoint=health, methods=["GET"]),
        Mount("/mcp", app=handle_streamable_http),
        Mount("/", app=handle_streamable_http),
    ],
    lifespan=lifespan,
)
starlette_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

if __name__ == "__main__":
    uvicorn.run(starlette_app, host="0.0.0.0", port=8001, log_level="info")
