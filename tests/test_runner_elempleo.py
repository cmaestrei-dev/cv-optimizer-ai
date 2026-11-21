"""elempleo: búsqueda y oferta públicas (páginas de ejemplo, sin red) y el perfil del navegador del bot."""

import html
import json
import os
import socket
from datetime import date

import pytest

from runner import __main__ as cli
from runner import browser as bot_browser
from runner import elempleo
from runner.config import Search

TODAY = date(2026, 11, 21)
OFFER = "https://www.elempleo.com/co/ofertas-trabajo/practicante-ingenieria-en-sistemas-1886801108"


def card(job_id: int, title: str, company: str, city: str, when: str, modality: str = "") -> str:
    data = html.escape(json.dumps({"section": "SEARCH", "id": job_id, "title": title, "company": company,
                                   "location": city, "salary": "$1,5 a $2 millones"}), quote=True)
    url = f"/co/ofertas-trabajo/{elempleo.slug(title)}-{job_id}"
    return (f'<div class="col-md-12 result-item mb-3 bg-white" style="text-align: left;">'
            f'<div class="col-md-12 p-0 js-area-bind area-bind" data-url="{url}" data-ga4-offerdata="{data}">'
            f'<div class="js-work-modality hide">{modality}</div><a href="{url}">{title}</a>'
            f'<span class="info-publish-date"> {when} </span></div></div>')


RESULTS = "<html><body>" + "".join([
    card(1886801108, "Practicante ingeniería en sistemas", "Empresa confidencial", "Bogotá", "Hoy"),
    card(1886800596, "Desarrollador bizagi. remoto", "Cinte Colombia SAS", "Bogotá", "Hace 2 d&#237;as", "- Remoto"),
    card(1886799448, "Desarrollador backend (.net)", "Zemsania", "Cartagena", "Hace 1 semana", "- Hibrido"),
    card(1886799448, "Desarrollador backend (.net)", "Zemsania", "Cartagena", "Hace 1 semana", "- Hibrido"),  # repetida
]) + '<script id="hbtpl"><div class="col-md-12 result-item mb-3 bg-white">{{title}}</div></script></body></html>'


def test_search_url_uses_the_date_filter_and_the_remote_listing():
    url = elempleo.search_url(Search("Practicante Sistemas", "Colombia", 7, portal="elempleo"))
    assert url == "https://www.elempleo.com/co/ofertas-empleo/trabajo-practicante-sistemas?fecha=hace-1-semana"
    assert elempleo.search_url(Search("desarrollador", "Remoto", 1, portal="elempleo"), page=2) == (
        "https://www.elempleo.com/co/ofertas-empleo/trabajo-desarrollador-modalidad-remoto/2?fecha=hoy")
    assert elempleo.search_url(Search("qa", "Colombia", 30, portal="elempleo")).endswith("?fecha=hace-1-mes")


def test_cards_come_from_the_page_data_and_the_city_is_filtered():
    cards = elempleo.parse_cards(RESULTS, today=TODAY)
    assert [c.job_id for c in cards] == ["ee:1886801108", "ee:1886800596", "ee:1886799448"]  # sin la plantilla ni repetidas
    first = cards[0]
    assert first.company == "Confidencial" and first.place == "Bogotá" and first.posted == TODAY
    assert first.url == OFFER
    assert cards[1].posted == date(2026, 11, 19) and cards[2].posted == date(2026, 11, 14)
    near = elempleo.parse_cards(RESULTS, place="Cartagena", today=TODAY)
    assert [c.job_id for c in near] == ["ee:1886800596", "ee:1886799448"]  # en Cartagena o remota


POSTING = """<html><head><script type="application/ld+json">{"@type": "BreadcrumbList"}</script>
<script type="application/ld+json">{"@context": "https://schema.org/", "@type": "JobPosting",
 "title": "Practicante Ingeniería en Sistemas", "description": "Buscamos practicante.\\r\\n\\r\\n- Python\\r\\n- SQL",
 "datePosted": "2026-11-20", "validThrough": "2026-12-20"}</script></head><body>
<input type="hidden" class="js-config" data-jobofferconstraint-val="{&quot;PositionAreas&quot;:&quot;Sistemas y Tecnolog&#237;a&quot;,&quot;Cities&quot;:&quot;Bogot&#225;&quot;,&quot;RequiredExperince&quot;:&quot;0&quot;,&quot;Studylevel&quot;:&quot;Universitaria&quot;,&quot;ContractType&quot;:&quot;Aprendizaje&quot;}">
</body></html>"""


def test_posting_text_comes_from_the_job_posting_and_its_rules():
    text = elempleo.parse_posting(POSTING)
    assert text.startswith("Área: Sistemas y Tecnología · Ciudad: Bogotá · Contrato: Aprendizaje · Formación: Universitaria")
    assert "Experiencia requerida: sin experiencia" in text and "Buscamos practicante.\n- Python\n- SQL" in text
    assert elempleo.closes_on(POSTING) == date(2026, 12, 20)
    assert elempleo.parse_posting("<html></html>") == ""


def test_job_ids_from_elempleo_links():
    assert cli._job_id("elempleo", OFFER + "?icid=rec") == "ee:1886801108"
    assert cli.PLATFORM_PORTAL["elempleo"] == "elempleo" and cli._portal("elempleo") is elempleo


# --- El perfil del navegador del bot ---------------------------------------------------------------------------


def test_a_busy_profile_is_waited_for_and_a_stale_lock_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_browser, "PROFILE_DIR", tmp_path)
    assert bot_browser.owner_pid(tmp_path) is None
    os.symlink(f"{socket.gethostname()}-{os.getpid()}", tmp_path / "SingletonLock")  # un proceso vivo: este
    assert bot_browser.owner_pid(tmp_path) == os.getpid()
    with pytest.raises(bot_browser.ProfileBusyError):
        bot_browser.wait_free(wait_seconds=0)
    os.remove(tmp_path / "SingletonLock")
    os.symlink(f"{socket.gethostname()}-999999999", tmp_path / "SingletonLock")  # candado viejo
    assert bot_browser.owner_pid(tmp_path) is None
    bot_browser.wait_free(wait_seconds=0)


def test_the_profile_reopens_the_last_session_so_session_cookies_survive(tmp_path):
    (tmp_path / "Default").mkdir()
    prefs = tmp_path / "Default" / "Preferences"
    prefs.write_text(json.dumps({"profile": {"name": "bot"}, "session": {"restore_on_startup": 5}}))
    bot_browser._keep_sessions(tmp_path)
    assert json.loads(prefs.read_text()) == {"profile": {"name": "bot"}, "session": {"restore_on_startup": 1}}
    bot_browser._keep_sessions(tmp_path / "nuevo")  # perfil sin archivo todavía: no hace nada
