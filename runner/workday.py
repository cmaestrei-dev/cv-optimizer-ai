"""Vigilar el portal de empleo de una empresa en Workday (Accenture, Unisys, DXC…) con su búsqueda PÚBLICA, sin sesión.

`sitio` es la página de empleos de la empresa: `https://<host>.myworkdayjobs.com/<sitio>` (p. ej.,
`https://accenture.wd103.myworkdayjobs.com/AccentureCareers`). Su API pública (la que usa esa página):
- `POST https://<host>.myworkdayjobs.com/wday/cxs/<tenant>/<sitio>/jobs` con
  `{"appliedFacets": {...}, "limit": 20, "offset": n, "searchText": ""}` da 20 ofertas por página (`jobPostings`:
  title, externalPath, locationsText, postedOn) y el total; las facetas (`facets`) traen el id de cada país, que se
  busca por su nombre (`pais`). `tenant` suele ser la primera parte del host («accenture»).
- `GET …/wday/cxs/<tenant>/<sitio><externalPath>` trae la oferta (`jobPostingInfo`: jobDescription en HTML,
  startDate, endDate, location). La oferta pública es `https://<host>.myworkdayjobs.com/<sitio><externalPath>`.
- Frena rápido (HTTP 429 tras unas pocas consultas seguidas): pausas largas y, si frena, se sigue en la próxima vuelta.
Postular pide una cuenta en cada empresa, que crea la persona: el bot no postula; la oferta llega por Telegram con su CV.
"""

import re
import urllib.parse
from collections.abc import Callable
from datetime import date

from runner import watch

PAGE = 20
MAX_PAGES = 6
_LOCALE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")

PostJson = Callable[..., dict]


def _parts(site) -> tuple[str, str]:
    """(origen, dirección de la API) a partir de la página de empleos (`sitio`)."""
    url = urllib.parse.urlsplit(site.base)
    path = [p for p in url.path.split("/") if p and not _LOCALE.match(p)]
    if not url.hostname or not path:
        raise ValueError(f"«sitio» de Workday sin la página de empleos: {site.base}")
    tenant = site.tenant or url.hostname.split(".")[0]
    origin = f"https://{url.hostname}"
    return f"{origin}/{path[0]}", f"{origin}/wday/cxs/{tenant}/{path[0]}"


def _country_facet(facets: list, country: str) -> tuple[str, str] | None:
    """(parámetro, id) de la faceta del país, buscada por nombre (también dentro de grupos de facetas)."""
    want = watch._norm(country).strip()
    for facet in facets or []:
        for value in facet.get("values") or []:
            if value.get("facetParameter"):  # grupo anidado (p. ej., «locationMainGroup»)
                if found := _country_facet([value], country):
                    return found
            elif watch._norm(str(value.get("descriptor") or "")).strip() == want and value.get("id"):
                return facet["facetParameter"], value["id"]
    return None


def listing(site, *, post: PostJson | None = None) -> list[tuple[str, str, str]]:
    """(id, cargo, enlace público) de las ofertas del país."""
    post = post or watch.request_json
    public, api = _parts(site)
    first = post(f"{api}/jobs", {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
    facet = _country_facet(first.get("facets") or [], site.country)
    if not facet:
        raise ValueError(f"no encontré «{site.country}» entre los países del portal")
    out, seen = [], set()
    for term in site.terms or [""]:
        for page in range(MAX_PAGES):
            watch.pause(6, 10)
            data = post(f"{api}/jobs", {"appliedFacets": {facet[0]: [facet[1]]}, "limit": PAGE,
                                        "offset": page * PAGE, "searchText": term})
            jobs = data.get("jobPostings") or []
            for job in jobs:
                path = str(job.get("externalPath") or "")
                job_id = (job.get("bulletFields") or [""])[0] or path.rsplit("_", 1)[-1]
                if path and job_id and job_id not in seen:
                    seen.add(job_id)
                    out.append((job_id, str(job.get("title") or "").strip(), public + path))
            if len(jobs) < PAGE or (page + 1) * PAGE >= int(data.get("total") or 0):
                break
    return out


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def posting(site, url: str, *, get: PostJson | None = None) -> dict:
    """Cargo, lugar, texto, fecha de publicación y de cierre de una oferta pública."""
    get = get or watch.request_json
    public, api = _parts(site)
    path = url.split(public, 1)[1] if url.startswith(public) else urllib.parse.urlsplit(url).path
    path = path[path.find("/job/"):] if "/job/" in path else path
    info = get(api + path).get("jobPostingInfo") or {}
    return {"title": str(info.get("title") or "").strip(), "place": str(info.get("location") or "").strip(),
            "text": watch.html_text(str(info.get("jobDescription") or "")), "posted": _day(info.get("startDate")),
            "closes": _day(info.get("endDate"))}
