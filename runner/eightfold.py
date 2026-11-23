"""Vigilar el portal de empleo de una empresa en Eightfold (Mercado Libre) con su búsqueda PÚBLICA, sin sesión.

Verificado con Mercado Libre (2026-11-22):
- `GET <sitio>/api/pcsx/search?domain=<dominio>&location=<país>&start=<n>&sort_by=timestamp[&query=<texto>]` da 10
  ofertas por página (`data.positions`: id, name, locations, postedTs) y el total (`data.count`). Con «location»
  vienen también remotas de otros países: se deja solo las que tienen el país en `locations`.
- `GET <sitio>/api/pcsx/position_details?position_id=<id>&domain=<dominio>&hl=es` trae la descripción en HTML
  (`jobDescription`), `postedTs` y el enlace público `<sitio>/careers/job/<id>`.
- Postular pide la cuenta de la empresa: el bot no postula; la oferta le llega a la persona por Telegram con su CV.
"""

import re
import urllib.parse
from collections.abc import Callable
from datetime import date

from runner import watch

PAGE = 10
MAX_PAGES = 10  # 100 ofertas por búsqueda: Mercado Libre tenía 59 en Colombia

GetJson = Callable[[str], dict]


def _in_country(position: dict, country: str) -> bool:
    want = watch._norm(country).strip()
    return any(want in watch._norm(str(place)) for place in (position.get("locations") or []))


def listing(site, *, get: GetJson | None = None) -> list[tuple[str, str, str]]:
    """(id, cargo, enlace público) de las ofertas del país, de la más nueva a la más vieja."""
    get = get or watch.request_json
    out, seen = [], set()
    for term in site.terms or [""]:
        for page in range(MAX_PAGES):
            params = {"domain": site.domain, "location": site.country, "start": page * PAGE, "sort_by": "timestamp"}
            if term:
                params["query"] = term
            data = get(f"{site.base}/api/pcsx/search?" + urllib.parse.urlencode(params)).get("data") or {}
            positions = data.get("positions") or []
            for p in positions:
                job_id = str(p.get("id") or "")
                if job_id and job_id not in seen and _in_country(p, site.country):
                    seen.add(job_id)
                    out.append((job_id, str(p.get("name") or "").strip(), f"{site.base}/careers/job/{job_id}"))
            if len(positions) < PAGE or (page + 1) * PAGE >= int(data.get("count") or 0):
                break
            watch.pause(2, 4)
    return out


def posting(site, url: str, *, get: GetJson | None = None) -> dict:
    """Cargo, lugar, texto y fecha de una oferta (sin fecha de cierre: Eightfold no la publica)."""
    get = get or watch.request_json
    match = re.search(r"/careers/job/(\d+)", url)
    if not match:
        return {"title": "", "place": "", "text": "", "posted": None, "closes": None}
    params = {"position_id": match.group(1), "domain": site.domain, "hl": "es"}
    data = get(f"{site.base}/api/pcsx/position_details?" + urllib.parse.urlencode(params)).get("data") or {}
    posted = data.get("postedTs")
    return {"title": str(data.get("name") or "").strip(), "place": " · ".join(data.get("locations") or []),
            "text": watch.html_text(str(data.get("jobDescription") or "")),
            "posted": date.fromtimestamp(posted) if isinstance(posted, int | float) and posted > 0 else None,
            "closes": None}
