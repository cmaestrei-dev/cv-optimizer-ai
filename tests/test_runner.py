"""Bot local (runner): lectura de LinkedIn, configuración, estado y una vuelta completa contra la API de pruebas."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.jobs import worker
from runner import __main__ as cli
from runner import computrabajo, discover
from runner import config as cfg
from runner.api import Api, ApiError
from runner.state import State
from tests.test_api_assist import (
    diana,  # noqa: F401  (fixture: cuenta vacía con IA falsa de importación)
)
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

# Computrabajo: misma estructura que la página real (2026-11-18), con datos inventados.
CT_SEARCH_HTML = """
<article class="box_offer sel " data-id='2B8F7CDED6FA648661373E686DCF3405' data-blind="false">
  <h2 class="fs18 fwB prB"><a class="js-o-link fc_base" href="/ofertas-de-trabajo/oferta-de-trabajo-de-auxiliar-contable-en-cartagena-de-indias-2B8F7CDED6FA648661373E686DCF3405#lc=ListOffers-Score4-0">
    Auxiliar contable</a><div class="tags"><span class="tag postulated hide">Postulado</span></div></h2>
  <p class="dFlex vm_fx fs16 fc_base mt5"><a class="fc_base t_ellipsis" href="#" offer-grid-article-company-url>Contadores &amp; Cía</a></p>
  <p class="fs16 fc_base mt5"><span class="mr10">Cartagena de Indias, Bol&#xED;var</span></p>
  <p class="fs13 fc_aux mt15">Hace  2  horas</p>
</article>
<article class="box_offer" data-id='68F75B8F0F1E682961373E686DCF3405' data-blind="false">
  <h2><a class="js-o-link fc_base" href="/ofertas-de-trabajo/oferta-de-trabajo-de-asesor-comercial-senior-68F75B8F0F1E682961373E686DCF3405#lc=x">Asesor comercial senior</a></h2>
  <p class="fs16 fc_base mt5"><span class="mr10">Bogot&#xE1;, D.C.</span></p>
  <p class="fs13 fc_aux mt15">Ayer</p>
</article>
"""
CT_POSTING_HTML = """
<div class="mb40 pb40 bb1" div-link="oferta"><h2>Descripción de la oferta</h2>
  <div class="mbB"><span class="tag base mb10">$ 1.800.000,00 (Mensual)</span><span class="tag base mb10">Tiempo Completo</span></div>
  <p class="mbB">Buscamos <b>auxiliar contable</b>.<br /><br />Funciones:<br />Conciliaciones bancarias<br />Facturación</p>
  <p class="fwB fs18 mtB mb10">Requerimientos</p>
  <ul class="disc mbB"><li class='mb10'>Educación mínima: Técnico</li><li class='mb10'>1 año de experiencia</li></ul>
  <span class="tag bg_brand_light" data-skill-id="EC2456E4BF054B47">Excel</span>
  <p class="fc_aux fs13 mbB mtB">Palabras clave: developer, desarrollador, programador</p>
  <a data-href-offer-apply="https://candidato.co.computrabajo.com/match/?oi=2B8F" class="b_primary">Aplicar</a>
</div>
"""


def test_job_ids_from_canonical_urls():
    assert cli._job_id("linkedin", "https://www.linkedin.com/jobs/view/4012345678") == "4012345678"
    assert cli._job_id("computrabajo", "https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-qa-en-cali-"
                                       "3b20bf04c1af1c7061373e686dcf3405") == "ct:3B20BF04C1AF1C7061373E686DCF3405"
    assert cli._job_id("linkedin", "https://www.linkedin.com/feed/") == ""


class TestComputrabajoPages:
    def test_search_url_by_city_remote_and_date(self):
        url = computrabajo.search_url(cfg.Search("desarrollador de software", "Cartagena", days=7, portal="computrabajo"), 2)
        assert url == ("https://co.computrabajo.com/trabajo-de-desarrollador-de-software-en-cartagena-de-indias"
                       "?pubdate=7&by=publicationtime&p=2")
        assert "-en-remoto?" in computrabajo.search_url(cfg.Search("qa", "Remoto", portal="computrabajo"))
        assert "-en-medellin?" in computrabajo.search_url(cfg.Search("qa", "Medellín, Antioquia", portal="computrabajo"))
        assert "/trabajo-de-practicante-de-sistemas?pubdate=1" in computrabajo.search_url(
            cfg.Search("Practicante de Sistemas", "Colombia", portal="computrabajo"))

    def test_parse_cards(self):
        cards = computrabajo.parse_cards(CT_SEARCH_HTML, today=date(2026, 11, 18))
        first = cards[0]
        assert first.job_id == "ct:2B8F7CDED6FA648661373E686DCF3405" and first.title == "Auxiliar contable"
        assert (first.company, first.place, first.posted) == ("Contadores & Cía", "Cartagena de Indias, Bolívar", date(2026, 11, 18))
        assert first.url == ("https://co.computrabajo.com/ofertas-de-trabajo/"
                             "oferta-de-trabajo-de-auxiliar-contable-en-cartagena-de-indias-2B8F7CDED6FA648661373E686DCF3405")
        assert cards[1].posted == date(2026, 11, 17) and cards[1].company == ""

    def test_parse_posting_drops_the_seo_keywords(self):
        text = computrabajo.parse_posting(CT_POSTING_HTML)
        assert text.startswith("$ 1.800.000,00 (Mensual) · Tiempo Completo")
        assert "Funciones:\nConciliaciones bancarias\nFacturación" in text
        assert "Requerimientos:\n- Educación mínima: Técnico\n- 1 año de experiencia" in text and "Aptitudes: Excel" in text
        assert "developer" not in text and "Aplicar" not in text
        assert computrabajo.parse_posting("<html>sin oferta</html>") == ""

    def test_a_browser_check_is_a_block_never_solved(self, monkeypatch):
        class Page:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return b"<html><title>Just a moment...</title></html>"

        monkeypatch.setattr(computrabajo.urllib.request, "urlopen", lambda *a, **k: Page())
        with pytest.raises(discover.BlockedError, match="verificación"):
            computrabajo.fetch("https://co.computrabajo.com/trabajo-de-qa")


class TestLinkedInPages:
    def test_search_url_uses_the_public_filters(self):
        url = discover.search_url(cfg.Search("auxiliar administrativo", "Cartagena", days=7), start=10)
        assert "geoId=106336022" in url and "f_TPR=r604800" in url and "f_AL=true" in url and "start=10" in url

    def test_unknown_places_go_by_name(self):
        url = discover.search_url(cfg.Search("desarrollador", "Medellín, Antioquia, Colombia"))
        assert "location=Medell%C3%ADn%2C+Antioquia%2C+Colombia" in url and "geoId" not in url

    def test_exclusions_match_whole_words(self):
        conf = cfg.Config(api="https://x/api", token="cvb_x", exclude_words=["sr", "semi senior"], exclude_companies=["acme"])
        card = lambda title, company="Otra": discover.Card("1", title, company, "", None)  # noqa: E731
        assert cli._excluded(card("Ingeniero SRE"), conf) == ""
        assert cli._excluded(card("Desarrollador Sr. Python"), conf) == "el cargo contiene «sr»"
        assert cli._excluded(card("Analista Semi Senior"), conf) == "el cargo contiene «semi senior»"
        assert cli._excluded(card("Desarrollador", "ACME Corp"), conf) == "empresa excluida"

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
        assert conf.searches[0].geo_id == "100876405" and conf.exclude_words == ["senior", "lead"]
        assert conf.no_evidence == "saltar" and conf.default_years == 2 and conf.pause_seconds == (120, 240)
        assert conf.answers["aspiracion salarial|salario|expectativa salarial|salary"] == "3000000"

    def test_general_options_written_under_a_table_still_apply(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CVO_BOT_TOKEN", "cvb_x")
        body = (cfg.TEMPLATE.replace("https://TU-SERVICIO.run.app/api", "https://app.example.com/api")
                .replace('sin_evidencia = "saltar"', "") + 'sin_evidencia = "cero"\n')  # quedó dentro de [respuestas]
        conf = cfg.load(self._write(tmp_path, body))
        assert conf.no_evidence == "cero" and "sin_evidencia" not in conf.answers

    @pytest.mark.parametrize("change, message", [
        (('modo = "prueba"', 'modo = "turbo"'), "modo"),
        (('lugar = "Colombia"', 'lugar = ""'), "lugar"),
        (("tope_diario = 20", "tope_diario = 500"), "tope_diario"),
        (('api = "https://app.example.com/api"', 'api = "ftp://x"'), "https"),
        (('sin_evidencia = "saltar"', 'sin_evidencia = "inventar"'), "sin_evidencia"),
        (("experiencia_por_defecto = 2", "experiencia_por_defecto = 40"), "experiencia_por_defecto"),
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
    state.pause(6, "HTTP 429", kind="busqueda")
    state.save()
    again = State(tmp_path / "estado.json")
    assert again.seen("1") and not again.seen("2") and again.today("preparadas") == 1
    assert again.pause_until("busqueda") is not None and again.pause_reason("busqueda") == "HTTP 429"
    assert again.pause_until("cuenta") is None  # la búsqueda frenada no detiene la postulación


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
        ct = {"search": CT_SEARCH_HTML, "posting": CT_POSTING_HTML}
        monkeypatch.setattr(computrabajo, "fetch", lambda url, **k: ct["posting" if "/ofertas-de-trabajo/" in url else "search"])
        return client, h, tmp_path

    def test_prepares_new_vacancies_skips_excluded_and_repeats(self, bot, capsys):
        client, h, tmp_path = bot
        assert cli.main(["buscar"]) == 0
        out = capsys.readouterr().out
        assert "Auxiliar Administrativo" in out and "omitida (el cargo contiene «senior»)" in out
        apps = client.get("/applications?view=todas", headers=h).json()
        assert len(apps) == 1 and apps[0]["url"] == "https://www.linkedin.com/jobs/view/4012345678"
        assert apps[0]["status"] == "cv_generado" and apps[0]["posted_on"] == "2026-11-15"
        cv = client.get(f"/applications/{apps[0]['id']}", headers=h).json()["cvs"][-1]
        saved = tmp_path / "cvs" / str(apps[0]["id"]) / cv["filename"]  # con su nombre real (lo ve el reclutador)
        assert saved.read_bytes().startswith(b"%PDF")
        state = json.loads((tmp_path / "estado.json").read_text())
        assert state["vistas"]["4012345678"]["estado"] == "preparada"
        assert state["vistas"]["4012345678"]["cv_id"] == cv["id"] and state["vistas"]["4012345678"]["cv"] == str(saved)
        assert state["vistas"]["4012345679"]["estado"] == "excluida"

        assert cli.main(["buscar"]) == 0  # segunda vuelta: nada nuevo, nada repetido en la app
        assert len(client.get("/applications?view=todas", headers=h).json()) == 1

    def test_blocked_by_linkedin_pauses_a_day(self, bot, monkeypatch, capsys):
        def blocked(url, **k):
            raise discover.BlockedError("LinkedIn frenó las peticiones (HTTP 429).")

        monkeypatch.setattr(discover, "fetch", blocked)
        assert cli.main(["buscar"]) == 0
        assert "Pausa de 6 horas" in capsys.readouterr().out
        assert cli.main(["buscar"]) == 0
        assert capsys.readouterr().out.count("LinkedIn: búsqueda en pausa hasta") == 1

    def _config(self, tmp_path: Path, minimum: int) -> None:
        conf = tmp_path / "config.toml"
        conf.write_text(conf.read_text(encoding="utf-8").replace("compatibilidad_minima = 60", f"compatibilidad_minima = {minimum}"),
                        encoding="utf-8")

    def test_computrabajo_vacancies_are_prepared_apart_from_linkedin(self, bot, capsys):
        client, h, tmp_path = bot
        self._config(tmp_path, 0)
        assert cli.main(["buscar"]) == 0
        apps = {a["platform"]: a for a in client.get("/applications?view=todas", headers=h).json()}
        assert set(apps) == {"LinkedIn", "Computrabajo"} and apps["Computrabajo"]["status"] == "cv_generado"
        state = State(tmp_path / "estado.json")
        ct = state.data["vistas"]["ct:2B8F7CDED6FA648661373E686DCF3405"]
        assert ct["estado"] == "preparada" and ct["portal"] == "computrabajo" and Path(ct["cv"]).is_file()
        assert state.data["vistas"]["ct:68F75B8F0F1E682961373E686DCF3405"]["estado"] == "excluida"
        assert state.today("preparadas") == 1 and state.today("preparadas_computrabajo") == 1  # topes aparte
        assert "Computrabajo 1 de 20" in capsys.readouterr().out

    def test_below_the_minimum_is_discarded_in_the_app_without_a_cv(self, bot):
        client, h, tmp_path = bot
        self._config(tmp_path, 100)
        assert cli.main(["buscar"]) == 0
        app = next(a for a in client.get("/applications?view=descartadas", headers=h).json() if a["platform"] == "Computrabajo")
        assert app["status"] == "descartada"
        detail = client.get(f"/applications/{app['id']}", headers=h).json()
        assert not detail["cvs"] and any("mínimo 100" in str(e) for e in detail["events"])
        ct = State(tmp_path / "estado.json").data["vistas"]["ct:2B8F7CDED6FA648661373E686DCF3405"]
        assert ct["estado"] == "baja_compatibilidad"

    def test_inbox_vacancies_go_first_with_the_same_rules(self, bot, capsys):
        # Las alertas por correo llenan la bandeja de la app (analizadas en el servidor); el bot las toma de ahí.
        client, h, tmp_path = bot
        self._config(tmp_path, 0)
        text = "Auxiliar Administrativo\nLogística Andina\n\nBuscamos auxiliar administrativo. Excel avanzado. Facturación."
        ok = client.post("/vacancies", json={"text": text, "url": "https://www.linkedin.com/jobs/view/4555555555"}, headers=h).json()
        senior = client.post("/vacancies", json={"text": text, "url": "https://www.linkedin.com/jobs/view/4555555556"},
                             headers=h).json()
        client.patch(f"/applications/{senior['id']}", json={"role": "Analista Senior de Datos"}, headers=h)
        assert cli.main(["buscar", "--portal", "linkedin"]) == 0
        vistas = State(tmp_path / "estado.json").data["vistas"]
        assert vistas["4555555555"]["estado"] == "preparada" and vistas["4555555555"]["app"] == ok["id"]
        assert Path(vistas["4555555555"]["cv"]).is_file()
        assert vistas["4555555556"]["estado"] == "excluida"
        assert client.get(f"/applications/{senior['id']}", headers=h).json()["status"] == "descartada"
        assert "(bandeja)" in capsys.readouterr().out
        assert cli.main(["buscar", "--portal", "linkedin"]) == 0  # una segunda vuelta no la repite
        assert State(tmp_path / "estado.json").today("preparadas") == 2  # la de la bandeja + la de la búsqueda

    def test_portal_flag_searches_only_that_portal(self, bot, monkeypatch):
        client, h, tmp_path = bot
        monkeypatch.setattr(computrabajo, "fetch", lambda url, **k: pytest.fail("no debía buscar en Computrabajo"))
        assert cli.main(["buscar", "--portal", "linkedin"]) == 0
        assert State(tmp_path / "estado.json").today("preparadas") == 1

    def test_a_blocked_portal_pauses_only_its_own_search(self, bot, monkeypatch, capsys):
        client, h, tmp_path = bot

        def blocked(url, **k):
            raise discover.BlockedError("Computrabajo frenó las peticiones (HTTP 403).")

        monkeypatch.setattr(computrabajo, "fetch", blocked)
        assert cli.main(["buscar"]) == 0
        state = State(tmp_path / "estado.json")
        assert state.pause_until("busqueda_computrabajo") and not state.pause_until("busqueda")
        assert state.today("preparadas") == 1  # LinkedIn siguió
        assert "Paro la búsqueda en Computrabajo" in capsys.readouterr().out

    def test_revoked_token_is_explained(self, bot, capsys):
        client, h, _ = bot
        for t in client.get("/bot-tokens", headers=h).json():
            client.delete(f"/bot-tokens/{t['id']}", headers=h)
        assert cli.main(["buscar"]) == 1
        assert "revocado" in capsys.readouterr().err


class TestImportCommand:
    def test_imports_the_pdf_into_the_profile_once(self, diana, tmp_path, monkeypatch, capsys):  # noqa: F811
        from tests.test_api_assist import CV_HTML, _pdf

        client, h, _fake = diana
        token = client.post("/bot-tokens", json={}, headers=h).json()["token"]

        def request(self, method, path, body=None, *, raw=None, content_type="application/json"):
            kwargs = {"content": raw} if raw is not None else {"json": body}
            r = client.request(method, path, headers={"Authorization": f"Bearer {self.token}", "Content-Type": content_type}, **kwargs)
            if path == "/profile/import":
                worker.run_once()
            if r.status_code >= 400:
                raise ApiError(r.status_code, r.json().get("detail", ""), r.json())
            return r.status_code, r.content

        monkeypatch.setattr(Api, "_request", request)
        monkeypatch.setenv("CVO_BOT_TOKEN", token)
        conf = tmp_path / "config.toml"
        conf.write_text(cfg.TEMPLATE.replace("https://TU-SERVICIO.run.app/api", "https://app.example.com/api"), encoding="utf-8")
        monkeypatch.setattr(cfg, "load", lambda path=conf, _load=cfg.load: _load(path))
        pdf = tmp_path / "Profile.pdf"
        pdf.write_bytes(_pdf(CV_HTML))

        assert cli.main(["importar", str(pdf)]) == 0
        assert "Guardado: 1 experiencias, 2 logros, 1 habilidades y 1 estudios." in capsys.readouterr().out
        profile = client.get("/profile", headers=h).json()
        assert [e["role"] for e in profile["experiences"]] == ["Auxiliar Administrativa"]
        assert cli.main(["importar", str(pdf)]) == 0  # otra vez: nada repetido
        assert "Guardado: 0 experiencias" in capsys.readouterr().out
        assert len(client.get("/profile", headers=h).json()["experiences"]) == 1
        assert cli.main(["importar", str(tmp_path / "no-existe.pdf")]) == 2


def test_session_detection_reads_only_cookie_names(tmp_path):
    import sqlite3

    from runner import browser

    assert browser.has_session(tmp_path) is False  # sin perfil
    (tmp_path / "Default").mkdir()
    with sqlite3.connect(tmp_path / "Default" / "Cookies") as db:
        db.execute("create table cookies (host_key text, name text, encrypted_value blob)")
        db.execute("insert into cookies values ('.www.linkedin.com', 'bcookie', x'00')")
    assert browser.has_session(tmp_path) is False  # visitante
    with sqlite3.connect(tmp_path / "Default" / "Cookies") as db:
        db.execute("insert into cookies values ('.www.linkedin.com', 'li_at', x'00')")
    assert browser.has_session(tmp_path) is True
    assert browser.has_session(tmp_path, portal="computrabajo") is False  # su cookie de sesión aún no se conoce
    with sqlite3.connect(tmp_path / "Default" / "Cookies") as db:
        db.execute("insert into cookies values ('.computrabajo.com', 'sesion', x'00')")
    assert browser._cookie_names("computrabajo.com", tmp_path) == {"sesion"}


def test_login_refuses_while_the_bot_browser_is_open(tmp_path, monkeypatch, capsys):
    from runner import browser

    monkeypatch.setattr(browser, "PROFILE_DIR", tmp_path)
    monkeypatch.setattr(browser.shutil, "which", lambda _: "/usr/bin/google-chrome")
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: pytest.fail("no debía abrir otro Chrome"))
    (tmp_path / "SingletonLock").symlink_to("otro-equipo-12345")
    assert browser.login("computrabajo") == 1
    assert "ya está abierto" in capsys.readouterr().out


def test_waits_for_the_graphical_session_from_systemd(monkeypatch):
    # Una vuelta al encender el computador puede empezar antes que la sesión gráfica (pasó el 2026-11-20).
    from runner import browser

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        out = "HOME=/home/x\n" if len(calls) == 1 else "DISPLAY=:0\nXAUTHORITY=/run/user/1000/gdm/Xauthority\n"
        return SimpleNamespace(stdout=out)

    monkeypatch.setattr(browser.subprocess, "run", run)
    monkeypatch.setattr(browser.time, "sleep", lambda s: None)
    browser.ensure_display()
    assert browser.os.environ["DISPLAY"] == ":0" and len(calls) == 2
    monkeypatch.setattr(browser.subprocess, "run", lambda cmd, **k: SimpleNamespace(stdout=""))
    monkeypatch.delenv("DISPLAY")
    with pytest.raises(browser.NoDisplayError):
        browser.ensure_display(wait_seconds=0)


class TestAnswerer:
    """Las preguntas de experiencia sin respaldo en el perfil, según `sin_evidencia` (el resto no cambia)."""

    QUESTIONS = [
        ("radio", "¿Tienes experiencia con Microsoft Azure?", ["SI", "NO"], False),
        ("text", "¿Cuántos años de experiencia tienes con Kubernetes?", [], True),
        ("select", "¿Cuántos años de experiencia tienes con Python?", ["Menos de 1 año", "1 a 2 años", "3 a 5 años"], False),
        ("textarea", "¿Qué experiencia tienes con Terraform?", [], False),
        ("text", "¿Cuántos meses de experiencia tienes en soporte?", [], True),
        ("radio", "¿Requieres patrocinio de visa?", ["Sí", "No"], False),
        ("text", "¿Cuál es tu aspiración salarial?", [], True),
    ]

    def _answer(self, mode: str, replies: dict[str, str], *, units: bool = False):
        from runner.linkedin import Question

        api = SimpleNamespace(post=lambda path, body: [
            {"question": q, "answer": replies.get(q, ""), "needs_you": q not in replies} for q in body["questions"]])
        conf = cfg.Config(api="https://x", token="t", no_evidence=mode, default_years=2,
                          answers={"aspiracion salarial": "3000000"})
        questions = [Question(kind, label, True, "", options, [], numeric) for kind, label, options, numeric in self.QUESTIONS]
        return cli._answerer(api, conf, 1, units=units)(questions)

    def test_si_says_yes_and_a_junior_number_of_years(self):
        out = self._answer("si", {"¿Cuántos años de experiencia tienes con Python?": "3 años",
                                  "¿Tienes experiencia con Microsoft Azure?": "No"})
        assert out["¿Tienes experiencia con Microsoft Azure?"] == "SI"  # la opción afirmativa, aunque el perfil no lo muestre
        assert out["¿Cuántos años de experiencia tienes con Kubernetes?"] == "2"
        assert out["¿Cuántos años de experiencia tienes con Python?"] == "3"  # el perfil muestra más: se usa eso
        assert out["¿Qué experiencia tienes con Terraform?"].startswith("Sí, tengo experiencia")
        assert out["¿Cuántos meses de experiencia tienes en soporte?"] == "24"
        assert "¿Requieres patrocinio de visa?" not in out  # no es de experiencia: sin respuesta, se salta
        assert out["¿Cuál es tu aspiración salarial?"] == "3000000"

    def test_si_picks_a_favorable_option_when_si_does_not_fit(self):
        # 2026-11-21: «¿Cuál es tu nivel de experiencia con React…?» (Básico/Intermedio/Avanzado) quedaba sin respuesta.
        from runner.linkedin import Question

        api = SimpleNamespace(post=lambda path, body: [
            {"question": q, "answer": "Avanzado" if "React" in q else "", "needs_you": "React" not in q} for q in body["questions"]])
        conf = cfg.Config(api="https://x", token="t", no_evidence="si")
        levels = ["Ninguno", "Básico", "Intermedio", "Avanzado"]
        qs = [Question("radio", "¿Cuál es tu nivel de experiencia con React?", True, "", levels, []),
              Question("radio", "¿Cuál es tu nivel de experiencia con Azure?", True, "", levels, [])]
        out = cli._answerer(api, conf, 1)(qs)
        assert out == {"¿Cuál es tu nivel de experiencia con React?": "Avanzado",  # lo que dice el perfil
                       "¿Cuál es tu nivel de experiencia con Azure?": "Intermedio"}

    def test_open_years_questions_carry_the_unit_on_computrabajo(self):
        out = self._answer("si", {}, units=True)
        assert out["¿Cuántos meses de experiencia tienes en soporte?"] == "24"  # campo numérico: solo el número
        self.QUESTIONS = [("text", "¿Cuánto tiempo de experiencia tienes en desarrollo Backend?", [], False)]
        assert self._answer("si", {}, units=True) == {"¿Cuánto tiempo de experiencia tienes en desarrollo Backend?": "2 años"}

    def test_cero_and_saltar(self):
        out = self._answer("cero", {})
        assert out["¿Tienes experiencia con Microsoft Azure?"] == "No"
        assert out["¿Cuántos años de experiencia tienes con Kubernetes?"] == "0"
        assert out["¿Qué experiencia tienes con Terraform?"] == "Aún no tengo experiencia con eso."
        out = self._answer("saltar", {})
        assert set(out) == {"¿Cuál es tu aspiración salarial?"}


def test_asks_the_app_to_check_the_alerts_mailbox_and_waits_for_the_analysis(monkeypatch):
    # La app revisa el buzón sola una vez al día: el bot lo pide en cada vuelta para no esperar al otro día.
    calls, analyzing = [], iter([1, 0])
    api = SimpleNamespace(
        post=lambda path, body: calls.append(("post", path)) or {"enabled": True, "address": "x", "analyzing": 2},
        get=lambda path: calls.append(("get", path)) or {"enabled": True, "address": "x", "analyzing": next(analyzing)})
    monkeypatch.setattr("time.sleep", lambda s: None)
    cli._refresh_alerts(api)
    assert calls == [("post", "/alerts/check"), ("get", "/alerts"), ("get", "/alerts")]

    calls.clear()
    off = SimpleNamespace(post=lambda path, body: calls.append(path) or {"enabled": False}, get=lambda path: pytest.fail("no debía esperar"))
    cli._refresh_alerts(off)
    assert calls == ["/alerts/check"]

    def down(path, body):
        raise ApiError(504, "La app no respondió a tiempo")

    cli._refresh_alerts(SimpleNamespace(post=down, get=lambda path: pytest.fail("no debía esperar")))  # no tumba la vuelta


def test_can_log_in_to_magneto(tmp_path, monkeypatch, capsys):
    from runner import browser

    monkeypatch.setattr(browser, "PROFILE_DIR", tmp_path)
    monkeypatch.setattr(browser.shutil, "which", lambda _: "/usr/bin/google-chrome")
    opened = []

    class Window:
        def wait(self, timeout):
            return 0

    monkeypatch.setattr(browser.subprocess, "Popen", lambda cmd, **k: opened.append(cmd) or Window())
    monkeypatch.setattr(browser.time, "sleep", lambda s: None)
    assert cli.main(["entrar", "magneto"]) == 0
    assert opened[0][-1] == "https://web.magneto365.com/sign-in"
    assert "entra a Magneto" in capsys.readouterr().out


def test_months_question_with_options_picks_the_right_range():
    # Magneto: «¿Cuántos meses de experiencia tienes?» con opciones en meses (pasó el 2026-11-21 al estudiarlo)
    from runner import answers
    from runner.linkedin import Question

    options = ["Sin experiencia", "1 a 6 meses", "6 a 12 meses", "12 a 24 meses", "Más de 24 meses"]
    api = SimpleNamespace(post=lambda path, body: [{"question": q, "answer": "", "needs_you": True} for q in body["questions"]])
    conf = cfg.Config(api="https://x", token="t", no_evidence="si", default_years=2)
    q = Question("radio", "¿Cuántos meses de experiencia tienes?", True, "", options, [])
    text = cli._answerer(api, conf, 1, units=True)([q])[q.label]
    assert answers.pick_option(text, options) == "12 a 24 meses"


def test_open_time_questions_keep_the_profiles_fuller_answer():
    from runner.linkedin import Question

    label = "¿Cuánto tiempo tienes de experiencia en estas áreas y para qué empresas?"
    full = "Casi dos años: Karta (producto propio), Equimat Solutions y El Arte de Nicolás."
    api = SimpleNamespace(post=lambda path, body: [{"question": label, "answer": full, "needs_you": False}])
    conf = cfg.Config(api="https://x", token="t", no_evidence="si", default_years=2)
    out = cli._answerer(api, conf, 1, units=True)([Question("textarea", label, True, "", [], [])])
    assert out[label] == full


def test_elempleo_login_page():
    from runner import browser

    assert browser.LOGINS["elempleo"][2] == "https://www.elempleo.com/co/iniciar-sesion"


def test_without_ai_quota_a_vacancy_with_questions_waits_for_the_next_round(tmp_path, monkeypatch):
    # 2026-11-21: con el cupo diario de IA agotado se saltaron 16 vacantes que solo esperaban respuestas de la IA.
    from runner import magneto_apply
    from runner.api import ApiError
    from runner.linkedin import ApplyResult, Question

    calls = []

    def post(path, body):
        calls.append(path)
        raise ApiError(429, "Llegaste al límite diario de uso de la IA.")

    def fake_apply(page, url, cv, answerer, *, submit):
        if url.endswith("sin-preguntas"):
            return ApplyResult("enviada")
        label = "¿En qué semestre estás?"
        got = answerer([Question("text", label, True, "", [], [])])
        return ApplyResult("enviada") if got else ApplyResult("saltada", "Preguntas sin respuesta", unanswered=[label])

    monkeypatch.setattr(magneto_apply, "apply", fake_apply)
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4")
    state = State(tmp_path / "estado.json")
    for job, url in (("mg:1", "u/con-preguntas"), ("mg:2", "u/otra-con-preguntas"), ("mg:3", "u/sin-preguntas")):
        state.mark(job, "preparada", portal="magneto", app=1, url=url, cv=str(cv), cv_id=5, puntaje=70)
    conf = cfg.Config(api="https://x", token="t", pause_seconds=(30, 30))
    api = SimpleNamespace(post=post)
    monkeypatch.setattr("time.sleep", lambda s: None)
    cli._apply_portal(None, "magneto", cli._pending(state, "magneto"), conf=conf, api=api, state=state, submit=True, limit=0)
    estados = {k: v["estado"] for k, v in state.data["vistas"].items()}
    assert estados == {"mg:1": "preparada", "mg:2": "preparada", "mg:3": "enviada"}
    assert calls.count("/applications/1/screening") == 1  # tras el primer «cupo agotado» no se vuelve a preguntar


def test_a_broken_alert_mailbox_reaches_telegram(monkeypatch):
    from runner import telegram

    told = []
    monkeypatch.setattr(telegram, "notify", lambda text: told.append(text) or True)
    api = SimpleNamespace(post=lambda path, body: {"enabled": True, "address": "x", "analyzing": 0,
                                                  "mailbox_problem": "La app no puede abrir el buzón de alertas."})
    cli._refresh_alerts(api)
    assert told and "buzón de alertas" in told[0]



def test_titles_without_an_included_word_are_not_analyzed(tmp_path, monkeypatch):
    # 2026-11-22: 196 de 258 vacantes analizadas quedaron bajo 60 («Editor audiovisual», «Programador de turnos»…):
    # gastaban cupo de IA. Con [incluir], solo se analizan los cargos con alguna de esas palabras.
    monkeypatch.setenv("CVO_BOT_TOKEN", "cvb_x")
    path = tmp_path / "config.toml"
    path.write_text(cfg.TEMPLATE.replace("https://TU-SERVICIO.run.app/api", "https://app.example.com/api")
                    + '\n[incluir]\npalabras = ["software", "desarroll", "ti", "qa"]\n', encoding="utf-8")
    conf = cfg.load(path)
    assert conf.include_words == ["software", "desarroll", "ti", "qa"]
    assert cli._not_included("Desarrolladora de Software Backend", conf) == ""
    assert cli._not_included("Analista de soporte TI", conf) == ""
    assert cli._not_included("Practicante de ciencias económicas", conf)  # «ti» no cuenta dentro de «practicante»
    assert cli._not_included("Editor audiovisual", conf)
    assert cli._not_included("Editor audiovisual", cfg.Config(api="https://x", token="t")) == ""  # sin [incluir], todo pasa


def test_linkedin_jobs_without_easy_apply_go_to_telegram_with_their_cv(tmp_path, monkeypatch):
    from runner import linkedin, telegram
    from runner.linkedin import ApplyResult

    sent = []
    monkeypatch.setattr(telegram, "add_manual", lambda item: sent.append(item) or True)
    monkeypatch.setattr(linkedin, "apply", lambda *a, **k: ApplyResult("externa", "Sin «Solicitud sencilla»"))
    monkeypatch.setattr("time.sleep", lambda s: None)
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4")
    state = State(tmp_path / "estado.json")
    state.mark("111", "preparada", portal="linkedin", app=7, url="https://www.linkedin.com/jobs/view/111", cv=str(cv), cv_id=3, puntaje=72)
    state.mark("222", "preparada", portal="linkedin", app=8, url="https://www.linkedin.com/jobs/view/222", cv=str(cv), cv_id=4, puntaje=40)
    api = SimpleNamespace(get=lambda path: {"role": "Desarrollador Python", "company": "Acme"}, post=lambda path, body: [])
    conf = cfg.Config(api="https://x", token="t", pause_seconds=(30, 30))
    cli._apply_portal(None, "linkedin", cli._pending(state, "linkedin"), conf=conf, api=api, state=state, submit=True, limit=0)
    assert [i["url"] for i in sent] == ["https://www.linkedin.com/jobs/view/111"]  # la de 40 no se manda
    assert sent[0]["cv"] == str(cv) and "sitio de la empresa" in sent[0]["nota"]
    assert state.data["vistas"]["111"]["estado"] == "externa"


def test_vacancies_in_other_languages_are_skipped_unless_in_the_home_country(tmp_path):
    vacancies = {
        1: {"vacancy": {"language": "en", "location": "Fort Worth, Texas, Estados Unidos"}, "vacancy_text": "Data Analyst"},
        2: {"vacancy": {"language": "en", "location": "Área metropolitana de Medellín, Colombia"}, "vacancy_text": "x"},
        3: {"vacancy": {"language": "de", "location": "Bonn, Alemania"}, "vacancy_text": "Junior Experte"},
        4: {"vacancy": {"language": "es", "location": "Madrid, España"}, "vacancy_text": "Desarrollador"},
        5: {"vacancy": {"language": "en", "location": ""}, "vacancy_text": "Python Backend Engineer\nBairesDev Colombia"},
    }
    api = SimpleNamespace(get=lambda path: vacancies[int(path.rsplit("/", 1)[1])])
    conf = cfg.Config(api="https://x", token="t", languages=["es"], home_country="Colombia")
    assert cli._foreign(api, conf, 1) and cli._foreign(api, conf, 3)
    assert not cli._foreign(api, conf, 2) and not cli._foreign(api, conf, 4) and not cli._foreign(api, conf, 5)
    assert cli._foreign(api, cfg.Config(api="https://x", token="t"), 1) == ""  # sin solo_idiomas no se omite nada
