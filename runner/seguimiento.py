"""Seguimiento: qué pasó con las postulaciones en cada portal (solo lectura, con la sesión del navegador del bot).

Verificado el 2026-11-24 con las cuentas del dueño (pedido suyo: «revisa tú mismo mis plataformas»):
- Computrabajo: «Mis aplicaciones» (`/candidate/match?p=N`, 10 por página). Cada postulación es un `[data-match]`
  (id estable) con cargo, empresa, ciudad, estado («Postulado», «HdV Vista», «Finalista», «Proceso finalizado») y
  cuándo. Ojo: su correo «tu candidatura avanza» llegó también por procesos que la página ya daba por finalizados.
- elempleo: «Mis procesos» (`/co/estadisticas/mis-procesos/`, 20 por página; el selector `ResultsByPage` deja 100).
  Cada fila es `tr[id][data-job-offer-id]`; el estado de la persona está en «Mi proceso»
  (`estado-de-mi-proceso/<id>`): una línea de tiempo con fecha («Oferta publicada», «Postulación a oferta», …).
- Gupy: su API `private-api.gupy.io/selection-process/candidate/applications` (la página solo dibuja 12): estado y
  paso (1 de 5 es la inscripción).
- Magneto: «Mis procesos» por su API (`statusName`, p. ej. «Aplicación enviada»).
- AIRA (Falabella): `/list_applications`, una tabla con oferta, empresa, fecha y estado («Pendiente información»).
Nada se cambia en los portales. Un cambio (hoja de vida vista, avanza, se cierra) pasa a la app («En revisión» o
«Rechazada», con lo que dice el portal) cuando se sabe cuál postulación es, y llega por Telegram.
"""

import re
import time
from dataclasses import dataclass

from runner.answers import normalize

SENT, SEEN, ADVANCE, CLOSED = 0, 1, 2, -1
NAMES = {"computrabajo": "Computrabajo", "elempleo": "elempleo", "gupy": "Gupy", "magneto": "Magneto", "aira": "AIRA"}
CT = "https://candidato.co.computrabajo.com/candidate/match"
EE = "https://www.elempleo.com/co/estadisticas/mis-procesos/"
GUPY_PAGE, GUPY_API = "https://portal.gupy.io/my/applications", "private-api.gupy.io/selection-process/candidate/applications"
AIRA = "https://falabella.airavirtual.com/list_applications"
_CLOSED = re.compile(r"no seleccionad|no continua|descartad|rechazad|finalizad|cerrad|reprov|declin|desist", re.I)
_ADVANCE = re.compile(r"finalista|entrevista|seleccionad|contratad|hired|approved", re.I)
_DATE = re.compile(r"^\d{1,2} \w{3,4}\.? - \d{4}$")


@dataclass(frozen=True)
class Seen:
    portal: str
    key: str  # id estable de la postulación en el portal
    title: str
    company: str
    status: str  # como lo dice el portal
    level: int  # SENT, SEEN, ADVANCE o CLOSED
    ref: str = ""  # la clave de la vacante en el estado del bot («ee:…», «mg:…»), si se sabe


def _level(status: str, sent: re.Pattern) -> int:
    if sent.search(normalize(status)):
        return SENT
    if _CLOSED.search(normalize(status)):
        return CLOSED
    return ADVANCE if _ADVANCE.search(normalize(status)) else SEEN


# --- Lo que dice cada portal (sin red: se prueba con lo que devolvieron las páginas reales) ---

def parse_computrabajo(items: list[tuple[str, str]]) -> list[Seen]:
    """`items`: (data-match, texto de la tarjeta): cargo, empresa, ciudad, estado, cuándo, «N candidatos aplicados»."""
    states = {"postulado": SENT, "hdv vista": SEEN, "finalista": ADVANCE, "proceso finalizado": CLOSED}
    out = []
    for key, text in items:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        status = next((line for line in lines if normalize(line) in states), "")
        if not key or not lines or not status:
            continue
        before = lines[1:lines.index(status)]  # empresa (si la muestra, con su calificación «4,5») y ciudad
        is_city = len(before) == 1 and re.search(r",\s+[A-ZÁÉÍÓÚ]", before[0])  # «Cartagena de Indias, Bolívar»
        company = re.sub(r"\s+\d,\d$", "", before[0]) if before and not is_city else ""
        out.append(Seen("computrabajo", key, lines[0], company, status, states[normalize(status)]))
    return out


def elempleo_step(text: str) -> str:
    """El último paso con fecha de «Estado de mi proceso» («Postulación a oferta», …)."""
    lines = [line.strip() for line in text.split("Estado de mi proceso")[-1].splitlines() if line.strip()]
    if "Siguiente" in lines:
        lines = lines[:lines.index("Siguiente")]
    steps, label = [], []
    for line in lines:
        if _DATE.match(line):
            if label:
                steps.append(" ".join(label))
            label = []
        elif line not in ("Eliminar postulación",):
            label.append(line)
    return steps[-1] if steps else ""


def parse_elempleo(rows: list[dict]) -> list[Seen]:
    """`rows`: {id, offer, title, company, step} de «Mis procesos» con el paso de «Mi proceso»."""
    sent = re.compile(r"^(postulacion a oferta|oferta publicada)$")
    return [Seen("elempleo", r["id"], r["title"], r["company"], r["step"], _level(r["step"], sent), f"ee:{r['offer']}")
            for r in rows if r.get("id") and r.get("step")]


def parse_gupy(data: dict) -> list[Seen]:
    out = []
    for row in (data or {}).get("results") or []:
        status, step, steps = row.get("applicationStatus") or "", row.get("jobStepCurrent") or 1, row.get("jobStepCount") or 0
        if status == "in_process":
            level, text = (SENT if step <= 1 else ADVANCE), f"paso {step} de {steps}"
        else:
            level, text = (ADVANCE if _ADVANCE.search(status) else CLOSED), status
        out.append(Seen("gupy", str(row.get("applicationId")), (row.get("jobName") or "").strip(),
                        row.get("careerPageName") or "", text, level))
    return out


def parse_magneto(data: dict) -> list[Seen]:
    sent = re.compile(r"aplicacion enviada")
    return [Seen("magneto", str(r.get("id")), (r.get("title") or "").strip(), r.get("companyName") or "",
                 r.get("statusName") or "", _level(r.get("statusName") or "", sent), f"mg:{r.get('id')}")
            for r in (data or {}).get("rows") or [] if r.get("id") and r.get("statusName")]


def parse_aira(rows: list[list[str]]) -> list[Seen]:
    """`rows`: celdas de la tabla (vacía, oferta, empresa, fecha, estado, acciones)."""
    sent = re.compile(r"pendiente informacion|postulad|enviad")
    out = []
    for cells in rows:
        if len(cells) < 5 or not cells[1] or not cells[4] or cells[1] == "Oferta":
            continue
        out.append(Seen("aira", f"{normalize(cells[1])}|{normalize(cells[2])}", cells[1], cells[2], cells[4],
                        _level(cells[4], sent)))
    return out


# --- Leer cada portal con el navegador del bot ---

def read_computrabajo(page, *, pages: int = 15) -> list[Seen]:
    items: list[tuple[str, str]] = []
    for n in range(1, pages + 1):
        page.goto(f"{CT}?p={n}", wait_until="domcontentloaded")
        time.sleep(4)
        found = [(el.get_attribute("data-match") or "", el.inner_text()) for el in page.locator("[data-match]").all()]
        if not found or {k for k, _ in found} <= {k for k, _ in items}:  # se acabó (o repite la última página)
            break
        items += found
    return parse_computrabajo(items)


def read_elempleo(page, known: dict, *, details: int = 25) -> list[Seen]:
    """Los pasos de cada proceso. Se abren primero los que aún no han pasado de «Postulación a oferta» (los demás ya
    avisaron) y como mucho `details` por vuelta, para no recorrer 50 páginas cada vez."""
    page.goto(EE, wait_until="domcontentloaded")
    time.sleep(5)
    if page.locator("#ResultsByPage").count():
        page.locator("#ResultsByPage").select_option("100")
        time.sleep(5)
    # Con 100 por página, el cargo queda como texto de la primera celda (sin enlace y con «data-job-offer-title» vacío).
    rows = page.evaluate("""() => [...document.querySelectorAll('tr[id][data-job-offer-id]')].map(tr => {
        const cells = tr.querySelectorAll('td');
        return {id: tr.id, offer: tr.getAttribute('data-job-offer-id'),
                title: ((cells[0] || {}).innerText || '').replace(/Mi proceso|\\|/g, '').trim(),
                company: ((cells[1] || {}).innerText || '').trim()}; })""")
    pending = sorted(rows, key=lambda r: (known.get(f"elempleo|{r['id']}", {}).get("level", SENT) != SENT,
                                          known.get(f"elempleo|{r['id']}", {}).get("checked", "")))
    out = []
    for row in pending[:details]:
        page.goto(f"https://www.elempleo.com/co/estadisticas/estado-de-mi-proceso/{row['id']}", wait_until="domcontentloaded")
        time.sleep(3)
        out += parse_elempleo([{**row, "step": elempleo_step(page.inner_text("body"))}])
    return out


def read_gupy(page) -> list[Seen]:
    with page.expect_response(lambda r: GUPY_API in r.url and r.request.method == "GET", timeout=40_000) as info:
        page.goto(GUPY_PAGE, wait_until="domcontentloaded")
    return parse_gupy(info.value.json())


def read_magneto(page) -> list[Seen]:
    from runner import magneto_apply as mg

    session = mg.Session(page)
    page.goto("https://www.magneto365.com/co", wait_until="domcontentloaded")
    time.sleep(3)
    if not session.renew():
        return []
    status, data = session.get(mg.PROCESSES)
    return parse_magneto(data) if status == 200 and isinstance(data, dict) else []


def read_aira(page) -> list[Seen]:
    page.goto(AIRA, wait_until="domcontentloaded")
    time.sleep(6)
    if "/register" in page.url or page.locator("input[type=password]:visible").count():
        return []
    return parse_aira(page.evaluate("""() => [...document.querySelectorAll('table tr')].map(tr =>
        [...tr.querySelectorAll('td, th')].map(c => c.innerText.trim().replace(/\\s+/g, ' ')))"""))


READERS = {"computrabajo": read_computrabajo, "gupy": read_gupy, "magneto": read_magneto, "aira": read_aira}


# --- Qué cambió y qué se hace con eso ---

def compare(previous: dict, seen: list[Seen], *, now: str = "") -> tuple[list[tuple[Seen, dict | None]], dict]:
    """Los cambios que importan (todo lo que no es «enviada») y el estado nuevo para guardar."""
    current, changes = dict(previous), []
    for s in seen:
        key = f"{s.portal}|{s.key}"
        before = previous.get(key)
        current[key] = {"status": s.status, "level": s.level, "title": s.title, "company": s.company, "checked": now}
        if s.level != SENT and (before is None or before.get("status") != s.status):
            changes.append((s, before))
    return changes, current


def _same(application: dict, s: Seen) -> bool:
    role, company = normalize(application.get("role", "")), normalize(application.get("company", ""))
    title, other = normalize(s.title), normalize(s.company)
    return role == title and (not other or not company or other in company or company in other)


def match(applications: list[dict], s: Seen, refs: dict[str, int]) -> dict | None:
    """La postulación de la app: por la vacante que guardó el bot (`refs`: «ee:…» → id) o, si hay una sola, por cargo
    y empresa."""
    if s.ref and s.ref in refs:
        return next((a for a in applications if a["id"] == refs[s.ref]), None)
    found = [a for a in applications if _same(a, s)]
    return found[0] if len(found) == 1 else None


def update_app(api, changes: list[tuple[Seen, dict | None]], applications: list[dict], refs: dict[str, int]) -> int:
    """«En revisión» si el portal muestra que avanzó; «Rechazada» si se cerró. Nunca hacia atrás."""
    moved = 0
    for s, _ in changes:
        application = match(applications, s, refs)
        if application is None:
            continue
        note = f"{NAMES.get(s.portal, s.portal)}: {s.status}"
        target = "rechazada" if s.level == CLOSED else "en_revision"
        if application["status"] == "postulada" or (target == "rechazada" and application["status"] == "en_revision"):
            api.post(f"/applications/{application['id']}/status", {"status": target, "note": note})
            application["status"] = target
            moved += 1
        elif application["status"] in ("en_revision", "entrevista"):
            api.post(f"/applications/{application['id']}/notes", {"note": note})
    return moved


def notice(changes: list[tuple[Seen, dict | None]], limit: int = 15) -> str:
    if not changes:
        return ""
    lines = [f"• {NAMES.get(s.portal, s.portal)}: {s.title}" + (f" ({s.company})" if s.company else "") + f" → {s.status}"
             for s, _ in sorted(changes, key=lambda c: -c[0].level)]
    more = f"\n… y {len(lines) - limit} más" if len(lines) > limit else ""
    return "Novedades en tus postulaciones:\n" + "\n".join(lines[:limit]) + more
