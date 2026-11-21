"""Postular en Magneto con la sesión de la persona: la misma petición que hace su página al pulsar «Aplicar».

Lo verificado leyendo su página y consultándola sin postular (2026-11-21):
- La sesión es una cookie `access_token` que vence en más o menos una hora. Abrir
  `login.magneto365.com/candidates` la renueva sola, porque la persona entró con Google en el navegador del bot.
- Antes de postular, la página consulta `verify-applications-by-dni/{id}`. Si la cédula ya tiene postulaciones a
  esa vacante (p. ej. con otra cuenta), ofrece cambiar de cuenta. El bot ahí se detiene, sin cambiar nada.
- Con cuestionario de filtro, la página consulta primero `questionnaire/already-answered/{id}` y luego trae
  `questionnaire/{id}`. Las respuestas van en el mismo envío:
  `questionnaires: [{id, questions: [{id, type, answer: [ids]} | {id, type, openAnswer}]}]`.
  Los tipos son 0 = una opción, 1 = varias opciones, 2 = abierta corta (140 caracteres) y 3 = abierta larga.
- «Aplicar» es `POST /jobs/v1/jobs/apply`, sin pantalla de revisión. Por eso el modo prueba no envía nada.
- Magneto envía a la empresa el perfil de Magneto, no un PDF por vacante: el CV de la app queda como referencia.
- Ante una verificación o un captcha, el bot se detiene; nunca la resuelve.
"""

import time
from collections.abc import Callable
from pathlib import Path

from runner.answers import pick_option
from runner.linkedin import ApplyResult, Question

API = "https://api.magneto365.com/jobs/v1"
LOGIN = "https://login.magneto365.com/candidates"
WEB = "https://www.magneto365.com"
UNIQUE, MULTIPLE, OPEN_SHORT, OPEN_LONG = 0, 1, 2, 3
LIMITS = {OPEN_SHORT: 140, OPEN_LONG: 2500}

Answerer = Callable[[list[Question]], dict[str, str]]


class Session:
    """Las peticiones de la página, con la sesión del navegador del bot. El token nunca se muestra ni se guarda."""

    def __init__(self, page):
        self.page = page
        self.token = ""

    def renew(self) -> bool:
        self.page.goto(LOGIN, wait_until="domcontentloaded")
        time.sleep(6)
        cookies = self.page.context.cookies(WEB)
        self.token = next((c["value"] for c in cookies if c["name"] == "access_token"), "")
        return bool(self.token)

    def _headers(self) -> dict:
        return {"Authorization": "Bearer " + self.token, "Origin": WEB, "Referer": WEB + "/", "Accept": "application/json"}

    @staticmethod
    def _answer(response) -> tuple[int, object]:
        try:
            return response.status, response.json()
        except Exception:  # noqa: BLE001 — una respuesta que no es JSON se informa por su estado
            return response.status, None

    def get(self, path: str) -> tuple[int, object]:
        return self._answer(self.page.context.request.get(API + path, headers=self._headers(), timeout=30_000))

    def post(self, path: str, body: dict) -> tuple[int, object]:
        return self._answer(self.page.context.request.post(API + path, data=body, headers=self._headers(), timeout=60_000))


def slug(url: str) -> str:
    return url.split("#")[0].split("?")[0].rstrip("/").rsplit("/", 1)[-1]


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def _questions(data: dict) -> list[tuple[int, dict, Question]]:
    out = []
    for questionnaire in (data or {}).get("questionnaires") or []:
        for q in questionnaire.get("questions") or []:
            options = [a.get("titleAnswer", "").strip() for a in q.get("possibleAnswers") or []]
            kind = ("radio" if options else ("textarea" if q.get("answerType") == OPEN_LONG else "text"))
            label = str(q.get("titleQuestion", "")).strip()
            out.append((questionnaire["id"], q, Question(kind, label, True, "", options, [str(q.get("id"))])))
    return out


def _fill(data: dict, answerer: Answerer) -> tuple[list[dict], list[str]]:
    """Las respuestas en el formato de la página y las preguntas que quedaron sin respuesta."""
    items = _questions(data)
    answers = answerer([q for _, _, q in items]) if items else {}
    by_questionnaire: dict[int, list[dict]] = {}
    missing = []
    for questionnaire_id, raw, q in items:
        value = (answers.get(q.label) or "").strip()
        kind = raw.get("answerType", OPEN_SHORT)
        entry = None
        if value and q.options:
            if option := pick_option(value, q.options):
                chosen = raw["possibleAnswers"][q.options.index(option)]
                entry = {"id": raw["id"], "type": kind, "answer": [chosen["id"]]}
        elif value:
            entry = {"id": raw["id"], "type": kind, "openAnswer": _shorten(value, LIMITS.get(kind, 140))}
        if entry is None:
            missing.append(q.label)
        else:
            by_questionnaire.setdefault(questionnaire_id, []).append(entry)
    return [{"id": k, "questions": v} for k, v in by_questionnaire.items()], missing


def apply(page, offer_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, session=None) -> ApplyResult:
    """Postula a una oferta de Magneto. `cv_pdf` no se envía (Magneto usa tu perfil); queda en la app."""
    session = session or Session(page)
    if not session.renew():
        return ApplyResult("sin_sesion", "El navegador del bot no tiene sesión de Magneto: python -m runner entrar magneto")
    status, job = session.get(f"/jobs/slug/{slug(offer_url)}")
    if status == 401:
        return ApplyResult("sin_sesion", "Magneto pidió iniciar sesión: python -m runner entrar magneto")
    if status == 404 or not isinstance(job, dict) or not job.get("id"):
        return ApplyResult("saltada", "La oferta ya no está en Magneto")
    if status != 200:
        return ApplyResult("error", f"Magneto respondió {status} al abrir la oferta")
    job_id = job["id"]
    if job.get("isApplied"):
        return ApplyResult("ya_postulada")
    if job.get("canApply") is False or job.get("status", "published") != "published":
        return ApplyResult("saltada", "Magneto no permite postular a esta oferta (¿cerrada?)")
    status, previous = session.get(f"/jobs/verify-applications-by-dni/{job_id}")
    if status == 200 and previous:
        return ApplyResult("ya_postulada", "Magneto dice que tu cédula ya tiene una postulación a esta oferta "
                                           "(quizá con otra cuenta): revísalo tú en Magneto")
    questionnaires: list[dict] = []
    if job.get("hasPrefilterQuestionnaire"):
        status, answered = session.get(f"/questionnaire/already-answered/{job_id}")
        if status == 200 and isinstance(answered, dict) and answered.get("isAlreadyAnswered"):
            return ApplyResult("ya_postulada", "Ya respondiste el cuestionario de esta oferta")
        status, data = session.get(f"/questionnaire/{job_id}")
        if status != 200 or not isinstance(data, dict):
            return ApplyResult("error", f"Magneto respondió {status} al traer el cuestionario")
        questionnaires, missing = _fill(data, answerer)
        if missing:
            return ApplyResult("saltada", "Preguntas de filtro sin respuesta en tu perfil ni en tu banco",
                               unanswered=missing)
    if not submit:
        return ApplyResult("revisada", "Modo prueba: todo listo y no se envió"
                                       + (" (cuestionario respondido)" if questionnaires else ""))
    body = {"jobId": job_id, "suggestedByMatcher": False,
            "sourceOrigins": {"f_magneto": False, "isPublicJobsite": False}, "utmPayload": {}}
    if questionnaires:
        body["questionnaires"] = questionnaires
    status, answer = session.post("/jobs/apply", body)
    if status not in (200, 201):
        message = answer.get("message", "") if isinstance(answer, dict) else ""
        return ApplyResult("error", f"Magneto no aceptó la postulación (HTTP {status}{': ' + str(message)[:120] if message else ''})")
    time.sleep(2)
    status, job = session.get(f"/jobs/slug/{slug(offer_url)}")
    if status == 200 and isinstance(job, dict) and job.get("isApplied"):
        return ApplyResult("enviada", "Confirmada en Magneto")
    return ApplyResult("error", "Magneto aceptó el envío pero la oferta no aparece como postulada: revísala tú")
