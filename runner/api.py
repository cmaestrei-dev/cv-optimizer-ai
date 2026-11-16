"""Cliente de la API de la app con el token del bot (solo la librería estándar, siempre con timeout)."""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str, body: dict | None = None):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail, self.body = status, detail, body or {}


@dataclass(frozen=True)
class Vacancy:
    id: int
    created: bool  # False: ya estaba en la app
    role: str
    company: str
    score: int | None
    missing: list[str]


class Api:
    def __init__(self, base: str, token: str, *, timeout: float = 60):
        self.base, self.token, self.timeout = base.rstrip("/"), token, timeout

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                payload = {}
            detail = payload.get("detail") if isinstance(payload.get("detail"), str) else raw[:200].decode("utf-8", "replace")
            raise ApiError(e.code, detail, payload) from None

    def get(self, path: str) -> dict | list:
        return json.loads(self._request("GET", path)[1])

    def post(self, path: str, body: dict | None = None) -> dict:
        return json.loads(self._request("POST", path, body or {})[1])

    def me(self) -> dict:
        return self.get("/me")

    def usage(self) -> dict:
        return self.get("/usage")

    def add_vacancy(self, *, text: str, url: str, posted: date | None) -> Vacancy:
        body = {"text": text[:20000], "url": url, "prepare": True, "posted_on": posted.isoformat() if posted else None}
        try:
            out, created = self.post("/vacancies", body), True
        except ApiError as e:
            if e.status != 409 or "application_id" not in e.body:
                raise
            out, created = self.get(f"/applications/{e.body['application_id']}"), False
        return Vacancy(out["id"], created, out["role"], out["company"], out["match_score"], out.get("missing_musts") or [])

    def make_cv(self, application_id: int, *, wait: float = 180) -> dict:
        """Genera el CV a la medida (trabajo en segundo plano) y devuelve su registro (id, archivo, huella)."""
        job = self.post(f"/applications/{application_id}/cvs", {"focus": ""})
        deadline = time.monotonic() + wait
        while job["status"] in ("queued", "running"):
            if time.monotonic() > deadline:
                raise ApiError(504, "El CV tardó demasiado; se intentará en la próxima vuelta")
            time.sleep(3)
            job = self.get(f"/jobs/{job['id']}")
        if job["status"] != "done":
            raise ApiError(500, job.get("error") or "No se pudo generar el CV")
        cvs = self.get(f"/applications/{application_id}")["cvs"]
        return cvs[-1]

    def download_cv(self, cv_id: int, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self._request("GET", f"/cvs/{cv_id}/pdf")[1])
        return dest
