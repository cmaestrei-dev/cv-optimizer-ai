"""API del SaaS (fase 5) sobre el mismo núcleo que usa Streamlit.

    uvicorn api.main:app --reload

Variables: DATABASE_URL, AUTH_* (ver api/auth.py), API_CORS_ORIGINS (orígenes del frontend,
separados por comas), AI_DAILY_CALLS (cupo de IA por cuenta) y API_INPROCESS_WORKER=0 para correr la
cola de trabajos aparte (`python -m core.jobs.worker`).
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import config  # noqa: F401  (carga .env antes de leer variables)
from api.limits import BodySizeLimit
from api.routers import alerts, applications, assist, dev, engine, market, profile
from api.web import mount_web
from core.applying import DuplicateVacancyError
from core.capture import CaptureError
from core.db import database_url, session_scope
from core.errors import UserInputError, describe
from core.jobs import worker
from core.llm import LLMConfigError, StructuredOutputError
from core.llm.client import LLMAuthError, LLMUnavailableError
from core.profile import service as profiles
from core.profile.repository import NotFoundError, UserExistsError
from core.usage import QuotaExceededError
from core.vacancy import NotAVacancyError
from utils.retry import RetryableError

_DOMAIN_ERRORS = (
    NotFoundError, UserExistsError, UserInputError, CaptureError, NotAVacancyError, QuotaExceededError,
    RetryableError, LLMAuthError, LLMConfigError, LLMUnavailableError, StructuredOutputError,
)

logger = logging.getLogger(__name__)


def _check_production_config() -> None:
    """Con Postgres (producción) se exige el proveedor de identidad. Evita que un `uvicorn` local con el
    `.env` de producción aplique migraciones de una rama sin fusionar a la base real."""
    if database_url().startswith("postgresql") and not os.environ.get("AUTH_JWKS_URL", "").strip():
        raise RuntimeError(
            "La API no arranca con Postgres sin AUTH_JWKS_URL. Para desarrollo usa SQLite (sin DATABASE_URL)."
        )
    if os.environ.get("K_SERVICE") and not database_url().startswith("postgresql"):  # Cloud Run lo define
        raise RuntimeError("En Cloud Run falta DATABASE_URL (Postgres): los datos se perderían con el contenedor.")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _check_production_config()
    profiles.ensure_ready()  # migraciones pendientes, una vez por proceso
    running = None
    if os.environ.get("API_INPROCESS_WORKER", "1") != "0":
        running = worker.start_thread()
    yield
    if running is not None:
        worker.stop_thread(*running)


def create_app() -> FastAPI:
    # API_PREFIX="/api" en producción (la misma app sirve la web en "/"); vacío en desarrollo y pruebas.
    prefix = os.environ.get("API_PREFIX", "").strip().rstrip("/")
    app = FastAPI(title="CV Optimizer AI", version="0.1.0", lifespan=_lifespan,
                  docs_url=f"{prefix}/docs", redoc_url=None, openapi_url=f"{prefix}/openapi.json")

    app.add_middleware(BodySizeLimit)  # se agrega antes que CORS: así CORS lo envuelve y el 413 lleva sus cabeceras
    origins = [o.strip() for o in os.environ.get("API_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(  # tokens en la cabecera Authorization, no cookies: sin credenciales de CORS
            CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")  # nadie puede incrustar la app (clickjacking)
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/assets/"):  # archivos de la web con huella en el nombre: no cambian
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        response.headers.setdefault("Cache-Control", "no-store")  # datos personales: nada en cachés intermedias
        return response

    async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
        # 404 con el mismo mensaje exista o no el recurso en otra cuenta: no se filtra qué ids existen.
        code, message = describe(exc)
        if code >= 500:
            logger.warning("Error de la IA: %s", exc)
        return JSONResponse({"detail": message}, status_code=code)

    for error in _DOMAIN_ERRORS:
        app.add_exception_handler(error, _domain_error)

    @app.exception_handler(DuplicateVacancyError)
    async def _duplicate(_request: Request, exc: DuplicateVacancyError) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "application_id": exc.application_id},
                            status_code=status.HTTP_409_CONFLICT)

    @app.get(f"{prefix}/config", tags=["sistema"])
    def public_config() -> dict[str, str]:
        """Configuración PÚBLICA para la web (sin sesión): la llave publicable de Clerk (es pública por diseño)."""
        return {"clerk_publishable_key": os.environ.get("CLERK_PUBLISHABLE_KEY", "").strip()}

    @app.get(f"{prefix}/health", tags=["sistema"])
    def health() -> dict[str, str]:
        with session_scope() as s:
            s.execute(text("select 1"))
        return {"status": "ok"}

    for router in (profile.router, assist.router, applications.router, market.router, engine.router, alerts.router):
        app.include_router(router, prefix=prefix)
    if alerts.cron_enabled():  # revisión programada del buzón: solo con un token largo configurado
        app.include_router(alerts.internal, prefix=prefix)
    if dev.enabled():  # entrar con un nombre: solo en desarrollo local (nunca con Postgres ni con JWKS)
        app.include_router(dev.router, prefix=prefix)
    if web_dist := os.environ.get("WEB_DIST", "").strip():  # después de la API: lo demás es la web
        mount_web(app, web_dist, prefix)
    return app


app = create_app()
