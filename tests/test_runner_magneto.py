"""Magneto: búsqueda pública (datos de ejemplo, sin red) y postulación contra una sesión falsa (nunca la real)."""

from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from runner import __main__ as cli
from runner import magneto, magneto_apply
from runner.config import Search

TODAY = date(2026, 11, 21)


def row(**over):
    base = {"id": 1143279, "jobSlug": "practicante-de-sistemas-1143279", "title": "Practicante de sistemas",
            "companyName": "Banco Ejemplo", "cities": ["Bogotá, D.C."], "isRemote": False, "status": "published",
            "canApply": True, "isApplied": False, "publishDate": "2026-11-19T14:10:15.212Z",
            "experienceMonthsNumber": 0, "educationLevel": [{"name": "Profesional"}], "contractType": "6",
            "minSalary": 1850000, "maxSalary": 1850000, "hasPrefilterQuestionnaire": True,
            "description": "<p>Buscamos <b>estudiante</b> de sistemas.</p><ul><li>Python</li><li>SQL</li></ul>"}
    base.update(over)
    return base


def test_search_url_uses_the_public_search_with_the_only_accepted_order():
    url = magneto.search_url(Search("desarrollador de software", "Colombia", 7, False, "magneto"), page=2)
    q = parse_qs(urlparse(url).query)
    assert url.startswith(magneto.API)
    assert q["queries[0][term]"] == ["desarrollador de software"] and q["order[field]"] == ["_score"]
    assert q["filters[locations][0]"] == ["C47"] and q["paginator[page]"] == ["2"]


def test_parse_builds_the_posting_text_and_filters():
    data = {"rows": [
        row(),
        row(id=2, jobSlug="viejo-2", publishDate="2026-09-01T00:00:00Z"),           # demasiado vieja
        row(id=3, jobSlug="ya-3", isApplied=True),                                  # ya postulada
        row(id=4, jobSlug="cerrada-4", canApply=False),
        row(id=5, jobSlug="remota-5", cities=["Medellín"], isRemote=True),
        row(id=6, jobSlug="medellin-6", cities=["Medellín"]),
    ]}
    cards = magneto.parse(data, place="Colombia", days=30, today=TODAY)
    assert [c.job_id for c in cards] == ["mg:1143279", "mg:5", "mg:6"]
    card = cards[0]
    assert card.url == "https://www.magneto365.com/co/empleos/practicante-de-sistemas-1143279" and card.questionnaire
    assert "Buscamos estudiante de sistemas." in card.text and "- Python" in card.text
    assert "Salario: 1.850.000" in card.text and "a 1.850.000" not in card.text and "Contrato" not in card.text
    assert "Experiencia requerida: sin experiencia" in card.text and "Formación: Profesional" in card.text
    near = magneto.parse(data, place="Cartagena", days=30, today=TODAY)
    assert [c.job_id for c in near] == ["mg:5"]  # en otra ciudad solo sirven las remotas
    assert [c.job_id for c in magneto.parse(data, place="Remoto", days=30, today=TODAY)] == ["mg:5"]


def test_job_ids_from_magneto_links():
    assert cli._job_id("magneto", "https://www.magneto365.com/co/empleos/practicante-de-sistemas-1143279") == "mg:1143279"
    assert cli.PLATFORM_PORTAL["Magneto"] == "magneto"


class FakeSession:
    """Responde como la API de Magneto vista el 2026-11-21 y anota lo que el bot envía."""

    def __init__(self, *, job=None, previous=(), answered=False, questionnaire=None, logged=True, accept=True):
        self.job = {"id": 1143279, "isApplied": False, "canApply": True, "status": "published",
                    "hasPrefilterQuestionnaire": questionnaire is not None, **(job or {})}
        self.previous, self.answered, self.questionnaire = list(previous), answered, questionnaire
        self.logged, self.accept, self.posts, self.processes = logged, accept, [], []

    def renew(self):
        return self.logged

    def get(self, path):
        if path == magneto_apply.PROCESSES:
            return 200, {"rows": [{"id": i} for i in self.processes]}
        if path.startswith("/jobs/slug/"):
            return 200, self.job
        if path.startswith("/jobs/verify-applications-by-dni/"):
            return 200, self.previous
        if path.startswith("/questionnaire/already-answered/"):
            return 200, {"isAlreadyAnswered": self.answered}
        if path.startswith("/questionnaire/"):
            return 200, {"id": self.job["id"], "questionnaires": [self.questionnaire]}
        return 404, None

    def post(self, path, body):
        self.posts.append((path, body))
        if not self.accept:
            return 400, {"message": "Invalid body"}
        self.processes.append(self.job["id"])  # como Magneto: la oferta no pasa a isApplied, pero sí a «Mis procesos»
        return 201, {"applicationId": 99}


QUESTIONNAIRE = {"id": 1003492, "questions": [
    {"id": 1, "titleQuestion": "¿Cuántos meses de experiencia tienes?", "answerType": 1, "possibleAnswers": [
        {"id": 11, "titleAnswer": "Sin experiencia"}, {"id": 12, "titleAnswer": "1 a 6 meses"},
        {"id": 13, "titleAnswer": "12 a 24 meses"}, {"id": 14, "titleAnswer": "Más de 24 meses"}]},
    {"id": 2, "titleQuestion": "¿Qué carrera estudias actualmente y en qué universidad?", "answerType": 2,
     "possibleAnswers": []},
]}
URL = "https://www.magneto365.com/co/empleos/practicante-de-sistemas-1143279"


def answerer(questions):
    known = {"¿Cuántos meses de experiencia tienes?": "2",
             "¿Qué carrera estudias actualmente y en qué universidad?": "Ingeniería de Sistemas en la Universidad de "
                                                                       "Cartagena " + "y más detalle " * 20}
    return {q.label: known[q.label] for q in questions if q.label in known}


def test_applies_with_the_questionnaire_answers_in_the_pages_format():
    s = FakeSession(questionnaire=QUESTIONNAIRE)
    result = magneto_apply.apply(None, URL, None, answerer, submit=True, session=s)
    assert result.status == "enviada", result
    (path, body), = s.posts
    assert path == "/jobs/apply" and body["jobId"] == 1143279 and body["suggestedByMatcher"] is False
    answers = {q["id"]: q for q in body["questionnaires"][0]["questions"]}
    assert body["questionnaires"][0]["id"] == 1003492
    assert answers[1] == {"id": 1, "type": 1, "answer": [13]}  # 2 años → «12 a 24 meses»
    assert answers[2]["type"] == 2 and len(answers[2]["openAnswer"]) <= 140  # abierta corta: máximo 140


def test_dry_run_and_unanswered_questions_never_send():
    s = FakeSession(questionnaire=QUESTIONNAIRE)
    assert magneto_apply.apply(None, URL, None, answerer, submit=False, session=s).status == "revisada"
    result = magneto_apply.apply(None, URL, None, lambda qs: {}, submit=True, session=s)
    assert result.status == "saltada" and "¿Cuántos meses de experiencia tienes?" in result.unanswered
    assert s.posts == []


def test_stops_where_the_page_would_ask_the_person():
    assert magneto_apply.apply(None, URL, None, answerer, submit=True, session=FakeSession(logged=False)).status == "sin_sesion"
    assert magneto_apply.apply(None, URL, None, answerer, submit=True,
                               session=FakeSession(job={"isApplied": True})).status == "ya_postulada"
    by_id = FakeSession(previous=[{"channel": "otra cuenta"}])
    assert magneto_apply.apply(None, URL, None, answerer, submit=True, session=by_id).status == "ya_postulada"
    assert by_id.posts == []  # nunca se cambia de cuenta ni se postula por encima
    assert magneto_apply.apply(None, URL, None, answerer, submit=True,
                               session=FakeSession(questionnaire=QUESTIONNAIRE, answered=True)).status == "ya_postulada"
    mine = FakeSession()
    mine.processes = [1143279]
    assert magneto_apply.apply(None, URL, None, answerer, submit=True, session=mine).status == "ya_postulada"
    assert mine.posts == []  # nunca dos veces
    rejected = magneto_apply.apply(None, URL, None, answerer, submit=True, session=FakeSession(accept=False))
    assert rejected.status == "error" and "Invalid body" in rejected.detail


def test_session_renewal_reads_only_the_session_cookie(monkeypatch):
    visited = []
    context = SimpleNamespace(cookies=lambda url: [{"name": "_ga", "value": "x"}, {"name": "access_token", "value": "tok"}])
    page = SimpleNamespace(goto=lambda url, **k: visited.append(url), context=context)
    monkeypatch.setattr(magneto_apply.time, "sleep", lambda s: None)
    s = magneto_apply.Session(page)
    assert s.renew() and s.token == "tok" and visited == [magneto_apply.LOGIN]
