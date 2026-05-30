import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404:
                return await super().get_response("index.html", scope)
            raise

from app.db import init_db

_version_file = Path(__file__).parent.parent.parent / "VERSION"
APP_VERSION = _version_file.read_text().strip() if _version_file.exists() else "unknown"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Mealplanner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.get("/version")
def version():
    from app.config import settings
    return {"version": APP_VERSION, "display_timezone": settings.display_timezone}


@app.get("/health")
def health():
    return {"status": "ok"}


# Routers are included as they are built.
from app.routers import recipes, plans, imports  # noqa: E402

app.include_router(recipes.router)
app.include_router(plans.router)
app.include_router(imports.router)


# Serve the built Angular app if present. In dev the frontend runs separately
# on :4200, so the dist dir may not exist — don't fail startup if it's missing.
_frontend_dist = os.path.join(os.path.dirname(__file__), "../frontend-dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", SPAStaticFiles(directory=_frontend_dist, html=True), name="static")
else:
    @app.get("/")
    def _root():
        return JSONResponse(
            {"app": "Mealplanner", "version": APP_VERSION, "note": "frontend not built"}
        )
