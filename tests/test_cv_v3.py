"""Hojas de vida v3 (pedido del dueño, 2026-11-28): 4 o 5 viñetas por experiencia en una página, palabras clave
honestas (línea «Competencias clave» + cobertura, sin texto oculto) y redacción que no suene a IA."""

import json

from core.engine.keywords import coverage, key_skills
from core.engine.matching import EvidenceMap, compute_match
from core.engine.pipeline import analyze, generate
from core.engine.selection import Budget, select_content
from core.engine.writing import style_problems, write_cv
from core.profile.periods import parse_period
from core.profile.snapshot import AchievementSnap as A
from core.profile.snapshot import EducationSnap as Ed
from core.profile.snapshot import ExperienceSnap as X
from core.profile.snapshot import ProfileSnapshot
from core.profile.snapshot import SkillSnap as S
from core.vacancy import VacancyAnalysis
from models import UserProfile
from tests.test_core_engine import _EVIDENCE, _VACANCY, TODAY, FakeLLM, _match, _profile


def _dev() -> ProfileSnapshot:
    return ProfileSnapshot(
        username="camilo",
        experiences=(
            X(1, "Desarrollador Fullstack", "Karta", "Enero 2025 - Presente", parse_period("Enero 2025 - Presente"), "", "", (
                A(11, "Construí una API REST en FastAPI con 70 endpoints"),
                A(12, "Integré OpenStreetMap para buscar direcciones"),
            )),
        ),
        skills=(S(1, "React", "Frameworks / Librerías"), S(2, "Python", "Lenguajes de Programación"),
                S(3, "JavaScript", "Lenguajes de Programación"), S(4, "Node.js", "Frameworks / Librerías")),
        education=(Ed(1, "Ingeniería de Sistemas", "Universidad de Cartagena", "2022 - 2027", parse_period("2022 - 2027")),),
    )


def _vacancy(keywords: list[str]) -> VacancyAnalysis:
    return VacancyAnalysis.model_validate({**_VACANCY, "keywords": keywords})


class TestKeywords:
    def test_only_what_the_profile_backs_goes_in_the_line(self):
        vacancy = _vacancy(["ReactJS", "Python", "Kubernetes", "API REST", "Java", "NodeJS", "Trabajo en equipo", "python"])
        # «ReactJS» es React y «NodeJS» es Node.js; «Java» NO es JavaScript; nada de lo que no tiene
        assert key_skills(vacancy, _dev()) == ["ReactJS", "Python", "API REST", "NodeJS"]

    def test_the_line_stays_short(self):
        many = [f"Habilidad número {i}" for i in range(40)]
        profile = ProfileSnapshot("x", skills=tuple(S(i, name, "Otros") for i, name in enumerate(many)))
        line = key_skills(_vacancy(many), profile)
        assert len(line) <= 12 and len(" · ".join(line)) <= 200

    def test_coverage_says_what_is_missing(self):
        vacancy = _vacancy(["Python", "FastAPI", "React", "Kubernetes"])
        report = coverage("Construí una API REST en FastAPI con Python", vacancy, _dev())
        assert report.present == ["Python", "FastAPI"] and report.missing_owned == ["React"]
        assert report.missing == ["Kubernetes"] and report.coverage == 50
        assert report.to_dict()["total"] == 4
        assert coverage("texto", _vacancy([]), _dev()).coverage == 100


class TestStyle:
    def test_ai_tells_are_caught_only_when_the_user_did_not_write_them(self):
        original = "Desarrollé la API de reservas"
        assert any("gerundio" in p for p in style_problems("Desarrollé la API de reservas, garantizando su calidad", original))
        assert any("muletillas" in p for p in style_problems("Desarrollé de manera eficiente la API de reservas", original))
        assert any("rayas" in p for p in style_problems("Desarrollé la API — reservas y pagos", original))
        assert style_problems("Desarrollé la API de reservas para el sitio web", original) == []
        assert style_problems("Impulsé la venta en línea", "Impulsé la venta en línea") == []  # lo escribió la persona
        assert style_problems("Built the API, ensuring uptime", "Built the API", "en")  # en inglés, la muletilla


class TestSelection:
    def test_four_bullets_per_experience_and_five_at_most(self):
        exp = lambda i, n: X(i, f"Cargo {i}", "Empresa", "2024 - 2025", parse_period("2024 - 2025"), "", "",  # noqa: E731
                             tuple(A(i * 10 + j, f"Logro {i}-{j} sobre tema {j} distinto") for j in range(n)))
        profile = ProfileSnapshot("x", experiences=(exp(1, 7), exp(2, 6), exp(3, 2)))
        vacancy = _vacancy(["tema"])
        match = compute_match(vacancy, EvidenceMap(), profile, today=TODAY)
        sel = select_content(profile, match, vacancy)
        counts = [len(s.achievements) for s in sel.experiences]
        assert counts[2] == 2 and all(4 <= c <= 5 for c in counts[:2])  # o todas las que tenga

    def test_two_bullets_that_say_the_same_are_avoided(self):
        profile = ProfileSnapshot("x", experiences=(X(1, "Auxiliar", "Autos", "2024 - 2025", parse_period("2024 - 2025"), "", "", (
            A(11, "Elaboré la facturación de 180 facturas al mes en Excel"),
            A(12, "Elaboré la facturación mensual de 180 facturas en Excel"),
            A(13, "Concilié cuentas por cobrar con cartera"),
            A(14, "Organicé el archivo de contratos"),
        )),))
        vacancy = _vacancy(["facturación", "Excel", "cartera"])
        match = compute_match(vacancy, EvidenceMap(), profile, today=TODAY)
        sel = select_content(profile, match, vacancy, Budget(min_bullets_per_experience=2, max_bullets_per_experience=2))
        assert [a.id for a in sel.experiences[0].achievements] == [11, 13]


class TestWriting:
    NATURAL = ("Asistente Administrativa con 7 años de experiencia en facturación y Excel, formada como Tecnóloga en Gestión "
               "Administrativa en el SENA. Llevo la facturación del concesionario y atiendo a clientes y proveedores con "
               "orden y buen trato, lo que puedo aportar desde el primer día en el área.")

    def _run(self, responses):
        vacancy, m = _match()
        sel = select_content(_profile(), m, vacancy, Budget(max_bullets=3, min_bullets=1))
        ids = [a.id for s in sel.experiences for a in s.achievements]
        llm = FakeLLM(*responses(ids))
        return write_cv(llm, vacancy, sel, m, _profile()), ids, llm

    def test_ai_sounding_bullet_is_rewritten_once_or_left_as_the_user_wrote_it(self):
        text = lambda aid: _profile().achievement(aid)[1].text  # noqa: E731

        def responses(ids):
            first, second, third = ids
            return ({"summary": self.NATURAL, "bullets": [
                        {"id": first, "text": "Elaboré 180 facturas al mes, garantizando la calidad"},
                        {"id": second, "text": f"{text(second)} de manera eficiente"},
                        {"id": third, "text": f"Caja: {text(third).lower()}"}]},
                    {"bullets": [{"id": first, "text": "Elaboré la facturación de 180 facturas al mes"},
                                 {"id": second, "text": f"{text(second)}, optimizando tiempos"}]})
        written, (first, second, third), llm = self._run(responses)
        assert written.bullets[first] == "Elaboré la facturación de 180 facturas al mes"  # corregida
        assert written.bullets[second] == text(second)  # siguió sonando a IA: la del usuario
        assert written.bullets[third] == text(third)  # sin la etiqueta que dejó la IA
        assert written.restyled.keys() == {second} and not written.reverted  # no inventó: no cuenta como inventado
        assert "garantizando" in llm.prompts[1] and "gerundio" in llm.prompts[1] and len(llm.prompts) == 2

    def test_a_long_clean_bullet_is_kept_if_the_shorter_one_sounds_worse(self):
        long = "Elaboré la facturación de 180 facturas al mes " + "para los clientes del concesionario y sus sedes " * 2
        def responses(ids):
            return ({"summary": self.NATURAL, "bullets": [{"id": ids[0], "text": long}] +
                     [{"id": i, "text": _profile().achievement(i)[1].text} for i in ids[1:]]},
                    {"bullets": [{"id": ids[0], "text": "Elaboré 180 facturas al mes, asegurando su entrega"}]})
        written, ids, llm = self._run(responses)
        assert len(long.strip()) > 105 and "déjala en una línea" in llm.prompts[1]
        assert written.bullets[ids[0]] == long.strip() and not written.restyled and not written.reverted


def test_generate_puts_the_keywords_and_measures_coverage():
    profile = _profile()
    analysis = analyze(FakeLLM(_VACANCY, _EVIDENCE), profile, text="vacante")
    ids = [a.id for e in profile.experiences for a in e.achievements]
    cv = generate(FakeLLM({"summary": TestWriting.NATURAL,
                           "bullets": [{"id": i, "text": profile.achievement(i)[1].text} for i in ids]}),
                  profile, UserProfile(username="laura", full_name="Laura"), analysis)
    assert cv.document.key_skills == ["Facturación", "Excel", "Cartera"]
    assert "**Competencias clave:** Facturación · Excel · Cartera" in cv.document.to_markdown()
    assert cv.keywords.coverage == 100 and cv.output.pages == 1
    assert json.loads(json.dumps(cv.keywords.to_dict()))["present"] == ["facturación", "Excel", "cartera"]


def test_the_bot_reports_coverage_and_what_vacancies_ask_most(tmp_path, monkeypatch):
    from runner import __main__ as cli
    from runner.api import Api
    from runner.state import State

    api = Api("http://127.0.0.1:9", "t")
    monkeypatch.setattr(api, "post", lambda path, body=None: {"id": 5, "status": "done",
                                                              "result": {"keywords": {"coverage": 75, "total": 4}}})
    monkeypatch.setattr(api, "get", lambda path: {"cvs": [{"id": 31, "filename": "cv.pdf"}]})
    assert api.make_cv(9) == {"id": 31, "filename": "cv.pdf", "keywords": {"coverage": 75, "total": 4}}

    state = State(tmp_path / "estado.json")
    state.mark("li:1", "preparada", claves=80, faltan=["Java", "Docker"])
    state.mark("li:2", "preparada", claves=60, faltan=["java"])
    state.mark("li:3", "preparada")  # sin CV
    text = cli._keywords_today(state)
    assert "70 % en promedio" in text and "Java (2), Docker (1)" in text
    assert cli._keywords_today(State(tmp_path / "otro.json")) == ""


def test_what_the_repair_left_is_tidied_without_ai():
    from core.engine.writing import tidy

    assert tidy("Gestioné órdenes de compra, optimizando los tiempos del área", "Gestioné órdenes de compra") == (
        "Gestioné órdenes de compra")
    assert tidy("Gestioné órdenes, reduciendo los errores un 30 %", "Gestioné órdenes") == (
        "Gestioné órdenes, reduciendo los errores un 30 %")  # con cifra: vale más que la forma
    assert tidy("Integré Wompi — webhooks firmados", "Integré Wompi con webhooks firmados") == "Integré Wompi, webhooks firmados"
    assert tidy("Estudiante de sistemas. Domino Python y React.", "") == "Estudiante de sistemas. Manejo Python y React."
    assert tidy("Built it, ensuring uptime", "", "en") == "Built it, ensuring uptime"


def test_a_degree_is_not_a_key_skill_but_counts_for_coverage():
    vacancy = _vacancy(["Ingeniería de Sistemas", "Python"])
    assert key_skills(vacancy, _dev()) == ["Python"]
    assert coverage("Ingeniería de Sistemas · Python", vacancy, _dev()).coverage == 100


def test_a_topic_in_a_role_or_certificate_is_a_key_skill():
    # Caso real (vacante de seguridad, 2026-11-28): la línea salía vacía porque «Ciberseguridad» solo estaba en el cargo.
    profile = ProfileSnapshot("x", experiences=(X(1, "Analista Ciberseguridad Jr", "Equimat", "2026", parse_period("2026"), "", "",
                                                  (A(11, "Contuve una intrusión"),)),),
                              education=(Ed(1, "Ingeniería de Sistemas", "UdeC", "2022 - 2027", parse_period("2022 - 2027")),))
    assert key_skills(_vacancy(["ciberseguridad", "Ingeniería de Sistemas", "Analista Ciberseguridad Jr"]), profile) == [
        "Ciberseguridad"]
