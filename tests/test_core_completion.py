import json
from unittest.mock import MagicMock

import pytest

from core.profile import service
from core.profile.completion import (
    find_duplicate,
    merge_task_details,
    split_into_achievements,
    typical_tasks,
)
from core.profile.periods import parse_period
from core.profile.snapshot import AchievementSnap, ExperienceSnap

EXP = ExperienceSnap(
    1, "Auxiliar Administrativa", "Concesionario", "2024 - Presente", parse_period("2024 - Presente"), "", "",
    (AchievementSnap(1, "Apoyo administrativo y operativo al área comercial"),),
)


def _llm(*payloads):
    llm = MagicMock()
    llm.label = "fake:model"
    llm.complete.side_effect = [json.dumps(p) for p in payloads]
    return llm


def test_find_duplicate():
    existing = ["Apoyo administrativo y operativo al área comercial"]
    assert find_duplicate("Brindé apoyo administrativo al área comercial", existing) == existing[0]
    assert find_duplicate("Elaboré facturas de venta", existing) is None


def test_split_keeps_user_facts_and_flags_inventions_and_duplicates():
    llm = _llm({"achievements": [
        "Elaboré las facturas de vehículos, unas 60 al mes.",
        "Gestioné la cobranza a clientes con saldos pendientes por WhatsApp",
        "Reduje la cartera vencida un 30% usando SAP",
        "Brindé apoyo administrativo al área comercial",
        "Elaboré las facturas de vehículos, unas 60 al mes",  # repetido en la misma respuesta
    ]})
    text = "hacía las facturas de los carros, unas 60 al mes, y llamaba por whatsapp a los que debían plata"
    candidates = split_into_achievements(llm, EXP, text)
    assert [c.suggested for c in candidates] == [True, True, False, False]
    assert any("30" in p for p in candidates[2].problems) and candidates[3].duplicate_of
    assert text in llm.complete.call_args[0][0]


def test_split_with_empty_text_does_not_call_the_llm():
    llm = _llm()
    assert split_into_achievements(llm, EXP, "   ") == []
    llm.complete.assert_not_called()


def test_typical_tasks_skip_what_is_already_there():
    llm = _llm({"tasks": ["Elaboré facturas de venta.", "Brindé apoyo administrativo y operativo al área comercial",
                          "Radiqué documentos de matrícula", "Elaboré facturas de venta"]})
    assert typical_tasks(llm, EXP) == ["Elaboré facturas de venta", "Radiqué documentos de matrícula"]


def test_merge_without_details_needs_no_llm():
    llm = _llm()
    candidates = merge_task_details(llm, EXP, [("Radiqué documentos de matrícula", "")])
    assert [c.text for c in candidates] == ["Radiqué documentos de matrícula"] and candidates[0].ok
    llm.complete.assert_not_called()


def test_merge_keeps_user_numbers_even_if_the_llm_drops_them():
    llm = _llm({"achievements": ["Radiqué documentos de matrícula en el sistema DMS", "Elaboré facturas con los asesores"]})
    candidates = merge_task_details(llm, EXP, [
        ("Radiqué documentos de matrícula", "unas 15 al día en el sistema DMS"),
        ("Elaboré facturas", "con los asesores"),
    ])
    assert candidates[0].text == "Radiqué documentos de matrícula (unas 15 al día en el sistema DMS)"
    assert candidates[1].text == "Elaboré facturas con los asesores"
    assert all(c.ok for c in candidates)


class TestAppendAchievements:
    @pytest.fixture(autouse=True)
    def _fresh(self, monkeypatch):
        monkeypatch.setattr(service, "_ready", False)
        service.ensure_ready()

    def test_appends_after_existing_in_order(self):
        service.create_user("ana")
        service.add_experience("ana", role="Aux", achievements=["a", "b"])
        exp_id = service.list_experiences("ana")[0].id
        assert service.append_achievements("ana", exp_id, ["c", " ", "d"]) == 2
        assert [a.text for a in service.list_experiences("ana")[0].achievements] == ["a", "b", "c", "d"]

    def test_cannot_append_to_someone_elses_experience(self):
        from core.profile.repository import NotFoundError

        service.create_user("ana")
        service.create_user("eve")
        service.add_experience("ana", role="Aux")
        exp_id = service.list_experiences("ana")[0].id
        with pytest.raises(NotFoundError):
            service.append_achievements("eve", exp_id, ["hackeado"])
