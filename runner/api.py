"""Cliente de la API de la app con el token del bot (solo la librería estándar, siempre con timeout)."""

import base64
import json
import secrets
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
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
    status: str = ""
    has_cv: bool = False

    @property
    def unfinished(self) -> bool:
        """Ya estaba en la app pero sin CV ni envío (p. ej. una vuelta anterior se cortó): se termina de preparar."""
        return not self.created and not self.has_cv and self.status in ("por_revisar", "guardada")


class Api:
    def __init__(self, base: str, token: str, *, timeout: float = 180):  # análisis con IA + arranque en frío
        self.base, self.token, self.timeout = base.rstrip("/"), token, timeout

    def _request(self, method: str, path: str, body: dict | None = None, *, raw: bytes | None = None,
                 content_type: str = "application/json") -> tuple[int, bytes]:
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": content_type, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read()
        except (TimeoutError, urllib.error.URLError) as e:
            if isinstance(e, urllib.error.HTTPError):
                raise self._http_error(e) from None
            raise ApiError(504, "La app no respondió a tiempo (¿conexión lenta o servidor arrancando?)") from None
        except urllib.error.HTTPError as e:
            raise self._http_error(e) from None

    @staticmethod
    def _http_error(e: urllib.error.HTTPError) -> "ApiError":
        raw = e.read()
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}
        detail = payload.get("detail") if isinstance(payload.get("detail"), str) else raw[:200].decode("utf-8", "replace")
        return ApiError(e.code, detail, payload)

    def get(self, path: str) -> dict | list:
        return json.loads(self._request("GET", path)[1])

    def post(self, path: str, body: dict | None = None) -> dict:
        return json.loads(self._request("POST", path, body or {})[1])

    def me(self) -> dict:
        return self.get("/me")

    def usage(self) -> dict:
        return self.get("/usage")

    def add_vacancy(self, *, text: str, url: str, posted: date | None, images: Sequence[tuple[bytes, str]] = ()) -> Vacancy:
        body = {"text": text[:20000], "url": url, "prepare": True, "posted_on": posted.isoformat() if posted else None}
        if images:  # p. ej. el afiche de una publicación de LinkedIn: la app transcribe su texto
            body["images"] = [{"mime": mime, "data": base64.b64encode(data).decode()} for data, mime in images]
        try:
            out, created = self.post("/vacancies", body), True
        except ApiError as e:
            if e.status != 409 or "application_id" not in e.body:
                raise
            out, created = self.get(f"/applications/{e.body['application_id']}"), False
        return Vacancy(out["id"], created, out["role"], out["company"], out["match_score"], out.get("missing_musts") or [],
                       out.get("status", ""), bool(out.get("cvs")))

    def make_cv(self, application_id: int, *, wait: float = 180) -> dict:
        """Genera el CV a la medida (trabajo en segundo plano) y devuelve su registro (id, archivo, huella) con la
        cobertura de palabras clave de la vacante (`keywords`, vacía si la app es anterior a la v3)."""
        job = self.wait_job(self.post(f"/applications/{application_id}/cvs", {"focus": ""}), wait=wait)
        cvs = self.get(f"/applications/{application_id}")["cvs"]
        return {**cvs[-1], "keywords": (job.get("result") or {}).get("keywords") or {}}

    def wait_job(self, job: dict, *, wait: float = 300) -> dict:
        deadline = time.monotonic() + wait
        while job["status"] in ("queued", "running"):
            if time.monotonic() > deadline:
                raise ApiError(504, "La app tardó demasiado; inténtalo de nuevo en unos minutos")
            time.sleep(3)
            job = self.get(f"/jobs/{job['id']}")
        if job["status"] != "done":
            raise ApiError(500, job.get("error") or "El trabajo falló")
        return job

    def import_profile(self, pdf: Path) -> tuple[dict, dict]:
        """Sube el CV o el PDF de LinkedIn, espera la lectura y guarda todo lo nuevo (nunca lo repetido)."""
        boundary = "----cvo" + secrets.token_hex(12)
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{pdf.name}\"\r\n"
                "Content-Type: application/pdf\r\n\r\n").encode() + pdf.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        job = json.loads(self._request("POST", "/profile/import", raw=body, content_type=f"multipart/form-data; boundary={boundary}")[1])
        result = self.wait_job(job)["result"]
        choice = {"experiences": result["new_experiences"], "skills": result["new_skills"],
                  "education": result["new_education"], "fill_contact": True}
        return result, self.post(f"/profile/import/{job['id']}/apply", choice)

    def download_cv(self, cv_id: int, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self._request("GET", f"/cvs/{cv_id}/pdf")[1])
        return dest
