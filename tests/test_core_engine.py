import json
from datetime import date

import pytest

from core.engine.document import (
    CVBullet,
    CVDocument,
    CVExperience,
    build_document,
    render,
    render_html,
)
from core.engine.matching import EvidenceMap, compute_match
from core.engine.pipeline import analyze, generate
from core.engine.selection import Budget, select_content
from core.engine.verification import unsupported
from core.engine.writing import write_cv
from core.profile.periods import parse_period
from core.profile.snapshot import AchievementSnap as A
from core.profile.snapshot import EducationSnap as Ed
from core.profile.snapshot import ExperienceSnap as X
from core.profile.snapshot import ProfileSnapshot
from core.profile.snapshot import SkillSnap as S
from core.vacancy import VacancyAnalysis
from models import UserProfile

TODAY = date(2026, 10, 1)


class FakeLLM:
    """Devuelve respuestas en cola y guarda los prompts recibidos."""

    label = "fake:model"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        response = self.responses.pop(0)
        return response if isinstance(response, str) else json.dumps(response)


def _profile() -> ProfileSnapshot:
    return ProfileSnapshot(
        username="laura",
        experiences=(
            X(1, "Asistente Administrativa", "Autos del Caribe", "Marzo 2023 - Presente",
              parse_period("Marzo 2023 - Presente"), "Colombia", "Presencial", (
                  A(11, "Elaboré la facturación de 180 facturas al mes"),
                  A(12, "Concilié cuentas por cobrar con cartera"),
                  A(13, "Organicé el archivo de contratos"),
                  A(14, "Atendí clientes en recepción"),
              )),
            X(2, "Auxiliar Administrativa", "TiendaYa", "Enero 2021 - Febrero 2023",
              parse_period("Enero 2021 - Febrero 2023"), "Colombia", "Híbrido", (
                  A(21, "Gestioné órdenes de compra"),
                  A(22, "Apoyé el pago a proveedores"),
              )),
            X(3, "Cajera", "El Ahorro", "2019 - 2020", parse_period("2019 - 2020"), "", "", (
                A(31, "Manejé caja y cuadre diario"),
            )),
        ),
        skills=(S(1, "Excel", "Herramientas y software"), S(2, "Facturación", "Conocimientos del área"),
                S(3, "Atención al cliente", "Habilidades blandas")),
        education=(Ed(1, "Tecnóloga en Gestión Administrativa", "SENA", "2018 - 2020", parse_period("2018 - 2020")),
                   Ed(2, "Bachiller", "Colegio", "2017", parse_period("2017"))),
    )


_VACANCY = {
    "is_vacancy": True, "role": "Auxiliar Administrativo", "company": "Logística Andina",
    "language": "es", "area": "Administrativa", "min_years_experience": 2,
    "requirements": [
        {"text": "Tecnólogo en gestión administrativa", "kind": "obligatorio", "category": "formacion"},
        {"text": "Mínimo 10 años de experiencia en facturación", "kind": "obligatorio", "category": "experiencia"},
        {"text": "Excel intermedio", "kind": "obligatorio", "category": "herramienta"},
        {"text": "SAP Business One", "kind": "deseable", "category": "herramienta"},
    ],
    "responsibilities": ["Elaborar facturas", "Atender proveedores"],
    "keywords": ["facturación", "Excel", "cartera"],
}
_EVIDENCE = {
    "items": [
        {"requirement": 1, "level": "cubre", "evidence": ["E1"]},
        {"requirement": 2, "level": "cubre", "evidence": ["L11"]},
        {"requirement": 3, "level": "cubre", "evidence": [" h1", "L999"]},
        {"requirement": 4, "level": "parcial", "evidence": ["H404"]},
    ],
    "functions": [{"function": 1, "evidence": ["L11"]}, {"function": 2, "evidence": ["L22"]}, {"function": 9, "evidence": ["L13"]}],
}


def _match(profile=None):
    profile = profile or _profile()
    vacancy = VacancyAnalysis.model_validate(_VACANCY)
    return vacancy, compute_match(vacancy, EvidenceMap.model_validate(_EVIDENCE), profile, today=TODAY)


class TestSnapshot:
    def test_overlapping_periods_are_not_double_counted(self):
        p = ProfileSnapshot("x", experiences=(
            X(1, "A", "", "2020 - 2021", parse_period("2020 - 2021")),
            X(2, "B", "", "Junio 2021 - Diciembre 2021", parse_period("Junio 2021 - Diciembre 2021")),
        ))
        assert p.total_experience_months(TODAY) == 24


class TestMatching:
    def test_score_and_validation(self):
        _, m = _match()
        levels = [r.level for r in m.requirements]
        # R2 baja a parcial (7.8 años < 10), R4 a "no" porque su única evidencia no existe.
        assert levels == ["cubre", "parcial", "cubre", "no"]
        assert "10 años" in m.requirements[1].note
        assert m.requirements[2].evidence == ["H1"]  # L999 descartado
        assert m.score == round(100 * (1 + 0.5 + 1) / 3.4)
        assert m.meets_years is True and m.experience_years == 7.8  # 44 + 26 + 24 meses

    def test_functions_add_relevance_not_score(self):
        _, m = _match()
        assert m.achievement_weights[22] == pytest.approx(0.3)
        assert 13 not in m.achievement_weights  # función inexistente (F9) ignorada
        assert m.cited_skills == {1} and m.cited_education == {1}


class TestSelection:
    def test_most_recent_and_one_bullet_per_experience(self):
        vacancy, m = _match()
        sel = select_content(_profile(), m, vacancy)
        assert [s.experience.id for s in sel.experiences][0] == 1
        assert all(s.achievements for s in sel.experiences)
        ids = [a.id for s in sel.experiences for a in s.achievements]
        assert 11 in ids and 22 in ids
        assert ids == sorted(ids, key=lambda i: (i // 10, i))  # orden original dentro de cada cargo

    def test_experience_without_achievements_does_not_take_a_slot(self):
        base = _profile()
        empty = X(9, "Nuevo cargo", "Recién", "Septiembre 2026 - Presente", parse_period("Septiembre 2026 - Presente"))
        profile = ProfileSnapshot("laura", experiences=(empty, *base.experiences), skills=base.skills)
        vacancy, m = _match(profile)
        sel = select_content(profile, m, vacancy, Budget(max_experiences=2))
        assert [s.experience.id for s in sel.experiences] == [1, 2]

    def test_respects_budget(self):
        vacancy, m = _match()
        sel = select_content(_profile(), m, vacancy, Budget(max_bullets=3, min_bullets=1))
        assert sum(len(s.achievements) for s in sel.experiences) <= 3

    def test_skills_and_education_priority(self):
        vacancy, m = _match()
        sel = select_content(_profile(), m, vacancy, Budget(max_education=1))
        assert sel.skill_groups[0][1][0].name == "Excel"  # citada como evidencia
        assert [e.id for e in sel.education] == [1]


class TestVerification:
    SRC = "Gestioné la facturación y cartera de 120 clientes en Excel para Logística Andina."

    @pytest.mark.parametrize("text", [
        "Gestioné cuentas por cobrar y facturación de 120 clientes usando Excel",
        "Elaboré facturas para Logística Andina con Excel",
    ])
    def test_supported(self, text):
        assert unsupported(text, self.SRC) == []

    @pytest.mark.parametrize(("text", "problem"), [
        ("Gestioné la facturación de 120 clientes en SAP", "SAP"),
        ("Gestioné la facturación de 150 clientes", "150"),
        ("Reduje errores de facturación un 30%", "30"),
        ("Coordiné Facturación Electrónica para 120 clientes", "Electrónica"),
    ])
    def test_unsupported(self, text, problem):
        assert any(problem in p for p in unsupported(text, self.SRC))

    def test_translation_mode_only_checks_acronyms_and_numbers(self):
        assert unsupported("Managed invoicing for 120 clients using Excel", self.SRC, strict=False) == []
        assert unsupported("Managed invoicing in SAP", self.SRC, strict=False) == ["término sin respaldo: SAP"]


class TestWriting:
    def _selection(self):
        vacancy, m = _match()
        return vacancy, m, select_content(_profile(), m, vacancy, Budget(max_bullets=2, min_bullets=1))

    def test_invented_data_is_repaired_or_reverted(self):
        vacancy, m, sel = self._selection()
        ids = [a.id for s in sel.experiences for a in s.achievements]
        first, second = ids[0], ids[1]
        llm = FakeLLM(
            {"summary": "Auxiliar Administrativo con 7 años de experiencia en facturación y Excel",
             "bullets": [{"id": first, "text": "Elaboré 180 facturas al mes en SAP"},
                         {"id": second, "text": "Texto correcto."}]},
            {"bullets": [{"id": first, "text": "Elaboré 180 facturas en SAP otra vez"}]},
        )
        written = write_cv(llm, vacancy, sel, m, _profile())
        assert written.bullets[first] == _profile().achievement(first)[1].text.rstrip(".")
        assert first in written.reverted and second not in written.reverted
        assert written.bullets[second] == "Texto correcto"
        assert written.summary.startswith("Auxiliar Administrativo con 7")
        assert "180 facturas" in llm.prompts[0] and len(llm.prompts) == 2

    def test_summary_with_invented_tool_falls_back(self):
        vacancy, m, sel = self._selection()
        ids = [a.id for s in sel.experiences for a in s.achievements]
        llm = FakeLLM({"summary": "Experta en SAP y Power BI", "bullets": [{"id": i, "text": "Hice algo"} for i in ids]})
        written = write_cv(llm, vacancy, sel, m, _profile())
        assert written.summary_problems and "SAP" not in written.summary
        assert written.summary.startswith("Auxiliar Administrativo: 7 años")


class TestDocument:
    def test_html_escapes_everything(self):
        doc = CVDocument("es", "<b>hola</b>", [CVExperience("Rol", "<script>", "2020", "", [
            CVBullet(1, '<link rel="attachment" href="file:///etc/passwd">', "x", 1.0)])], [], [])
        html = render_html(doc, UserProfile(username="u", full_name="Ana"))
        assert "<script>" not in html and "<link" not in html and "<b>hola" not in html

    def test_fits_one_page_by_trimming_least_relevant(self):
        bullets = [CVBullet(i, f"Logro número {i} " + "con mucho detalle " * 12, "x", score=i) for i in range(40)]
        doc = CVDocument("es", "Resumen", [CVExperience("Rol", "Empresa", "2020", "", bullets)], [], [])
        result = render(doc, UserProfile(username="u", full_name="Ana"))
        assert result.pages == 1 and result.trimmed
        kept = [b.achievement_id for b in doc.experiences[0].included]
        assert min(kept) > 0 and 39 in kept  # se quitan primero los de menor puntaje
        assert result.pdf.startswith(b"%PDF") and result.docx[:2] == b"PK"

    def test_english_titles_and_labels(self):
        vacancy, m = _match()
        sel = select_content(_profile(), m, vacancy)
        from core.engine.writing import WrittenCV

        doc = build_document(sel, WrittenCV(summary="S", bullets={}), "en")
        md = doc.to_markdown()
        assert "## Work Experience" in md and "Tools & software" in md


class TestPipeline:
    def test_analyze_and_generate_end_to_end(self):
        profile = _profile()
        analysis = analyze(FakeLLM(_VACANCY, _EVIDENCE), profile, text="vacante")
        assert analysis.match.score > 0
        ids = [a.id for e in profile.experiences for a in e.achievements]
        cv = generate(
            FakeLLM({"summary": "Auxiliar Administrativo con 7 años de experiencia",
                     "bullets": [{"id": i, "text": profile.achievement(i)[1].text} for i in ids]}),
            profile, UserProfile(username="laura", full_name="Laura"), analysis,
        )
        assert cv.output.pages == 1 and not cv.reverted
        assert "### Asistente Administrativa - Autos del Caribe" in cv.document.to_markdown()
