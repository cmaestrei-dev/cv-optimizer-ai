import json
from unittest.mock import MagicMock

from core.profile.interview import (
    CheckedProposal,
    Question,
    generate_questions,
    merge_achievements,
    propose_improvements,
    strength,
)
from core.profile.periods import parse_period
from core.profile.snapshot import AchievementSnap, ExperienceSnap

EXP = ExperienceSnap(
    2, "Auxiliar Administrativa", "TiendaYa", "2021 - 2023", parse_period("2021 - 2023"), "", "",
    (AchievementSnap(21, "Gestioné órdenes de compra y despachos"),
     AchievementSnap(22, "Respondí PQR de 30 clientes al día"),
     AchievementSnap(23, "Llevé el control de inventario")),
)


def _llm(*payloads):
    llm = MagicMock()
    llm.label = "fake:model"
    llm.complete.side_effect = [json.dumps(p) for p in payloads]
    return llm


def test_strength_counts_achievements_with_numbers():
    assert strength(EXP) == (1, 3)


def test_questions_are_capped_and_ids_validated():
    qs = [{"achievement_id": 21, "question": "¿Cuántas órdenes?"}, {"achievement_id": 999, "question": "¿Y esto?"},
          {"question": "  "}] + [{"question": f"P{i}"} for i in range(10)]
    questions = generate_questions(_llm({"questions": qs}), EXP)
    assert len(questions) <= 6
    assert questions[0].achievement_id == 21 and questions[1].achievement_id is None
    assert all(q.question.strip() for q in questions)


def test_proposals_only_use_answers_and_skip_unknowns():
    q1 = Question(achievement_id=21, question="¿Cuántas órdenes?")
    q2 = Question(achievement_id=23, question="¿Qué programa?")
    q3 = Question(achievement_id=None, question="¿Algún reconocimiento?")
    llm = _llm({"proposals": [
        {"achievement_id": 21, "text": "Gestioné 40 órdenes de compra semanales con Servientrega."},
        {"achievement_id": 23, "text": "Llevé el inventario en SAP reduciendo pérdidas 20%"},
        {"achievement_id": None, "text": "Fui empleada del mes en 2022"},
        {"achievement_id": 22, "text": "Respondí PQR de 30 clientes al día"},  # sin cambios: se ignora
    ]})
    checked = propose_improvements(llm, EXP, [(q1, "unas 40 a la semana, con Servientrega"), (q2, "no sé"), (q3, "empleada del mes 2022")])
    by_id = {p.achievement_id: p for p in checked}
    assert by_id[21].ok and by_id[21].proposed.endswith("Servientrega")
    assert not by_id[23].ok and any("SAP" in x for x in by_id[23].problems)
    assert by_id[None].ok and 22 not in by_id
    prompt = llm.complete.call_args[0][0]
    assert "no sé" not in prompt  # las respuestas vacías o "no sé" no se envían


def test_no_answers_means_no_call():
    llm = _llm()
    assert propose_improvements(llm, EXP, [(Question(question="¿x?"), ""), (Question(question="¿y?"), "N/A")]) == []
    llm.complete.assert_not_called()


def test_merge_keeps_order_and_appends_new():
    accepted = [CheckedProposal(23, "Llevé el control de inventario", "Llevé el inventario en Google Sheets"),
                CheckedProposal(None, "", "Fui empleada del mes en 2022")]
    assert merge_achievements(EXP, accepted) == [
        "Gestioné órdenes de compra y despachos", "Respondí PQR de 30 clientes al día",
        "Llevé el inventario en Google Sheets", "Fui empleada del mes en 2022",
    ]
