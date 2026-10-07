import json
from unittest.mock import MagicMock, patch

import pytest

from core.profile import service
from core.profile.importer import ImportedCV, extract_cv, plan_import
from core.profile.periods import parse_period
from core.profile.snapshot import ExperienceSnap, ProfileSnapshot, SkillSnap

PDF_TEXT = """Laura Gómez  laura@example.com  Aptitudes principales: Facturación, Microsoft Excel
Experiencia
Autos del Caribe  Asistente Administrativa  marzo de 2023 - Present (3 años 8 meses)
Elaboré la facturación de 180 facturas al mes.
Concilié las cuentas por cobrar.
TiendaYa  Auxiliar Administrativa  enero de 2021 - febrero de 2023
Educación  SENA  Tecnóloga en Gestión Administrativa (2018 - 2020)"""

EXTRACTED = {
    "full_name": "Laura Gómez", "email": "laura@example.com", "phone": "", "linkedin_url": "",
    "experiences": [
        {"role": "Asistente Administrativa", "company": "Autos del Caribe", "period_text": "marzo de 2023 - Presente",
         "achievements": ["Elaboré la facturación de 180 facturas al mes.", "Concilié las cuentas por cobrar.",
                          "Reduje errores un 40% usando SAP."]},
        {"role": "Auxiliar Administrativa", "company": "TiendaYa", "period_text": "enero de 2021 - febrero de 2023"},
    ],
    "skills": [{"name": "Facturación", "category": "Conocimientos del área"},
               {"name": "Microsoft Excel", "category": "Herramientas y software"},
               {"name": "Power BI", "category": "Herramientas y software"},
               {"name": "Liderazgo", "category": "inventada"}],
    "education": [{"title": "Tecnóloga en Gestión Administrativa", "institution": "SENA", "period_text": "2018 - 2020"}],
}


def _llm(payload):
    llm = MagicMock()
    llm.label = "fake:model"
    llm.complete.return_value = json.dumps(payload)
    return llm


class TestExtractAndPlan:
    def test_extraction_prompt_and_unknown_category(self):
        llm = _llm(EXTRACTED)
        data = extract_cv(llm, PDF_TEXT)
        assert "Present" in llm.complete.call_args[0][0]
        assert data.skills[3].category == "Otros"

    def test_discards_what_is_not_in_the_pdf(self):
        plan = plan_import(ImportedCV.model_validate(EXTRACTED), PDF_TEXT, ProfileSnapshot("laura"))
        assert plan.data.experiences[0].achievements == [
            "Elaboré la facturación de 180 facturas al mes.", "Concilié las cuentas por cobrar.",
        ]
        assert [s.name for s in plan.data.skills] == ["Facturación", "Microsoft Excel"]
        assert len(plan.discarded) == 3  # logro con 40%/SAP, Power BI, Liderazgo
        assert plan.new_experiences == [0, 1] and plan.new_education == [0]

    def test_skips_what_the_profile_already_has(self):
        profile = ProfileSnapshot(
            "laura",
            experiences=(ExperienceSnap(1, "asistente administrativa", "AUTOS DEL CARIBE", "", parse_period("")),),
            skills=(SkillSnap(1, "facturacion", "Otros"),),
        )
        plan = plan_import(ImportedCV.model_validate(EXTRACTED), PDF_TEXT, profile)
        assert plan.duplicate_experiences == [0] and plan.new_experiences == [1]
        assert [plan.data.skills[i].name for i in plan.new_skills] == ["Microsoft Excel"]


class TestApplyImport:
    @pytest.fixture(autouse=True)
    def _fresh_db_flag(self, monkeypatch):
        monkeypatch.setattr(service, "_ready", False)  # cada test usa una base temporal nueva

    def test_atomic_import_and_contact_fill(self):
        service.ensure_ready()
        service.create_user("laura", full_name="Laura G.")
        plan = plan_import(ImportedCV.model_validate(EXTRACTED), PDF_TEXT, ProfileSnapshot("laura"))
        counts = service.apply_import(
            "laura", plan.data, experiences=plan.new_experiences, skills=plan.new_skills,
            education=plan.new_education, fill_contact=True,
        )
        assert counts == {"experiencias": 2, "logros": 2, "habilidades": 2, "estudios": 1}
        user = service.get_user("laura")
        assert user.full_name == "Laura G." and user.email == "laura@example.com"  # solo llena vacíos
        exps = service.list_experiences("laura")
        assert exps[0].is_current and exps[0].start_year == 2023

    def test_failure_saves_nothing(self):
        service.ensure_ready()
        service.create_user("laura")
        plan = plan_import(ImportedCV.model_validate(EXTRACTED), PDF_TEXT, ProfileSnapshot("laura"))
        with pytest.raises(IndexError):
            service.apply_import("laura", plan.data, experiences=[0, 99], skills=[], education=[])
        assert service.list_experiences("laura") == []


class TestInvalidKeyMessages:
    @pytest.mark.parametrize(("status", "body"), [
        (401, '{"error":{"status":"UNAUTHENTICATED","details":[{"reason":"ACCESS_TOKEN_TYPE_UNSUPPORTED"}]}}'),
        (400, '{"error":{"details":[{"reason":"API_KEY_INVALID"}]}}'),
        (403, "{}"),
    ])
    def test_new_client(self, status, body, monkeypatch):
        from core.llm import PROVIDERS, LLMAuthError, LLMClient

        monkeypatch.setattr("utils.retry.time.sleep", lambda _s: None)
        resp = MagicMock(status_code=status, text=body)
        with patch("core.llm.client.requests.post", return_value=resp), pytest.raises(LLMAuthError) as exc:
            LLMClient(PROVIDERS["gemini"], "AQ.mala", "m").complete("x")
        assert "GEMINI_API_KEY" in str(exc.value) and "AQ.mala" not in str(exc.value)
