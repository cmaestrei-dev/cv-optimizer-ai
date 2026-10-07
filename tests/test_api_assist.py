import json

import pytest
from weasyprint import HTML

from core import llm as llm_module
from core.db import session_scope
from core.jobs import worker
from core.jobs.models import Job
from core.profile import service as profiles
from tests.test_api import _h, _username

CV_HTML = """<h1>Diana Rojas</h1><p>diana@example.com · 300 123 4567</p>
<h2>Experiencia</h2><h3>Auxiliar Administrativa — Nissan</h3><p>Marzo 2023 - Presente</p>
<ul><li>Elaboré 120 facturas al mes en SAP</li><li>Atendí a clientes del taller</li></ul>
<h2>Aptitudes principales</h2><p>Excel, Atención al cliente</p>
<h2>Educación</h2><p>Tecnóloga en Gestión Administrativa — SENA</p>"""


def _pdf(html: str) -> bytes:
    return HTML(string=html).write_pdf()


class AssistLLM:
    label = "fake:assist"

    def __init__(self):
        self.calls: list[str] = []

    def complete(self, prompt, **kwargs):
        for title, kind, answer in [
            ("ImportedCV", "importar", {
                "full_name": "Diana Rojas", "email": "diana@example.com", "phone": "300 123 4567",
                "linkedin_url": "www.linkedin.com/in/diana-rojas",  # así viene en el PDF de LinkedIn
                "experiences": [{"role": "Auxiliar Administrativa", "company": "Nissan", "period_text": "Marzo 2023 - Presente",
                                 "achievements": ["Elaboré 120 facturas al mes en SAP", "Atendí a clientes del taller",
                                                  "Reduje la cartera un 40%"]}],  # inventado: no está en el PDF
                "skills": [{"name": "Excel", "category": "Herramientas y software"},
                           {"name": "Power BI", "category": "Herramientas y software"}],  # no está en el PDF
                "education": [{"title": "Tecnóloga en Gestión Administrativa", "institution": "SENA"}],
            }),
            ("AchievementList", "logros", {"achievements": ["Radiqué las facturas de vehículos en el DMS",
                                                            "Gestioné 300 pedidos diarios"]}),  # "300" inventado
            ("TaskList", "tareas", {"tasks": ["Elaboré cotizaciones", "Archivé documentos"]}),
            ("QuestionSet", "preguntas", {"questions": [{"achievement_id": None, "question": "¿Cuántas facturas?",
                                                         "example": "Unas 50"}]}),
            ("ProposalSet", "propuestas", {"proposals": [{"achievement_id": None, "text": "Archivé 200 contratos al mes"},
                                                         {"achievement_id": None, "text": "Archivé 999 contratos"}]}),
        ]:
            if f'"title": "{title}"' in prompt:
                self.calls.append(kind)
                return json.dumps(answer)
        raise AssertionError("Esquema no esperado")


@pytest.fixture
def diana(client, monkeypatch):
    fake = AssistLLM()
    monkeypatch.setattr(llm_module, "get_llm", lambda task, overrides=None: fake)
    _username(client, "diana")
    return client, _h("diana"), fake


def _upload(client, h, data: bytes, name="cv.pdf"):
    return client.post("/profile/import", headers=h, files={"file": (name, data, "application/pdf")})


class TestImport:
    def test_import_verifies_against_the_pdf_and_applies_once(self, diana):
        client, h, _ = diana
        r = _upload(client, h, _pdf(CV_HTML))
        assert r.status_code == 202 and r.json()["kind"] == "importar"
        job_id = r.json()["id"]
        worker.run_once()
        job = client.get(f"/jobs/{job_id}", headers=h).json()
        assert job["status"] == "done"
        result = job["result"]
        assert result["data"]["experiences"][0]["achievements"] == ["Elaboré 120 facturas al mes en SAP",
                                                                    "Atendí a clientes del taller"]
        assert [s["name"] for s in result["data"]["skills"]] == ["Excel"]
        assert any("40" in d for d in result["discarded"]) and any("Power BI" in d for d in result["discarded"])
        with session_scope() as s:  # el texto del CV no se queda en la cola
            assert s.get(Job, job_id).payload == "{}"

        assert client.post(f"/profile/import/{job_id}/apply", headers=h, json={"experiences": [7]}).status_code == 422
        assert client.post(f"/profile/import/{job_id}/apply", headers=_h("eve"), json={}).status_code == 404
        r = client.post(f"/profile/import/{job_id}/apply", headers=h, json={
            "experiences": result["new_experiences"], "skills": result["new_skills"], "education": result["new_education"]})
        assert r.status_code == 200 and r.json()["counts"] == {"experiencias": 1, "logros": 2, "habilidades": 1, "estudios": 1}
        profile = r.json()["profile"]
        assert profile["contact"]["full_name"] == "Diana Rojas" and profile["experiences"][0]["role"] == "Auxiliar Administrativa"
        assert profile["contact"]["linkedin_url"] == "https://www.linkedin.com/in/diana-rojas"
        again = client.post(f"/profile/import/{job_id}/apply", headers=h, json={"experiences": result["new_experiences"]})
        assert again.status_code == 422 and "Ya guardaste" in again.json()["detail"]
        assert len(client.get("/profile", headers=h).json()["experiences"]) == 1
        # Tras aplicar, lo leído (nombre, contacto, historial) ya no se guarda en el trabajo
        assert client.get(f"/jobs/{job_id}", headers=h).json()["result"] == {"applied": True, "counts": r.json()["counts"]}

        # Reimportar el mismo CV: la experiencia ya existe y se marca repetida
        worker_job = _upload(client, h, _pdf(CV_HTML)).json()["id"]
        worker.run_once()
        second = client.get(f"/jobs/{worker_job}", headers=h).json()["result"]
        assert second["new_experiences"] == [] and second["duplicate_experiences"] == [0] and second["new_skills"] == []

    def test_two_readings_or_repeated_indices_never_duplicate(self, diana):
        client, h, _ = diana
        first, second = _upload(client, h, _pdf(CV_HTML)).json()["id"], _upload(client, h, _pdf(CV_HTML)).json()["id"]
        worker.run_once()
        worker.run_once()
        body = {"experiences": [0, 0, 0], "skills": [0, 0], "education": [0, 0]}
        assert client.post(f"/profile/import/{first}/apply", headers=h, json=body).json()["counts"] == {
            "experiencias": 1, "logros": 2, "habilidades": 1, "estudios": 1}
        # La segunda lectura se hizo antes de guardar la primera: su plan ofrece lo mismo como nuevo,
        # pero al guardar se compara con el perfil actual
        assert client.post(f"/profile/import/{second}/apply", headers=h, json=body).json()["counts"] == {
            "experiencias": 0, "logros": 0, "habilidades": 0, "estudios": 0}
        profile = client.get("/profile", headers=h).json()
        assert (len(profile["experiences"]), len(profile["skills"]), len(profile["education"])) == (1, 1, 1)

    def test_rejects_non_pdfs_and_pdfs_without_text(self, diana):
        client, h, fake = diana
        assert _upload(client, h, b"hola, no soy un PDF").status_code == 422
        r = _upload(client, h, _pdf("<p> </p>"))
        assert r.status_code == 422 and "escaneo" in r.json()["detail"]
        assert _upload(client, h, b"%PDF" + b"0" * 5_000_001).status_code == 422
        assert fake.calls == []

    def test_apply_before_the_reading_ends(self, diana):
        client, h, _ = diana
        job_id = _upload(client, h, _pdf(CV_HTML)).json()["id"]
        r = client.post(f"/profile/import/{job_id}/apply", headers=h, json={})
        assert r.status_code == 422 and "todavía" in r.json()["detail"]


class TestCompletion:
    @pytest.fixture
    def exp(self, diana):
        client, h, fake = diana
        exp = client.post("/experiences", headers=h, json={
            "role": "Auxiliar Administrativa", "company": "Nissan", "achievements": ["Facturé ventas"]}).json()["experiences"][0]
        return client, h, fake, exp["id"]

    def test_free_text_and_typical_tasks_are_verified_not_saved(self, exp):
        client, h, fake, exp_id = exp
        r = client.post(f"/experiences/{exp_id}/suggestions/from-text", headers=h,
                        json={"text": "radicaba las facturas de los carros en el DMS y llevaba los pedidos"})
        candidates = r.json()
        assert candidates[0]["suggested"] is True and candidates[1]["suggested"] is False and candidates[1]["problems"]
        assert len(client.get("/profile", headers=h).json()["experiences"][0]["achievements"]) == 1  # nada guardado

        assert client.post(f"/experiences/{exp_id}/suggestions/tasks", headers=h).json()["tasks"][0] == "Elaboré cotizaciones"
        calls = len(fake.calls)
        plain = client.post(f"/experiences/{exp_id}/suggestions/from-tasks", headers=h,
                            json={"items": [{"task": "Elaboré cotizaciones"}]}).json()
        assert [c["text"] for c in plain] == ["Elaboré cotizaciones"] and len(fake.calls) == calls  # sin detalle, sin IA

    def test_interview_accepts_only_what_the_person_chooses(self, exp):
        client, h, _, exp_id = exp
        questions = client.post(f"/experiences/{exp_id}/interview/questions", headers=h).json()
        assert questions[0]["question"] == "¿Cuántas facturas?"
        assert client.post(f"/experiences/{exp_id}/interview/proposals", headers=h,
                           json={"answers": [{"question": "x", "answer": ""}]}).status_code == 422
        proposals = client.post(f"/experiences/{exp_id}/interview/proposals", headers=h, json={"answers": [
            {"question": "¿Archivabas?", "answer": "archivaba unos 200 contratos al mes"}]}).json()
        ok = [p for p in proposals if not p["problems"]]
        assert [p["proposed"] for p in ok] == ["Archivé 200 contratos al mes"] and len(proposals) == 2
        answers = ["archivaba unos 200 contratos al mes"]
        # El servidor verifica de nuevo: lo que no sale de las respuestas no se guarda aunque el cliente lo envíe
        bad = client.post(f"/experiences/{exp_id}/interview/accept", headers=h,
                          json={"accepted": [{"text": "Archivé 999 contratos"}], "answers": answers})
        assert bad.status_code == 422 and "999" in bad.json()["detail"]
        gone = client.post(f"/experiences/{exp_id}/interview/accept", headers=h,
                           json={"accepted": [{"achievement_id": 999999, "text": ok[0]["proposed"]}], "answers": answers})
        assert gone.status_code == 422
        r = client.post(f"/experiences/{exp_id}/interview/accept", headers=h,
                        json={"accepted": [{"achievement_id": None, "text": ok[0]["proposed"]}], "answers": answers})
        assert [a["text"] for a in r.json()["experiences"][0]["achievements"]] == ["Facturé ventas", "Archivé 200 contratos al mes"]

    def test_other_accounts_experiences_are_not_reachable(self, exp):
        client, _, fake, exp_id = exp
        eve = _h("eve")
        for path, body in [("suggestions/from-text", {"text": "x"}), ("suggestions/tasks", None),
                           ("interview/questions", None),
                           ("interview/accept", {"accepted": [{"text": "hack"}], "answers": ["hack"]})]:
            assert client.post(f"/experiences/{exp_id}/{path}", headers=eve, json=body).status_code == 404, path
        assert fake.calls == []
        assert profiles.list_usernames() == []


def test_failed_pdfs_never_stay_on_disk(tmp_path, monkeypatch):
    import tempfile

    from utils.pdf_extractor import extract_text_from_pdf

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert not extract_text_from_pdf(b"%PDF-1.4\n" + b"basura" * 100)
    assert extract_text_from_pdf(_pdf(CV_HTML))
    assert list(tmp_path.iterdir()) == []


def test_body_size_limit(diana):
    client, h, _ = diana
    big = b"%PDF" + b"0" * 6_100_000
    r = client.post("/profile/import", headers=h, files={"file": ("cv.pdf", big, "application/pdf")})
    assert r.status_code == 413
    r = client.post("/profile/import", files={"file": ("cv.pdf", big, "application/pdf")})  # sin token: igual se corta
    assert r.status_code == 413

    def chunks():
        for _ in range(7):
            yield b"0" * 1_000_000

    chunked = client.post("/profile/import", headers={**h, "Content-Type": "multipart/form-data; boundary=x"}, content=chunks())
    assert chunked.status_code in (400, 413)


def test_unsafe_stored_links_are_not_returned(diana):
    client, h, _ = diana
    profiles.update_user(_username(client, "diana"), linkedin_url="javascript:alert(1)", github_url="github.com/diana")
    contact = client.get("/me", headers=h).json()["contact"]
    assert contact["linkedin_url"] == "" and contact["github_url"] == "https://github.com/diana"


def test_old_jobs_are_purged(diana):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from core.jobs import service as jobs

    client, h, _ = diana
    job_id = _upload(client, h, _pdf(CV_HTML)).json()["id"]
    worker.run_once()
    assert jobs.purge() == 0
    with session_scope() as s:
        s.execute(update(Job).where(Job.id == job_id).values(created_at=datetime.now(UTC) - timedelta(days=3)))
    assert jobs.purge() == 1  # las lecturas de CV duran 2 días
    assert client.get(f"/jobs/{job_id}", headers=h).status_code == 404
