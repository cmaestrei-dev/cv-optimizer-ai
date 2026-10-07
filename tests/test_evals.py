from core.engine.matching import RequirementMatch
from core.vacancy import Requirement, VacancyAnalysis
from evals.cases import CASES, PROFILES
from evals.metrics import keyword_coverage, match_accuracy


class _Analysis:
    def __init__(self, requirements, keywords=()):
        self.match = type("M", (), {"requirements": requirements})()
        self.vacancy = VacancyAnalysis(is_vacancy=True, keywords=list(keywords))


def _req(text, level):
    return RequirementMatch(Requirement(text=text, kind="obligatorio", category="otro"), level)


def test_cases_are_well_formed():
    assert len({c.name for c in CASES}) == len(CASES)
    for case in CASES:
        assert case.profile in PROFILES and case.expected and case.language in ("es", "en")


def test_match_accuracy_ignores_case_and_accents():
    case = CASES[0]  # SAP: no, Excel: cubre/parcial, factura: cubre, gesti: cubre
    analysis = _Analysis([_req("Manejo de SAP Business One", "no"), _req("EXCEL intermedio", "parcial"),
                          _req("Experiencia en facturación", "no"), _req("Tecnólogo en gestión", "cubre")])
    hits, total, misses = match_accuracy(case, analysis)
    assert (hits, total) == (3, 4) and "factura" in misses[0]


def test_keyword_coverage_only_counts_what_the_candidate_has():
    profile, _ = PROFILES["andres_dev"]
    analysis = _Analysis([], keywords=["Python", "Docker", "Kubernetes"])
    assert keyword_coverage(analysis, profile, "Python y Docker") == 1.0  # Kubernetes no está en el perfil
    assert keyword_coverage(analysis, profile, "Solo Python") == 0.5
