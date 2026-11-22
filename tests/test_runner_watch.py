"""Vigilar portales de empresas (SuccessFactors): leer resultados, filtrar por cargo y avisar solo lo nuevo."""

import pytest

from runner import watch

PAGE = """
<a class="jobTitle-link" href="/bancolombia/job/Etipani-Ingenieroa-Software-Backend-%28Junior%29-COL/1451777800/">Ingeniero/a Software Backend (Junior)</a>
<a class="jobTitle-link" href="/bancolombia/job/Etipani-Ingenieroa-Software-Backend-%28Junior%29-COL/1451777800/">Ingeniero/a Software Backend (Junior)</a>
<a class="jobTitle-link" href="/bancolombia/job/X-ANALISTA-III-DE-DATOS/1400000001/">ANALISTA III DE DATOS</a>
<a class="jobTitle-link" href="/bancolombia/job/Y-Practicante-en-Tecnologia/1400000002/">Practicante en Tecnología</a>
<a class="jobTitle-link" href="/bancolombia/job/Z-Asesor-Comercial/1400000003/">Asesor/a Comercial</a>
<a class="jobTitle-link" href="/bancolombia/job/W-Practicante-Economia/1400000004/">Practicante Universitario/a de Ciencias Económicas</a>
"""
SITE = watch.Site(name="Bancolombia", base="https://empleo.grupobancolombia.com", terms=["software"])


def test_parse_and_match():
    rows = watch.parse(PAGE, SITE.base)
    assert [r[0] for r in rows] == ["1451777800", "1400000001", "1400000002", "1400000003", "1400000004"]
    assert rows[0][2].startswith("https://empleo.grupobancolombia.com/bancolombia/job/")
    fits = [title for _, title, _ in rows if watch.matches(SITE, title)]
    assert fits == ["Ingeniero/a Software Backend (Junior)", "Practicante en Tecnología"]  # sin «III», comerciales ni economía


def test_only_new_fitting_offers_are_reported():
    data, calls = {}, []
    get = lambda url: calls.append(url) or PAGE  # noqa: E731
    first = watch.check([SITE], data, get=get)
    assert [n["cargo"] for n in first] == ["Ingeniero/a Software Backend (Junior)", "Practicante en Tecnología"]
    assert "q=software" in calls[0] and len(data["vigiladas"]) == 5
    assert watch.check([SITE], data, get=get) == []  # ya vistas: no se repite el aviso
    assert "te llegan aparte, con su CV" in watch.notice(first)


def test_sites_come_from_the_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[[vigilar]]\nnombre = "Ecopetrol"\nsitio = "https://jobs.ecopetrol.com.co/"\nbuscar = ["practicante"]\n',
                    encoding="utf-8")
    (site,) = watch.load_sites(path)
    assert site.base == "https://jobs.ecopetrol.com.co" and site.terms == ["practicante"] and "software" in site.include
    assert site.min_score == 60


def test_short_words_match_whole_words_only():
    assert not watch.matches(SITE, "Practicante de Ciencias Económicas")  # «ti» dentro de «practicante»
    assert watch.matches(SITE, "Analista de Soporte TI")
    assert not watch.matches(SITE, "Analista III de Datos") and watch.matches(SITE, "Analista de Datos")


JOB = """<div class="jobDisplayShell" itemscope="itemscope" itemtype="http://schema.org/JobPosting">
<span itemprop="jobLocation"><span itemprop="address"><meta itemprop="addressLocality" content="Medellín">
<meta itemprop="addressCountry" content="CO"></span></span>
<meta itemprop="datePosted" content="Wed Nov 18 00:00:00 UTC 2026"><meta itemprop="validThrough" content="Tue Nov 24 05:00:00 UTC 2026">
<h1 id="job-title" itemprop="title">Ingeniero/a Software Backend (Junior)</h1>
<span itemprop="description" class="jobdescription"><p><span style="color:dimgray"><strong>Ubicación:</strong> Medellín.</span></p>
<ul><li>Java y Spring Boot</li><li>APIs REST</li></ul></span>
<p>Fuera de la descripción</p></div>"""


def test_posting_reads_the_public_offer():
    info = watch.posting(JOB)
    assert info["title"] == "Ingeniero/a Software Backend (Junior)" and info["place"] == "Medellín, CO"
    assert info["text"] == "Ubicación: Medellín.\n- Java y Spring Boot\n- APIs REST"  # sin lo que sigue a la descripción
    assert str(info["posted"]) == "2026-11-18" and str(info["closes"]) == "2026-11-24"


class FakeApi:
    def __init__(self, score=75, fail=None):
        self.score, self.fail, self.discarded, self.added = score, fail, [], []

    def add_vacancy(self, *, text, url, posted):
        from runner.api import ApiError, Vacancy

        if self.fail:
            raise ApiError(self.fail, "Llegaste al límite diario de uso de la IA.")
        self.added.append((text, url, posted))
        return Vacancy(id=len(self.added), created=True, role="Ingeniero/a Software Backend (Junior)", company="Bancolombia",
                       score=self.score, missing=[])

    def post(self, path, body):
        self.discarded.append((path, body))

    def make_cv(self, app_id):
        return {"id": 9, "filename": "Camilo_Maestre_Ingeniero_Software.pdf"}

    def download_cv(self, cv_id, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF-1.4")
        return dest


def watched_state(tmp_path, monkeypatch):
    from runner import __main__ as cli
    from runner import config as cfg
    from runner.state import State

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(watch, "fetch", lambda url: JOB)
    state = State(tmp_path / "estado.json")
    state.data["vigiladas"] = {
        "Bancolombia:1451777800": {"cargo": "Ingeniero/a Software Backend (Junior)", "url": "https://e/job/1451777800/", "encaja": True},
        "Bancolombia:1400000004": {"cargo": "Practicante Universitario/a de Ciencias Económicas", "url": "https://e/job/4/", "encaja": True},
        "Bancolombia:1400000003": {"cargo": "Asesor/a Comercial", "url": "https://e/job/3/", "encaja": False},
    }
    return cli, state


def test_fitting_offers_get_their_cv_and_go_to_telegram(tmp_path, monkeypatch):
    from runner import telegram

    cli, state = watched_state(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(telegram, "add_manual", lambda item: sent.append(item) or True)
    api = FakeApi(score=75)
    assert cli._prepare_watched(api, state, [SITE]) == 1
    (item,) = sent
    assert item["empresa"] == "Bancolombia" and item["puntaje"] == 75 and item["cv"].endswith(".pdf")
    assert "captcha" in item["nota"] and "24/11/2026" in item["nota"]
    assert api.added[0][0].startswith("Ingeniero/a Software Backend (Junior)\nBancolombia\nMedellín, CO")
    vistas = state.data["vigiladas"]
    assert vistas["Bancolombia:1451777800"]["app"] == 1
    assert vistas["Bancolombia:1400000004"]["listo"] == "no_encaja"  # anotada con reglas viejas: no gasta IA
    assert cli._prepare_watched(api, state, [SITE]) == 0 and len(api.added) == 1  # nunca dos veces


def test_low_scores_are_discarded_and_no_quota_retries_later(tmp_path, monkeypatch):
    from runner import telegram

    cli, state = watched_state(tmp_path, monkeypatch)
    monkeypatch.setattr(telegram, "add_manual", lambda item: pytest.fail("no debía enviarse"))
    assert cli._prepare_watched(FakeApi(fail=429), state, [SITE]) == 0
    assert "app" not in state.data["vigiladas"]["Bancolombia:1451777800"]  # sin cupo de IA: queda para otra vuelta
    low = FakeApi(score=40)
    assert cli._prepare_watched(low, state, [SITE]) == 0
    assert low.discarded and "compatibilidad 40 (mínimo 60)" in low.discarded[0][1]["note"]



def test_a_site_with_postular_needs_its_login_and_profile(tmp_path):
    from runner import config as cfg

    base = '[[vigilar]]\nnombre = "Bancolombia"\nsitio = "https://empleo.grupobancolombia.com"\nbuscar = ["software"]\n'
    path = tmp_path / "config.toml"
    path.write_text(base + "postular = true\n", encoding="utf-8")
    with pytest.raises(cfg.ConfigError):
        watch.load_sites(path)
    path.write_text(base + 'postular = true\nacceso = "https://career8.successfactors.com/career?company=X"\n'
                    'perfil = "https://career8.successfactors.com/portalcareer?company=X&navBarLevel=MY_PROFILE"\n'
                    'firma = "Camilo Andres Maestre Iglesias"\n[vigilar.respuestas]\n"como te enteraste" = "Portal de empleo"\n',
                    encoding="utf-8")
    (site,) = watch.load_sites(path)
    assert site.apply and site.signature.startswith("Camilo") and site.answers == {"como te enteraste": "Portal de empleo"}


def test_offers_of_a_postular_site_wait_for_the_batch_with_their_cv(tmp_path, monkeypatch):
    from dataclasses import replace

    from runner import telegram

    cli, state = watched_state(tmp_path, monkeypatch)
    told = []
    monkeypatch.setattr(telegram, "add_manual", lambda item: pytest.fail("no debía ir como manual"))
    monkeypatch.setattr(telegram, "notify", lambda text: told.append(text) or True)
    site = replace(SITE, apply=True, login_url="https://login", profile_url="https://perfil", signature="Camilo")
    assert cli._prepare_watched(FakeApi(score=75), state, [site]) == 0
    rec = state.data["vigiladas"]["Bancolombia:1451777800"]
    assert rec["estado"] == "preparada" and rec["cv"].endswith(".pdf") and rec["cv_id"] == 9
    assert told and "python -m runner lote bancolombia" in told[0]
    assert [k for k, _ in cli._batch_pending(state, site)] == ["Bancolombia:1451777800"]
    rec["estado"] = "enviada"
    assert cli._batch_pending(state, site) == []  # nunca dos veces
