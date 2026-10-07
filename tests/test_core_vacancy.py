import json
from unittest.mock import MagicMock

import pytest

from core.vacancy import NotAVacancyError, analyze_vacancy

_ANALYSIS = {
    "is_vacancy": True,
    "role": "Auxiliar Administrativo",
    "company": "Logística SAS",
    "language": "es",
    "area": "Administrativa",
    "min_years_experience": 2,
    "summary": "Apoyo administrativo.",
    "requirements": [
        {"text": "Excel intermedio", "kind": "obligatorio", "category": "herramienta"},
        {"text": "SAP", "kind": "deseable", "category": "herramienta"},
    ],
    "responsibilities": ["Facturación"],
    "keywords": ["Excel", "SAP", "facturación"],
}


def _llm(payload: dict) -> MagicMock:
    llm = MagicMock()
    llm.label = "fake:model"
    llm.complete.return_value = json.dumps(payload)
    return llm


class TestAnalyzeVacancy:
    def test_returns_structured_analysis(self):
        llm = _llm(_ANALYSIS)
        analysis = analyze_vacancy(llm, text="Se busca auxiliar...")
        assert analysis.role == "Auxiliar Administrativo"
        assert [r.text for r in analysis.must_haves] == ["Excel intermedio"]
        prompt = llm.complete.call_args[0][0]
        assert "Se busca auxiliar..." in prompt
        assert llm.complete.call_args[1]["cache"] is True

    def test_rejects_non_vacancy(self):
        with pytest.raises(NotAVacancyError):
            analyze_vacancy(_llm({"is_vacancy": False}), text="hola")

    def test_requires_some_input(self):
        with pytest.raises(ValueError):
            analyze_vacancy(_llm(_ANALYSIS), text="  ")
