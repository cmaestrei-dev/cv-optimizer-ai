"""Postular con la «Solicitud sencilla» de LinkedIn en el navegador del bot (con la sesión de la persona).

Todo se ubica por roles y nombres accesibles («Solicitud sencilla», el diálogo, «Siguiente», «Revisar», «Enviar
solicitud»): desde 2026 las clases de LinkedIn son aleatorias. Reglas:
- Solo se llena lo obligatorio que esté vacío; lo que LinkedIn ya trae (respuestas anteriores de la persona) se deja,
  salvo los años de experiencia: esos se responden siempre de nuevo (decisión del dueño, 2026-11-24: LinkedIn traía
  «3 años de Java» de una respuesta vieja).
- Si algo obligatorio no tiene respuesta, se descarta la solicitud y la vacante se salta: nunca se responde al azar.
- «Seguir a la empresa» se desmarca. En modo prueba se llega a la revisión y se descarta sin enviar.
- Ante una verificación (checkpoint, captcha, tope de LinkedIn) se detiene todo. El tope es un aviso corto; una oferta
  cuya descripción hable de límites no cuenta (una así frenó LinkedIn del 22 al 24-11-2026).
- Diseño de 2026-11 (verificado el 24 con ofertas reales, sin enviar): hay un botón «Solicitud sencilla» oculto además
  del visible; pulsarlo cambia la dirección (no se espera esa navegación); los diálogos son `<dialog open>` apilados
  (la X del formulario abre «¿Quieres guardar esta solicitud?» encima: ahí se pulsa «Descartar»); los radios de las
  preguntas llevan la pregunta en su aria-label, la etiqueta vacía, el texto de la opción al lado y van fuera de la
  pantalla (se marcan con su propio clic). Los CV de la lista llevan su nombre de archivo en el aria-label.
"""

import contextlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from runner.answers import asks_experience, is_years, pick_option

EASY = re.compile(r"^(solicitud sencilla|easy apply)", re.I)
NAV = re.compile(r"^(siguiente|next|continuar|continue|revisar|review|enviar solicitud|submit application)", re.I)
SUBMIT = re.compile(r"^(enviar solicitud|submit application)", re.I)
SENT = re.compile(r"(se envi[oó] tu solicitud|tu solicitud se (ha )?envi[oó]|se ha enviado tu solicitud|solicitud enviada"
                  r"|application (was )?sent|your application was sent)", re.I)
APPLIED = re.compile(r"^(postulado|solicitado|applied|solicitud enviada)\b", re.I)
LIMIT = re.compile(r"(l[ií]mite diario|daily (application )?limit|alcanzado el l[ií]mite (diario|de (las )?solicitudes|de postulaciones)|"
                   r"reached [^.]{0,40}\b(application|apply|daily)[^.]{0,20}\blimit|limit for today)", re.I)
CLOSED = re.compile(r"(ya no se aceptan solicitudes|no longer accepting applications)", re.I)
FOLLOW = re.compile(r"(seguir a|follow )", re.I)
CHALLENGE_URL = ("/checkpoint", "/authwall", "/uas/login", "/login")

# Campos de la página actual: pregunta (nombre accesible), tipo, si es obligatorio, valor y opciones.
_FIELDS_JS = """(dialog) => {
  const labelOf = (el) => (el.getAttribute('aria-label')
      || (el.id && dialog.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText)
      || el.closest('fieldset')?.querySelector('legend')?.innerText || '').replace(/\\s+/g, ' ').trim();
  const out = [];
  const radios = new Map();
  dialog.querySelectorAll('input, select, textarea').forEach((el, i) => {
    if (el.type === 'hidden' || el.type === 'file' || el.disabled) return;
    el.setAttribute('data-cvo', String(i));
    const required = el.required || el.getAttribute('aria-required') === 'true'
      || /\\*\\s*$/.test(labelOf(el)) || !!el.closest('fieldset[aria-required=true]');
    if (el.type === 'radio') {
      // Desde 2026-11: cada radio trae la pregunta en su aria-label, la etiqueta va vacía y el texto de la opción
      // («Yes», «No») está al lado, en el contenedor más grande que solo tiene ese radio.
      const key = el.name || labelOf(el);
      const asked = el.getAttribute('aria-label') || '';
      const legend = el.closest('fieldset')?.querySelector('legend')?.innerText?.replace(/\\s+/g, ' ').trim()
        || ([...dialog.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)].every(r => r.getAttribute('aria-label') === asked) && asked)
        || key;
      const group = radios.get(key) || {kind: 'radio', key, label: legend, required: false, value: '', options: [], ids: []};
      let box = el;
      while (box.parentElement && box.parentElement !== dialog && box.parentElement.querySelectorAll('input[type=radio]').length === 1) box = box.parentElement;
      const text = (el.id && dialog.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText?.trim())
        || (box !== el && box.innerText.replace(/\\s+/g, ' ').trim()) || el.value;
      if (asked && legend === asked) group.required = true;  // pregunta de la empresa: LinkedIn no deja avanzar sin ella
      group.options.push(text); group.ids.push(String(i));
      if (el.checked) group.value = text;
      group.required = group.required || required;
      radios.set(key, group);
      return;
    }
    const kind = el.tagName === 'SELECT' ? 'select' : el.type === 'checkbox' ? 'checkbox' : el.tagName === 'TEXTAREA' ? 'textarea' : 'text';
    const value = kind === 'select' ? (el.selectedIndex > 0 ? el.options[el.selectedIndex].text.trim() : '')
                : kind === 'checkbox' ? (el.checked ? 'true' : '') : (el.value || '').trim();
    out.push({kind, key: String(i), label: labelOf(el), required, value,
              options: kind === 'select' ? [...el.options].map(o => o.text.trim()) : [], ids: [String(i)],
              numeric: el.type === 'number' || el.inputMode === 'numeric' || /a[nñ]os|years|n[uú]mero|number/i.test(labelOf(el))});
  });
  return out.concat([...radios.values()]);
}"""


@dataclass
class Question:
    kind: str
    label: str
    required: bool
    value: str
    options: list[str]
    ids: list[str]
    numeric: bool = False


@dataclass
class ApplyResult:
    status: str  # enviada | revisada | saltada | ya_postulada | externa | verificacion | tope | perfil | error
    detail: str = ""
    unanswered: list[str] = field(default_factory=list)
    screenshot: str = ""
    follow_up: str = ""  # algo que solo la persona puede hacer después (p. ej. seguir en el sitio de la empresa)


Answerer = Callable[[list[Question]], dict[str, str]]


def _challenge(page) -> bool:
    if any(part in page.url for part in CHALLENGE_URL):
        return True
    return page.locator("iframe[src*='captcha'], iframe[title*='captcha' i]").count() > 0


def _applied(page) -> bool:
    """La vacante ya figura como postulada («Postulado hace 1 minuto», «Solicitado», «Applied»; desde 2026-11,
    «Solicitud enviada justo ahora»)."""
    return bool(page.get_by_role("button", name=APPLIED).count()
                or page.get_by_text(re.compile(r"^(Postulado|Solicitado|Applied|Solicitud enviada)\b")).count())


def _nav_button(dialog):
    return dialog.get_by_role("button", name=NAV).last


def _wait_ready(dialog, timeout: float = 60) -> bool:
    """El formulario carga despacio con conexiones lentas: se espera a que aparezca su botón de avanzar."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _nav_button(dialog).count():
            return True
        time.sleep(1)
    return False


def _questions(dialog) -> list[Question]:
    return [Question(q["kind"], q["label"], q["required"], q["value"], q["options"], q["ids"], q.get("numeric", False))
            for q in dialog.evaluate(_FIELDS_JS)]


def _missing(questions: list[Question]) -> list[Question]:
    return [q for q in questions if q.required and not q.value and q.kind != "checkbox"]


def _saved_years(questions: list[Question]) -> list[Question]:
    """Años de experiencia que LinkedIn ya trae llenos (respuestas viejas): se vuelven a responder."""
    return [q for q in questions if q.value and q.kind != "checkbox"
            and (is_years(q.label) or (q.numeric and asks_experience(q.label)))]


def _fill(dialog, q: Question, answer: str) -> bool:
    target = dialog.locator(f"[data-cvo='{q.ids[0]}']")
    if q.kind in ("text", "textarea"):
        target.fill(answer)
        return True
    if q.kind == "select":
        option = pick_option(answer, q.options)
        if option is None:
            return False
        target.select_option(label=option)
        return True
    if q.kind == "radio":
        option = pick_option(answer, q.options)
        if option is None:
            return False
        radio = dialog.locator(f"[data-cvo='{q.ids[q.options.index(option)]}']")
        try:
            radio.check(force=True, timeout=5_000)
        except Exception:  # noqa: BLE001 — desde 2026-11 el radio real va fuera de la pantalla: su propio clic
            radio.evaluate("e => e.click()")
        return True  # LinkedIn vuelve a dibujar la pregunta: `apply` relee el formulario y ve si quedó respondida
    return False


UPLOAD = re.compile(r"^(cargar|subir|upload)( (el|tu|un|your|a))? (curr[ií]culum|cv|resume)", re.I)


def _shown_name(cv_pdf: Path) -> str:
    """Se compara el nombre sin extensión: LinkedIn puede agregarle « (1)» si ya tenía uno igual."""
    return cv_pdf.stem


def _upload(page, dialog, cv_pdf: Path) -> bool:
    """Sube el CV de la vacante y lo deja elegido. LinkedIn muestra los CV ya subidos (uno elegido) y crea el campo
    de archivo al pulsar «Cargar currículum»: se usa el selector de archivos del navegador. Devuelve True si el paso
    tenía dónde subirlo."""
    button = dialog.get_by_role("button", name=UPLOAD)
    file_input = dialog.locator("input[type=file]")
    if button.count():
        with page.expect_file_chooser(timeout=30_000) as chooser:
            button.first.click()
        chooser.value.set_files(str(cv_pdf))
    elif file_input.count():
        file_input.first.set_input_files(str(cv_pdf))
    else:
        return False
    name = _shown_name(cv_pdf)
    mine = dialog.get_by_role("radio", name=re.compile(re.escape(name)))
    mine.or_(dialog.get_by_text(name)).first.wait_for(timeout=120_000)  # subida lenta: se espera su nombre
    if mine.count() and not mine.first.is_checked():  # el más nuevo va primero
        mine.first.check(force=True)
    return True


def _cv_ok(dialog, cv_pdf: Path) -> bool:
    """El CV elegido (o el que muestra la revisión) es el de esta vacante."""
    name = _shown_name(cv_pdf)
    checked = [r.get_attribute("aria-label") or "" for r in dialog.locator("input[type=radio]:checked").all()]
    resumes = [label for label in checked if label.lower().endswith((".pdf", ".docx", ".doc"))]
    if resumes:
        return any(name in label for label in resumes)
    return name in dialog.inner_text()


_SAVE_PROMPT = re.compile(r"guardar esta solicitud|save this application", re.I)
_DISCARD = re.compile(r"^\s*(descartar|discard)\s*$", re.I)


def _discard(page) -> None:
    """Cierra la solicitud sin enviarla. Desde 2026-11 LinkedIn apila sus diálogos (`<dialog open>`): la X del
    formulario abre encima «¿Quieres guardar esta solicitud?», y ahí se pulsa «Descartar» (no su X ni «Guardar»)."""
    for _ in range(3):
        dialogs = page.get_by_role("dialog").filter(visible=True)
        if not dialogs.count():
            return
        prompt = dialogs.filter(has_text=_SAVE_PROMPT)
        if prompt.count():
            button = prompt.last.locator("button:not([data-dialog-dismiss])").filter(has_text=_DISCARD)
        else:
            button = dialogs.last.get_by_role("button", name=re.compile(r"^(descartar|dismiss|cerrar|close)", re.I))
        if not button.count():
            return
        with contextlib.suppress(Exception):  # si algo lo tapa, se vuelve a mirar
            button.first.click(timeout=10_000, no_wait_after=True)
        time.sleep(2)


def _limit_notice(page) -> str:
    """El aviso del tope de LinkedIn: un mensaje corto. No cuenta una oferta cuya descripción lo mencione (caso real,
    2026-11-22/24: una descripción en inglés frenó LinkedIn dos días seguidos)."""
    for text in page.get_by_text(LIMIT).all_text_contents()[:20]:
        if len(text.strip()) <= 300:
            return text.strip()
    return ""


def apply(page, job_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, shots: Path | None = None) -> ApplyResult:
    page.goto(job_url, wait_until="domcontentloaded")
    time.sleep(5)
    if _challenge(page):
        return ApplyResult("verificacion", page.url)
    if notice := _limit_notice(page):
        return ApplyResult("tope", f"LinkedIn avisó el tope diario de solicitudes: «{notice[:120]}»")
    if _applied(page):
        return ApplyResult("ya_postulada")
    if page.get_by_text(CLOSED).count():  # no es «externa»: no hay nada que hacer en el sitio de la empresa
        return ApplyResult("saltada", "La vacante ya no recibe solicitudes")
    button = page.get_by_role("button", name=EASY).filter(visible=True).first  # el diseño nuevo trae uno oculto
    if not button.count():
        return ApplyResult("externa", "Sin «Solicitud sencilla» (postulación en la página de la empresa)")
    button.click(no_wait_after=True)  # abre el diálogo y cambia la dirección: no se espera esa navegación
    dialog = page.get_by_role("dialog").first
    try:
        dialog.wait_for(timeout=30_000)
    except Exception:  # noqa: BLE001
        return ApplyResult("error", "No abrió el formulario")
    if not _wait_ready(dialog):
        _discard(page)
        return ApplyResult("error", "El formulario no terminó de cargar")
    uploaded = False
    for step in range(12):
        if _challenge(page):
            return ApplyResult("verificacion", page.url)
        if notice := _limit_notice(page):
            _discard(page)
            return ApplyResult("tope", f"LinkedIn avisó el tope diario de solicitudes: «{notice[:120]}»")
        if not uploaded and _upload(page, dialog, cv_pdf):
            uploaded = True
            if not _cv_ok(dialog, cv_pdf):
                _discard(page)
                return ApplyResult("saltada", "No quedó elegido el CV de esta vacante (no se envía con otro)")
        questions = _questions(dialog)
        missing, saved = _missing(questions), _saved_years(questions)
        if missing or saved:
            answers = answerer(missing + saved)
            for q in missing + saved:
                value = (answers.get(q.label) or "").strip()
                if value and (q in missing or value != q.value):  # sin respuesta nueva, la guardada se deja
                    _fill(dialog, q, value)
            still = _missing(_questions(dialog))
            if still:
                _discard(page)
                return ApplyResult("saltada", "Preguntas sin respuesta en tu perfil ni en tu banco",
                                   unanswered=[q.label for q in still])
        nav = _nav_button(dialog)
        label = nav.inner_text().strip()
        if SUBMIT.match(label):
            # Candado: el CV adjunto debe ser el hecho para ESTA vacante (nunca uno viejo que LinkedIn tenía elegido).
            if not _cv_ok(dialog, cv_pdf):
                _discard(page)
                return ApplyResult("saltada", "No se pudo adjuntar el CV de esta vacante (no se envía con otro)")
            for box in dialog.get_by_role("checkbox", name=FOLLOW).all():  # no seguir a la empresa
                if box.is_checked():
                    box.uncheck(force=True)
            shot = ""
            if shots:
                shots.mkdir(parents=True, exist_ok=True)
                job_id = re.sub(r"\D", "", job_url)[-12:]
                shot = str(shots / f"{job_id}-revision.png")
                page.screenshot(path=shot)
            if not submit:
                _discard(page)
                return ApplyResult("revisada", "Modo prueba: llegó a la revisión y se descartó", screenshot=shot)
            nav.click()
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if page.get_by_text(SENT).count() or _applied(page):
                    close = page.get_by_role("button", name=re.compile(r"^(descartar|dismiss|cerrar|close|listo|done)", re.I))
                    if close.count():
                        close.first.click()
                    return ApplyResult("enviada", screenshot=shot)
                time.sleep(1.5)
            # Sin el aviso esperado: la página de la vacante dice si quedó postulada.
            page.goto(job_url, wait_until="domcontentloaded")
            time.sleep(5)
            if _applied(page):
                return ApplyResult("enviada", "Confirmada en la página de la vacante", screenshot=shot)
            return ApplyResult("error", "No apareció la confirmación de envío: revísala en LinkedIn", screenshot=shot)
        before = dialog.inner_text()[:400]
        nav.click()
        time.sleep(3)
        if dialog.inner_text()[:400] == before and _nav_button(dialog).inner_text().strip() == label:
            problems = [q.label for q in _missing(_questions(dialog))]
            _discard(page)
            return ApplyResult("saltada", f"No avanzó del paso {step + 1}", unanswered=problems)
    _discard(page)
    return ApplyResult("error", "Demasiados pasos")
