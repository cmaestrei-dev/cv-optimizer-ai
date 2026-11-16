"""Bot local (runner): lectura de LinkedIn, configuración, estado y una vuelta completa contra la API de pruebas."""

import json
from datetime import date
from pathlib import Path

import pytest

from core.jobs import worker
from runner import __main__ as cli
from runner import config as cfg
from runner import discover
from runner.api import Api, ApiError
from runner.state import State
from tests.test_api_engine import ana  # noqa: F401  (fixture: cuenta con perfil e IA falsa)

SEARCH_HTML = """
<li><div class="base-card" data-entity-urn="urn:li:jobPosting:4012345678">
  <h3 class="base-search-card__title">  Auxiliar Administrativo  </h3>
  <h4 class="base-search-card__subtitle"><a href="#">Logística Andina</a></h4>
  <span class="job-search-card__location">Bogotá, Distrito Capital, Colombia</span>
  <time class="job-search-card__listdate" datetime="2026-11-15">Hace 1 día</time></div></li>
<li><div data-entity-urn="urn:li:jobPosting:4012345679">
  <h3 class="base-search-card__title">Analista Senior de Datos</h3>
  <h4 class="base-search-card__subtitle"><a>Datos &amp; Co</a></h4>
  <span class="job-search-card__location">Colombia</span></div></li>
"""
POSTING_HTML = """
<div class="show-more-less-html__markup"><p>Buscamos <strong>auxiliar administrativo</strong>.</p>
<ul><li>Excel avanzado</li><li>Facturación</li></ul></div>
<ul><li><h3 class="description__job-criteria-subheader">Tipo de empleo</h3>
<span class="description__job-criteria-text">Jornada completa</span></li></ul>
"""


class TestLinkedInPages:
    def test_search_url_uses_the_public_filters(self):
        url = discover.search_url(cfg.Search("auxiliar administrativo", "Cartagena", days=7), start=10)
        assert "geoId=106336022" in url and "f_TPR=r604800" in url and "f_AL=true" in url and "start=10" in url

    def test_parse_cards(self):
        cards = discover.parse_cards(SEARCH_HTML)
        assert [c.job_id for c in cards] == ["4012345678", "4012345679"]
        first = cards[0]
        assert (first.title, first.company, first.place, first.posted) == (
            "Auxiliar Administrativo", "Logística Andina", "Bogotá, Distrito Capital, Colombia", date(2026, 11, 15))
        assert first.url == "https://www.linkedin.com/jobs/view/4012345678"
        assert cards[1].company == "Datos & Co" and cards[1].posted is None

    def test_parse_posting_keeps_lines_and_criteria(self):
        text = discover.parse_posting(POSTING_HTML)
        assert text.splitlines()[:3] == ["Buscamos auxiliar administrativo.", "- Excel avanzado", "- Facturación"]
        assert text.endswith("Tipo de empleo: Jornada completa")
        assert discover.parse_posting("<html>sin oferta</html>") == ""


class TestConfig:
    def _write(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "config.toml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_template_is_rejected_until_edited(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CVO_BOT_TOKEN", "cvb_x")
        with pytest.raises(cfg.ConfigError, match="dirección de tu app"):
            cfg.load(self._write(tmp_path, cfg.TEMPLATE))

    def test_valid_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CVO_BOT_TOKEN", "cvb_x")
        conf = cfg.load(self._write(tmp_path, cfg.TEMPLATE.replace("https://TU-SERVICIO.run.app/api", "https://app.example.com/api/")))
        assert conf.api == "https://app.example.com/api" and conf.mode == "prueba" and conf.daily_cap == 20
        assert conf.searches[0].geo_id == "100876405" and conf.exclude_words == ["senior", "practicante"]

    @pytest.mark.parametrize("change, message", [
        (('modo = "prueba"', 'modo = "turbo"'), "modo"),
        (('lugar = "Colombia"', 'lugar = "Narnia"'), "Narnia"),
        (("tope_diario = 20", "tope_diario = 500"), "tope_diario"),
        (('api = "https://app.example.com/api"', 'api = "ftp://x"'), "https"),
    ])
    def test_invalid_values(self, tmp_path, monkeypatch, change, message):
        monkeypatch.setenv("CVO_BOT_TOKEN", "cvb_x")
        body = cfg.TEMPLATE.replace("https://TU-SERVICIO.run.app/api", "https://app.example.com/api").replace(*change)
        with pytest.raises(cfg.ConfigError, match=message):
            cfg.load(self._write(tmp_path, body))

    def test_token_file_is_private_and_validated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(cfg, "TOKEN_FILE", tmp_path / "token")
        with pytest.raises(cfg.ConfigError):
            cfg.save_token("no-es-un-token")
        path = cfg.save_token("  cvb_abc  ")
        assert path.read_text().strip() == "cvb_abc" and (path.stat().st_mode & 0o777) == 0o600


def test_state_round_trip(tmp_path):
    state = State(tmp_path / "estado.json")
    state.mark("1", "preparada", app=7)
    state.count("preparadas")
    state.pause(24, "HTTP 429")
    state.save()
    again = State(tmp_path / "estado.json")
    assert again.seen("1") and not again.seen("2") and again.today("preparadas") == 1
    assert again.pause_until() is not None and again.data["pausa_motivo"] == "HTTP 429"


class TestRun:
    """Una vuelta del bot contra la API de pruebas (IA falsa): sin red ni LinkedIn reales."""

    @pytest.fixture
    def bot(self, ana, tmp_path, monkeypatch):  # noqa: F811
        client, h, _fake = ana
        token = client.post("/bot-tokens", json={"label": "pruebas"}, headers=h).json()["token"]

        def request(self, method, path, body=None):
            r = client.request(method, path, json=body, headers={"Authorization": f"Bearer {self.token}"})
            if path.endswith("/cvs") and method == "POST":
                worker.run_once()  # en producción el trabajador de la API lo procesa en segundo plano
            if r.status_code >= 400:
                payload = r.json()
                raise ApiError(r.status_code, payload.get("detail", ""), payload)
            return r.status_code, r.content

        monkeypatch.setattr(Api, "_request", request)
        monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
        conf_path = tmp_path / "config.toml"
        conf_path.write_text(cfg.TEMPLATE.replace("https://TU-SERVICIO.run.app/api", "https://app.example.com/api"), encoding="utf-8")
        monkeypatch.setattr(cfg, "CONFIG_FILE", conf_path)
        monkeypatch.setenv("CVO_BOT_TOKEN", token)
        monkeypatch.setattr(cfg, "load", lambda path=conf_path, _load=cfg.load: _load(path))
        pages = {"search": SEARCH_HTML, "posting": POSTING_HTML}
        monkeypatch.setattr(discover, "fetch", lambda url, **k: pages["posting" if "/jobPosting/" in url else "search"])
        monkeypatch.setattr(discover, "pause", lambda *a, **k: None)
        return client, h, tmp_path

    def test_prepares_new_vacancies_skips_excluded_and_repeats(self, bot, capsys):
        client, h, tmp_path = bot
        assert cli.main(["buscar"]) == 0
        out = capsys.readouterr().out
        assert "Auxiliar Administrativo" in out and "omitida (el cargo contiene «senior»)" in out
        apps = client.get("/applications?view=todas", headers=h).json()
        assert len(apps) == 1 and apps[0]["url"] == "https://www.linkedin.com/jobs/view/4012345678"
        assert apps[0]["status"] == "cv_generado" and apps[0]["posted_on"] == "2026-11-15"
        assert (tmp_path / "cvs" / f"{apps[0]['id']}.pdf").read_bytes().startswith(b"%PDF")
        state = json.loads((tmp_path / "estado.json").read_text())
        assert state["vistas"]["4012345678"]["estado"] == "preparada"
        assert state["vistas"]["4012345679"]["estado"] == "excluida"

        assert cli.main(["buscar"]) == 0  # segunda vuelta: nada nuevo, nada repetido en la app
        assert len(client.get("/applications?view=todas", headers=h).json()) == 1

    def test_blocked_by_linkedin_pauses_a_day(self, bot, monkeypatch, capsys):
        def blocked(url, **k):
            raise discover.BlockedError("LinkedIn frenó las peticiones (HTTP 429).")

        monkeypatch.setattr(discover, "fetch", blocked)
        assert cli.main(["buscar"]) == 0
        assert "Pausa de 24 horas" in capsys.readouterr().out
        assert cli.main(["buscar"]) == 0
        assert "En pausa hasta" in capsys.readouterr().out

    def test_revoked_token_is_explained(self, bot, capsys):
        client, h, _ = bot
        for t in client.get("/bot-tokens", headers=h).json():
            client.delete(f"/bot-tokens/{t['id']}", headers=h)
        assert cli.main(["buscar"]) == 1
        assert "revocado" in capsys.readouterr().err
