"""HTTP transport for the MCP server using Streamable HTTP transport with OAuth2/PKCE auth.

Required env vars:
    MCP_API_TOKEN  - Bearer token accepted for authenticated MCP requests
    MCP_BASE_URL   - Public base URL, e.g. https://mealplanner-mcp.example.com
    MCP_CLIENT_ID  - OAuth2 client ID
"""

import base64
import contextlib
import hashlib
import logging
import os
import secrets
import time
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from .mcp_server import server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_PUBLIC_PATHS = {
    "/health", "/token", "/authorize", "/authorize/approve",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource",
}

# Short-lived auth codes: code -> {code_challenge, client_id, redirect_uri, expires_at, ...}
_auth_codes: dict[str, dict] = {}
_CODE_TTL = 300  # 5 minutes

_NO_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

_ALLOWED_REDIRECT_URIS = {
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
}


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info("REQ  %s %s", request.method, request.url.path)
        response = await call_next(request)
        logger.info("RESP %s %s → %s", request.method, request.url.path, response.status_code)
        return response


def _get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return value


def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return secrets.compare_digest(expected, code_challenge)
    return secrets.compare_digest(code_verifier, code_challenge)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            base = os.environ.get("MCP_BASE_URL", "").rstrip("/")
            www_auth = 'Bearer realm="MCP"'
            if base:
                www_auth += f', resource_metadata="{base}/.well-known/oauth-protected-resource"'
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": www_auth},
            )

        token = auth.removeprefix("Bearer ")
        expected = _get_required_env("MCP_API_TOKEN")
        if not secrets.compare_digest(token, expected):
            return JSONResponse({"error": "forbidden"}, status_code=403)

        return await call_next(request)


session_manager = StreamableHTTPSessionManager(app=server, stateless=True)


async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
    await session_manager.handle_request(scope, receive, send)


async def health(request: Request) -> Response:
    return Response('{"status": "ok"}', media_type="application/json")


async def oauth_metadata(request: Request) -> JSONResponse:
    """RFC 8414 OAuth Authorization Server Metadata."""
    base = _get_required_env("MCP_BASE_URL").rstrip("/")
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
    })


async def protected_resource_metadata(request: Request) -> JSONResponse:
    """RFC 9728 OAuth Protected Resource Metadata."""
    base = _get_required_env("MCP_BASE_URL").rstrip("/")
    return JSONResponse({
        "resource": base + "/",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
    })


async def authorize(request: Request) -> Response:
    """Authorization Code endpoint (RFC 6749 §4.1) with PKCE (RFC 7636)."""
    params = dict(request.query_params)
    response_type = params.get("response_type", "")
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "S256")
    state = params.get("state", "")

    static_client_id = os.environ.get("MCP_CLIENT_ID", "")
    if client_id != static_client_id:
        return JSONResponse({"error": "unauthorized_client"}, status_code=401)

    if response_type != "code":
        return JSONResponse({"error": "unsupported_response_type"}, status_code=400)

    if not redirect_uri or not code_challenge:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    if redirect_uri not in _ALLOWED_REDIRECT_URIS:
        return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)

    base = _get_required_env("MCP_BASE_URL").rstrip("/")
    approve_url = f"{base}/authorize/approve?" + urlencode(params)
    return HTMLResponse(f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Mealplanner MCP — Authorize</title>
  <style>
    body {{ font-family: system-ui, sans-serif; display: flex; justify-content: center;
           align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }}
    .card {{ background: white; border-radius: 8px; padding: 40px; max-width: 400px;
             box-shadow: 0 2px 8px rgba(0,0,0,.12); text-align: center; }}
    h2 {{ margin: 0 0 8px; }}
    p {{ color: #666; margin: 0 0 24px; }}
    a.btn {{ display: inline-block; background: #3f51b5; color: white; padding: 12px 32px;
             border-radius: 4px; text-decoration: none; font-size: 15px; }}
    a.btn:hover {{ background: #303f9f; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>Mealplanner MCP</h2>
    <p>Claude is requesting access to your meal plans and recipes.</p>
    <a class="btn" href="{approve_url}">Approve Access</a>
  </div>
</body>
</html>""")


async def authorize_approve(request: Request) -> Response:
    """User clicked Approve — issue code and redirect back to Claude."""
    params = dict(request.query_params)
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "S256")
    state = params.get("state", "")

    code = secrets.token_urlsafe(32)
    _auth_codes[code] = {
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "resource": params.get("resource", ""),
        "scope": params.get("scope", "openid profile"),
        "expires_at": time.time() + _CODE_TTL,
    }

    callback = redirect_uri + "?" + urlencode({"code": code, "state": state})
    return RedirectResponse(callback, status_code=302)


async def token(request: Request) -> JSONResponse:
    """Token endpoint — supports authorization_code (PKCE) and client_credentials."""
    form = await request.form()
    grant_type = form.get("grant_type", "")
    logger.info("TOKEN req grant_type=%r fields=%r", grant_type, sorted(form.keys()))

    if grant_type == "authorization_code":
        code = str(form.get("code", ""))
        code_verifier = str(form.get("code_verifier", ""))
        resource_req = str(form.get("resource", ""))
        redirect_uri_req = str(form.get("redirect_uri", ""))
        client_id_req = str(form.get("client_id", ""))
        client_secret_req = str(form.get("client_secret", ""))

        static_client_id = os.environ.get("MCP_CLIENT_ID", "")
        if client_id_req != static_client_id:
            return JSONResponse({"error": "invalid_client"}, status_code=401, headers=_NO_CACHE)

        static_secret = os.environ.get("MCP_CLIENT_SECRET", "")
        if static_secret and client_secret_req:
            if not secrets.compare_digest(client_secret_req, static_secret):
                return JSONResponse({"error": "invalid_client"}, status_code=401, headers=_NO_CACHE)

        stored = _auth_codes.pop(code, None)
        if not stored or time.time() > stored["expires_at"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400, headers=_NO_CACHE)

        if stored["client_id"] != client_id_req:
            return JSONResponse({"error": "invalid_grant"}, status_code=400, headers=_NO_CACHE)

        if not _verify_pkce(code_verifier, stored["code_challenge"], stored["code_challenge_method"]):
            return JSONResponse({"error": "invalid_grant"}, status_code=400, headers=_NO_CACHE)

        api_token = _get_required_env("MCP_API_TOKEN")
        resp: dict = {
            "access_token": api_token,
            "token_type": "Bearer",
            "expires_in": 86400,
            "scope": stored.get("scope", "openid profile"),
        }
        if resource_req:
            resp["resource"] = resource_req
        return JSONResponse(resp, headers=_NO_CACHE)

    if grant_type == "client_credentials":
        client_id = str(form.get("client_id", ""))
        client_secret = str(form.get("client_secret", ""))
        expected_id = _get_required_env("MCP_CLIENT_ID")
        expected_secret = _get_required_env("MCP_CLIENT_SECRET")

        if not secrets.compare_digest(client_id, expected_id) or \
           not secrets.compare_digest(client_secret, expected_secret):
            return JSONResponse({"error": "invalid_client"}, status_code=401)

        api_token = _get_required_env("MCP_API_TOKEN")
        return JSONResponse({
            "access_token": api_token,
            "token_type": "Bearer",
            "expires_in": 86400,
            "scope": "openid profile",
        })

    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    async with session_manager.run():
        logger.info("Mealplanner MCP server started")
        yield


starlette_app = Starlette(
    routes=[
        Route("/health", endpoint=health, methods=["GET"]),
        Route("/.well-known/oauth-authorization-server", endpoint=oauth_metadata, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource", endpoint=protected_resource_metadata, methods=["GET"]),
        Route("/authorize", endpoint=authorize, methods=["GET"]),
        Route("/authorize/approve", endpoint=authorize_approve, methods=["GET"]),
        Route("/token", endpoint=token, methods=["POST"]),
        Mount("/mcp", app=handle_streamable_http),
        Mount("/", app=handle_streamable_http),
    ],
    lifespan=lifespan,
)
starlette_app.add_middleware(BearerAuthMiddleware)
starlette_app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://claude.ai", "https://claude.com"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
starlette_app.add_middleware(RequestLogMiddleware)

if __name__ == "__main__":
    uvicorn.run(starlette_app, host="0.0.0.0", port=8001, log_level="info")
