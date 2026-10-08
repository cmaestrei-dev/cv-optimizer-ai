"""Sirve la web (web/dist) desde la misma app que la API: un solo servicio, mismo origen, sin CORS.

Solo se activa con WEB_DIST y un API_PREFIX (p. ej. "/api"): así ninguna ruta de la web puede
confundirse con una de la API. Las rutas de la web que no son archivos devuelven index.html (la
navegación la resuelve React).
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


def mount_web(app: FastAPI, dist: str, api_prefix: str) -> None:
    root = Path(dist).resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"WEB_DIST no tiene index.html: {root}")
    if not api_prefix:
        raise RuntimeError("Para servir la web hace falta API_PREFIX (p. ej. /api)")
    api_root = api_prefix.strip("/")
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)  # HEAD: monitores de disponibilidad
    def spa(path: str):
        if path == api_root or path.startswith(f"{api_root}/"):  # ruta de API inexistente: 404 de API, no la web
            return JSONResponse({"detail": "No encontrado"}, status_code=404)
        try:
            candidate = (root / path).resolve()
        except (ValueError, OSError):  # p. ej. un carácter nulo en la ruta
            candidate = root
        if path and candidate.is_file() and root in candidate.parents:  # archivos sueltos (favicon…)
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
