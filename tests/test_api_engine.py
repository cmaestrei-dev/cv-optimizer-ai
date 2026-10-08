import json

import pytest

from core import capture
from core import llm as llm_module
from core.jobs import worker
from core.llm.client import LLMAuthError
from core.profile import service as profiles
from core.tracking import service as tracking
from tests.test_api import _h, _username
from tests.test_core_engine import _VACANCY
from tests.test_phase3 import JOBPOSTING_HTML

JOB = "https://www.linkedin.com/jobs/view/4012345678"


class RouterLLM:
    """IA de prueba: responde según el esquema pedido; las respuestas pueden depender del perfil real."""

    label = "fake:router"

    def __init__(self, username: str):
        self.username = username
        self.calls: list[str] = []
        self.fail_with: Exception | None = None

    def _ids(self):
        snap = profiles.snapshot(self.username)
        return snap, [a.id for e in snap.experiences for a in e.achievements]

    def complete(self, prompt, **kwargs):
        if self.fail_with:
            raise self.fail_with
        snap, ids = self._ids()
        for title, kind, build in [
            ("VacancyAnalysis", "vacante", lambda: _VACANCY),
            ("EvidenceMap", "evidencias", lambda: {
                "items": [{"requirement": 1, "level": "cubre", "evidence": [f"E{snap.education[0].id}"]},
                          {"requirement": 3, "level": "cubre", "evidence": [f"L{ids[0]}", f"H{snap.skills[0].id}"]}],
                "functions": [{"function": 1, "evidence": [f"L{ids[0]}"]}],
            }),
            ("Draft", "cv", lambda: {"summary": "Auxiliar Administrativa con experiencia en facturación",
                                     "bullets": [{"id": i, "text": snap.achievement(i)[1].text} for i in ids]}),
            ("ScreeningAnswers", "preguntas", lambda: {"answers": [
                {"question": "¿Maneja Excel?", "answer": "Sí, Excel con tablas dinámicas", "needs_you": False, "note": ""},
                {"question": "¿Aspiración salarial?", "answer": "", "needs_you": True, "note": "Depende de ti"}]}),
            ("_Note", "mensaje", lambda: {"text": "Hola, me postulo a la vacante de Auxiliar Administrativo en "
                                                  "Logística Andina. Adjunto mi CV."}),
            ("TitleSuggestions", "cargos", lambda: {"titles": ["Asistente de Facturación"]}),
            ("AchievementList", "brecha", lambda: {"achievements": ["Registré facturas de proveedores en SAP"]}),
        ]:
            if f'"title": "{title}"' in prompt:
                self.calls.append(kind)
                return json.dumps(build())
        raise AssertionError("Esquema no esperado")


@pytest.fixture
def ana(client, monkeypatch):
    username = _username(client, "ana")
    profiles.update_user(username, full_name="Ana Pérez", email="ana@example.com")
    profiles.add_experience(username, role="Auxiliar Administrativa", company="Nissan", period_text="2021 - Presente",
                            achievements=["Elaboré 180 facturas al mes en Excel", "Concilié cuentas por cobrar"])
    profiles.add_skill(username, "Excel", "Herramientas y software")
    profiles.add_education(username, title="Tecnóloga en Gestión Administrativa", institution="SENA")
    fake = RouterLLM(username)
    monkeypatch.setattr(llm_module, "get_llm", lambda task, overrides=None: fake)
    monkeypatch.setattr(capture, "_download", lambda url: (url, JOBPOSTING_HTML))
    return client, _h("ana"), fake


def _add(client, h, **body):
    return client.post("/vacancies", headers=h, json={"text": "Vacante de auxiliar administrativo...", **body})


class TestVacancies:
    def test_add_analyze_and_prepare(self, ana):
        client, h, fake = ana
        r = _add(client, h)
        assert r.status_code == 201 and r.json()["status"] == "por_revisar" and r.json()["match_score"] > 0
        app_id = r.json()["id"]
        assert [a["id"] for a in client.get("/applications?view=bandeja", headers=h).json()] == [app_id]

        analysis = client.get(f"/applications/{app_id}/analysis", headers=h).json()
        assert analysis["stale"] is False and analysis["vacancy"]["role"] == "Auxiliar Administrativo"
        reqs = analysis["match"]["requirements"]
        assert reqs[0]["level"] == "cubre" and reqs[0]["evidence"][0]["label"] == "Tecnóloga en Gestión Administrativa"
        assert reqs[2]["evidence"][0]["label"].startswith("«Elaboré 180 facturas")
        assert reqs[2]["evidence"][1]["label"] == "Habilidad: Excel"
        assert reqs[1]["level"] == "no"
        calls = len(fake.calls)
        client.get(f"/applications/{app_id}/analysis", headers=h)
        assert len(fake.calls) == calls  # consultar el análisis no llama a la IA

        r = client.post(f"/applications/{app_id}/prepare", headers=h)
        assert r.json()["status"] == "guardada" and fake.calls[-1] == "evidencias"

    def test_by_link_and_duplicates(self, ana):
        client, h, _ = ana
        r = client.post("/vacancies", headers=h, json={"url": JOB + "?trk=abc", "prepare": True})
        assert r.status_code == 201
        assert (r.json()["platform"], r.json()["url"], r.json()["status"]) == ("LinkedIn", JOB, "guardada")
        dup = client.post("/vacancies", headers=h, json={"url": "https://www.linkedin.com/jobs/search/?currentJobId=4012345678"})
        assert dup.status_code == 409 and dup.json()["application_id"] == r.json()["id"]
        assert client.post("/vacancies", headers=h, json={"url": "file:///etc/passwd"}).status_code == 422
        assert client.post("/vacancies", headers=h, json={}).status_code == 422

    def test_needs_experience_first(self, client):
        r = client.post("/vacancies", headers=_h("nueva"), json={"text": "Vacante"})
        assert r.status_code == 422 and "experiencia" in r.json()["detail"]

    def test_profile_changes_make_the_analysis_stale(self, ana):
        client, h, _ = ana
        app_id = _add(client, h).json()["id"]
        exp_id = client.get("/profile", headers=h).json()["experiences"][0]["id"]
        client.post(f"/experiences/{exp_id}/achievements", headers=h, json={"texts": ["Atendí proveedores"]})
        assert client.get(f"/applications/{app_id}/analysis", headers=h).json()["stale"] is True
        assert client.post(f"/applications/{app_id}/analysis", headers=h).json()["stale"] is False

    def test_manual_application_has_nothing_to_analyze(self, ana):
        client, h, _ = ana
        app_id = client.post("/applications", headers=h, json={"role": "Aux"}).json()["id"]
        assert client.get(f"/applications/{app_id}/analysis", headers=h).status_code == 422
        assert client.post(f"/applications/{app_id}/cvs", headers=h, json={}).status_code == 422


class TestCV:
    def test_generate_edit_and_send_the_exact_version(self, ana):
        client, h, _ = ana
        app_id = _add(client, h, prepare=True).json()["id"]
        job = client.post(f"/applications/{app_id}/cvs", headers=h, json={"focus": "facturación"})
        assert job.status_code == 202 and job.json()["status"] == "queued"
        assert worker.run_once() is True and worker.run_once() is False
        done = client.get(f"/jobs/{job.json()['id']}", headers=h).json()
        assert done["status"] == "done" and done["result"]["pages"] == 1 and done["result"]["reverted"] == []
        cv_id = done["result"]["cv_id"]
        assert done["result"]["filename"].startswith("Ana_P")

        cv = client.get(f"/cvs/{cv_id}", headers=h).json()
        assert cv["application_id"] == app_id and cv["intact"] and cv["document"]["summary"]
        assert tracking.get_application(_username(client, "ana"), app_id).status == "cv_generado"

        document = cv["document"]
        edits = {"summary": "Resumen editado a mano", "experiences": [
            {"bullets": [{"text": b["text"], "included": i == 0} for i, b in enumerate(e["bullets"])]}
            for e in document["experiences"]]}
        r = client.put(f"/cvs/{cv_id}/document", headers=h, json=edits)
        assert r.status_code == 201 and r.json()["cv_id"] != cv_id
        edited = client.get(f"/cvs/{r.json()['cv_id']}", headers=h).json()
        assert "Resumen editado a mano" in edited["markdown"] and edited["pdf_sha256"] != cv["pdf_sha256"]
        assert client.get(f"/cvs/{cv_id}", headers=h).json()["pdf_sha256"] == cv["pdf_sha256"]  # el original intacto

        bad = {"summary": "x", "experiences": [{"bullets": []}] * 3}
        assert client.put(f"/cvs/{cv_id}/document", headers=h, json=bad).status_code == 422
        sent = client.post(f"/applications/{app_id}/sent", headers=h, json={"cv_id": r.json()["cv_id"]})
        assert [c["id"] for c in sent.json()["cvs"] if c["sent_at"]] == [r.json()["cv_id"]]

        assert client.get(f"/cvs/{cv_id}", headers=_h("eve")).status_code == 404
        assert client.get(f"/jobs/{job.json()['id']}", headers=_h("eve")).status_code == 404

    def test_failed_job_has_a_friendly_message(self, ana):
        client, h, fake = ana
        app_id = _add(client, h).json()["id"]
        job_id = client.post(f"/applications/{app_id}/cvs", headers=h, json={}).json()["id"]
        fake.fail_with = LLMAuthError("La API key de Gemini no es válida. Revisa GEMINI_API_KEY en los secretos")
        worker.run_once()
        job = client.get(f"/jobs/{job_id}", headers=h).json()
        assert job["status"] == "failed" and "GEMINI_API_KEY" not in job["error"] and "IA no está disponible" in job["error"]


class TestHelpers:
    def test_screening_cover_and_gap(self, ana):
        client, h, _ = ana
        app_id = _add(client, h).json()["id"]
        answers = client.post(f"/applications/{app_id}/screening", headers=h,
                              json={"questions": ["¿Maneja Excel?", "¿Aspiración salarial?"]}).json()
        assert answers[0]["answer"] and answers[1]["needs_you"] is True
        cover = client.post(f"/applications/{app_id}/cover", headers=h).json()
        assert cover["fallback"] is False and "Adjunto mi CV" in cover["text"]

        exp_id = client.get("/profile", headers=h).json()["experiences"][0]["id"]
        r = client.post(f"/applications/{app_id}/gaps", headers=h, json={
            "requirement": 3, "experience_id": exp_id, "story": "registraba las facturas de proveedores en SAP"})
        assert r.json()["added"] == 1 and r.json()["candidates"][0]["suggested"] is True
        assert client.get(f"/applications/{app_id}/analysis", headers=h).json()["stale"] is True
        assert client.post(f"/applications/{app_id}/gaps", headers=h, json={
            "requirement": 99, "experience_id": exp_id, "story": "x"}).status_code == 422
        other = client.post("/experiences", headers=_h("eve"), json={"role": "X"}).json()["experiences"][0]["id"]
        assert client.post(f"/applications/{app_id}/gaps", headers=h, json={
            "requirement": 0, "experience_id": other, "story": "x"}).status_code == 422

    def test_discovery(self, ana):
        client, h, _ = ana
        titles = client.get("/discovery/titles", headers=h).json()["titles"]
        assert titles == ["Auxiliar Administrativa", "Asistente de Facturación"]
        links = client.get("/discovery/links", headers=h, params={"title": "Auxiliar", "city": "Bogotá"}).json()
        assert [link["portal"] for link in links] == ["LinkedIn", "Computrabajo", "elempleo", "Magneto"]


class TestInbox:
    def test_batch_is_processed_in_the_background(self, ana):
        client, h, _ = ana
        links = "\n".join([JOB, "https://www.linkedin.com/jobs/view/5012345678"] + [f"https://x.co/{i}" for i in range(12)])
        r = client.post("/inbox", headers=h, json={"links": links})
        assert r.status_code == 202 and len(r.json()["accepted"]) == 10 and r.json()["skipped"] == 4
        worker.run_once()
        job = client.get(f"/jobs/{r.json()['job']['id']}", headers=h).json()
        assert job["status"] == "done" and job["result"]["done"] == job["result"]["total"] == 10
        statuses = [x["status"] for x in job["result"]["results"]]
        assert statuses.count("agregada") == 10
        assert len(client.get("/applications?view=bandeja", headers=h).json()) == 10
        assert client.post("/inbox", headers=h, json={"links": "nada"}).status_code == 422


class TestQuota:
    def test_daily_limit_counts_only_successful_calls(self, ana, monkeypatch):
        client, h, fake = ana
        monkeypatch.setenv("AI_DAILY_CALLS", "3")
        app_id = _add(client, h).json()["id"]  # 2 llamadas
        assert client.get("/usage", headers=h).json() == {"used_today": 2, "daily_limit": 3}
        fake.fail_with = LLMAuthError("clave")
        assert client.post(f"/applications/{app_id}/analysis", headers=h).status_code == 503
        assert client.get("/usage", headers=h).json()["used_today"] == 2  # los errores del proveedor no cuentan
        fake.fail_with = None
        assert client.post(f"/applications/{app_id}/analysis", headers=h).status_code == 200  # 3 de 3
        r = client.post(f"/applications/{app_id}/cover", headers=h)
        assert r.status_code == 429 and "límite diario" in r.json()["detail"]
        assert client.get(f"/applications/{app_id}/analysis", headers=h).status_code == 200  # sin IA: no se limita
        assert client.get("/usage", headers=_h("eve")).json()["used_today"] == 0  # el cupo es por cuenta


class TestRobustness:
    def test_malformed_links_are_422_not_500(self, ana):
        client, h, _ = ana
        for url in ("https://[::1", "https://example.com:99999/x"):
            assert client.post("/vacancies", headers=h, json={"url": url}).status_code == 422, url
        assert client.post("/inbox", headers=h, json={"links": "https://[::1 y https://example.com:99999/x"}).status_code == 422
        assert client.patch("/applications/1", headers=h, json={"url": "https://[::1"}).status_code == 422

    def test_provider_down_is_503_with_a_safe_message(self, ana):
        from core.llm.client import LLMUnavailableError

        client, h, fake = ana
        fake.fail_with = LLMUnavailableError("Gemini HTTP 500: {secreto interno}")
        r = _add(client, h)
        assert r.status_code == 503 and "secreto" not in r.json()["detail"]

    def test_edits_count_against_the_daily_quota(self, ana, monkeypatch):
        client, h, _ = ana
        app_id = _add(client, h).json()["id"]
        client.post(f"/applications/{app_id}/cvs", headers=h, json={})
        worker.run_once()
        cv_id = client.get(f"/applications/{app_id}", headers=h).json()["cvs"][0]["id"]
        document = client.get(f"/cvs/{cv_id}", headers=h).json()["document"]
        edits = {"summary": "x", "experiences": [{"bullets": [{"text": b["text"]} for b in e["bullets"]]}
                                                 for e in document["experiences"]]}
        used = client.get("/usage", headers=h).json()["used_today"]
        assert client.put(f"/cvs/{cv_id}/document", headers=h, json=edits).status_code == 201
        assert client.get("/usage", headers=h).json()["used_today"] == used + 1
        monkeypatch.setenv("AI_DAILY_CALLS", str(used + 1))
        assert client.put(f"/cvs/{cv_id}/document", headers=h, json=edits).status_code == 429

    def test_editing_a_cv_whose_application_has_no_analysis(self, ana):
        """CV hecho en Streamlit y adjuntado a una postulación registrada a mano (sin análisis)."""
        import json as _json

        from core.engine.document import CVBullet, CVDocument, CVExperience

        client, h, _ = ana
        user = _username(client, "ana")
        app_id = tracking.create_application(user, role="Auxiliar", company="ACME", status="guardada")
        doc = CVDocument("es", "Resumen", [CVExperience("Aux", "Nissan", "2021", "", [CVBullet(1, "Facturé", "Facturé", 1.0)])], [], [])
        cv_id = tracking.attach_cv(user, app_id, pdf=b"%PDF", docx=b"PK", markdown="", language="es", filename="cv.pdf",
                                   document_json=_json.dumps(doc.to_dict()))
        r = client.put(f"/cvs/{cv_id}/document", headers=h, json={"summary": "Nuevo", "experiences": [{"bullets": [{"text": "Facturé"}]}]})
        assert r.status_code == 201 and "Auxiliar_ACME" in r.json()["filename"]


def test_api_refuses_postgres_without_identity_provider(monkeypatch):
    from fastapi.testclient import TestClient

    from api import main

    monkeypatch.setattr(main, "database_url", lambda: "postgresql+psycopg://produccion")
    monkeypatch.delenv("AUTH_JWKS_URL", raising=False)
    with pytest.raises(RuntimeError, match="AUTH_JWKS_URL"), TestClient(main.create_app()):
        pass


def test_rereading_the_vacancy_saves_it_with_its_evidence(ana):
    """Las evidencias apuntan a los requisitos por número: si Streamlit relee la vacante, se guardan juntas."""
    client, h, _ = ana
    user = _username(client, "ana")
    app_id = _add(client, h).json()["id"]
    reread = {**_VACANCY, "requirements": list(reversed(_VACANCY["requirements"]))}
    tracking.set_match(user, app_id, 50, "", "", analysis_json=json.dumps(reread))
    assert client.get(f"/applications/{app_id}", headers=h).json()["vacancy"]["requirements"][0]["text"] == "SAP Business One"


def test_cloud_run_refuses_to_start_without_postgres(monkeypatch):
    from fastapi.testclient import TestClient

    from api import main

    monkeypatch.setenv("K_SERVICE", "cv-optimizer")
    with pytest.raises(RuntimeError, match="DATABASE_URL"), TestClient(main.create_app()):
        pass
