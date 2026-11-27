"""Vacantes que exigen un inglés más alto que el del dueño (decisión del 2026-11-26): se descartan antes del CV."""

import dataclasses

import pytest

from runner import __main__ as cli
from runner import config as cfg


def req(text, kind="obligatorio"):
    return {"text": text, "kind": kind, "category": "idioma"}


@pytest.mark.parametrize("requirements, level", [
    ([req("Advanced English proficiency (B2 or Higher)")], 3),   # Sutherland, 2026-11-26
    ([req("Inglés intermedio-avanzado")], 3),
    ([req("English C1"), req("Python")], 4),
    ([req("Inglés fluido")], 4),
    ([req("Bilingüe español-inglés")], 5),
    ([req("Inglés intermedio (B1)")], 2),
    ([req("Nivel de inglés básico")], 1),
    ([req("Advanced English", kind="deseable")], 0),           # deseable no cuenta
    ([req("Excel avanzado"), req("Conocimientos en Power BI")], 0),  # «avanzado» sin inglés
    ([], 0),
])
def test_english_required(requirements, level):
    assert cli.english_required(requirements) == level


def test_the_gap_uses_the_owners_threshold():
    conf = cfg.Config(api="http://127.0.0.1:9", token="t", english_from="B2")
    detail = {"vacancy": {"requirements": [req("Advanced English proficiency (B2 or Higher)")]}}
    assert cli._english_gap(detail, conf) == "exige inglés B2 o más"
    assert cli._english_gap({"vacancy": {"requirements": [req("Inglés intermedio")]}}, conf) == ""
    assert cli._english_gap(detail, dataclasses.replace(conf, english_from="")) == ""  # sin la regla, nada
    assert cli._english_gap(detail, dataclasses.replace(conf, english_from="C1")) == ""


def test_prepare_discards_before_the_cv(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from runner.state import State

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    calls = []

    class Api:
        def get(self, path):
            return {"vacancy": {"language": "en", "location": "Bogotá", "requirements": [req("Advanced English (B2+)")]},
                    "vacancy_text": "Software Engineer"}

        def post(self, path, body=None):
            calls.append((path, body))
            return {}

        def make_cv(self, app_id):
            pytest.fail("no debía hacer el CV")

    conf = cfg.Config(api="http://127.0.0.1:9", token="t", english_from="B2")
    state = State(tmp_path / "estado.json")
    args = SimpleNamespace(sin_cv=False)
    assert cli._prepare(Api(), conf, state, args, portal="linkedin", job_id="1", app_id=9, score=90, url="u") is False
    assert calls == [("/applications/9/status", {"status": "descartada", "note": "El bot la omitió: exige inglés B2 o más."})]
    assert state.data["vistas"]["1"]["estado"] == "excluida"


def test_config(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(cfg, "_token", lambda: "t")
    base = 'api = "https://x.run.app/api"\n[[busqueda]]\npalabras = "qa"\n'
    path.write_text(base + '[excluir]\ningles_exigido_desde = "b2"\n')
    assert cfg.load(path).english_from == "B2"
    path.write_text(base + '[excluir]\ningles_exigido_desde = "A2"\n')
    with pytest.raises(cfg.ConfigError):
        cfg.load(path)
