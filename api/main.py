"""API del SaaS (fase 5) sobre el mismo núcleo que usa Streamlit.

    uvicorn api.main:app --reload

Variables: DATABASE_URL, AUTH_* (ver api/auth.py) y API_CORS_ORIGINS (orígenes del frontend,
separados por comas).
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import config  # noqa: F401  (carga .env antes de leer variables)
from api.routers import applications, market, profile
from core.db import session_scope
from core.profile import service as profiles
from core.profile.repository import NotFoundError, UserExistsError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    profiles.ensure_ready()  # migraciones pendientes, una vez por proceso
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="CV Optimizer AI", version="0.1.0", lifespan=_lifespan)

    origins = [o.strip() for o in os.environ.get("API_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(  # tokens en la cabecera Authorization, no cookies: sin credenciales de CORS
            CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Cache-Control", "no-store")  # datos personales: nada en cachés intermedias
        return response

    @app.exception_handler(NotFoundError)
    async def _not_found(_request: Request, _exc: NotFoundError) -> JSONResponse:
        # Mismo mensaje exista o no el recurso en otra cuenta: no se filtra qué ids existen.
        return JSONResponse({"detail": "No encontrado"}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(UserExistsError)
    async def _conflict(_request: Request, _exc: UserExistsError) -> JSONResponse:
        return JSONResponse({"detail": "Ya existe"}, status_code=status.HTTP_409_CONFLICT)

    @app.get("/health", tags=["sistema"])
    def health() -> dict[str, str]:
        with session_scope() as s:
            s.execute(text("select 1"))
        return {"status": "ok"}

    for router in (profile.router, applications.router, market.router):
        app.include_router(router)
    return app


app = create_app()
