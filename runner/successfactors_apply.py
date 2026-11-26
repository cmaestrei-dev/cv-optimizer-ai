"""Postular en un portal SAP SuccessFactors de empresa (Bancolombia) con la sesión que la persona abre en la
ventana del bot.

Lo verificado con la cuenta del dueño (2026-11-22), sin postular:
- El acceso pide correo, contraseña y reCAPTCHA, sin «mantener la sesión»: la persona entra en la ventana del bot
  y el bot postula enseguida a todo lo pendiente («modo en lote»). La sesión de career8 duró más de 40 minutos con
  actividad; la de la página de ofertas (empleo.grupobancolombia.com) vence antes, pero se renueva al pasar por
  career8.
- En la oferta, «Aplicar» → «Enviar candidatura ahora» lleva al formulario (career8 `portalcareer`): el perfil del
  candidato, «Mis documentos» (el currículum se cambia con el lápiz `_attachIcon` → «Cargar de dispositivo»,
  `input[type=file]`) y la sección «Información específica del puesto».
- Las preguntas del puesto tienen la etiqueta `label.rcmFormQuestionLabel` y su control: grupo de radios
  (`role=radiogroup`, cada opción `span[role=radio]` con su `label.radioLabel`; se elige con `<id>_radio`), lista
  (`select`), texto o área de texto. Las listas con autocompletar (`NNN:_input`) muestran `li.globalMenuItem`.
- La «Declaración de conformidad» se acepta escribiendo el nombre completo (el dueño lo autorizó: `firma`).
- «Puestos solicitados (N)» en el perfil cuenta las postulaciones: si sube, la postulación quedó.
- El perfil solo abre con el código de la sesión en la dirección (`_s.crb`): el enlace directo responde «You are
  not authorized». Con la sesión abierta, el acceso lleva al perfil con ese código: se entra siempre por ahí.
- Los identificadores de los campos cambian al redibujarse: se buscan por etiqueta o valor, nunca por número fijo.
El bot nunca resuelve el captcha ni guarda la contraseña.
"""

import re
import time
from collections.abc import Callable
from pathlib import Path

from runner.answers import bank_answer, negative, pick_option
from runner.linkedin import ApplyResult, Question

Answerer = Callable[[list[Question]], dict[str, str]]
SECTION = "Información específica del puesto"  # aparece cuando el formulario terminó de cargar
FORM_TITLE = re.compile(r"^\s*Puestos vacantes:")  # el formulario de una oferta sin preguntas propias no trae SECTION
APPLIED = re.compile(r"Puestos solicitados\s*\((\d+)\)")
ALREADY = re.compile(r"ya (ha|has) (solicitado|aplicado|postulado)|already applied", re.I)
CURRENT_CV = re.compile(r"Curr[ií]culum\s+Descargar documento\s+(\S.*?\.(?:pdf|docx?|txt|rtf))\b", re.I)

# Las preguntas obligatorias del formulario (las del puesto, `rcmFormQuestionLabel`, y las de la sección
# «Información específica del puesto», `rcmFormFieldLabel`), con su tipo, opciones y valor actual, en orden.
_QUESTIONS = """() => {
  const clean = t => (t || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').replace(/^\\*\\s*/, '').trim();
  return [...document.querySelectorAll('label.rcmFormQuestionLabel, label.rcmFormFieldLabel')].filter(l => l.offsetParent !== null).map(l => {
    const el = document.getElementById(l.htmlFor);
    const q = {label: clean(l.innerText), required: !!l.querySelector('.requiredField'), id: l.htmlFor, kind: 'otro', options: [], value: '',
               job: l.classList.contains('rcmFormQuestionLabel')};
    if (!el) return q;
    if (el.getAttribute('role') === 'radiogroup') {
      q.kind = 'radio';
      for (const r of el.querySelectorAll('[role=radio]')) {
        const lab = document.getElementById(r.getAttribute('aria-labelledby'));
        const text = clean(lab ? lab.innerText : '');
        q.options.push([text, r.id.replace(/_anchor$/, '')]);
        if (r.getAttribute('aria-checked') === 'true') q.value = text;
      }
    } else if (el.tagName === 'SELECT') {
      q.kind = 'select';
      q.options = [...el.options].map(o => [clean(o.text), o.value]);
      // Las listas del puesto vienen con la primera opción marcada («1-Bachiller»): se responden siempre. Las del
      // perfil («Sexo») se respetan.
      const shown = el.selectedIndex >= 0 ? clean(el.options[el.selectedIndex].text) : '';
      q.value = q.job && !el.dataset.cvoTouched ? '' : (/^sin selecci/i.test(shown) ? '' : shown);
    } else if (el.tagName === 'TEXTAREA') { q.kind = 'textarea'; q.value = el.value;
    } else if (el.tagName === 'INPUT') { q.kind = el.getAttribute('role') === 'combobox' || /_input$/.test(el.id) ? 'lista' : 'texto'; q.value = el.value; }
    return q; });
}"""


def logged_in(page) -> bool:
    return not page.locator("input[type=password]:visible").count() and "Salir" in page.inner_text("body")


def wait_login(page, login_url: str, *, minutes: int = 15, poll: float = 3) -> bool:
    """Abre el acceso y espera a que la persona entre (ella escribe la contraseña y resuelve el captcha)."""
    page.goto(login_url, wait_until="domcontentloaded")
    deadline = time.monotonic() + minutes * 60
    while time.monotonic() < deadline:
        try:
            if logged_in(page):
                return True
        except Exception:  # noqa: BLE001 — la página está cambiando (envío del formulario de acceso)
            pass
        time.sleep(poll)
    return False


def open_profile(page, login_url: str) -> bool:
    """Abre el perfil del candidato pasando por el acceso (ver arriba). False si no llegó."""
    page.goto(login_url, wait_until="domcontentloaded")
    for _ in range(20):
        try:
            page.wait_for_url(re.compile(r"navBarLevel=MY_PROFILE"), timeout=1_000)
            break
        except Exception:  # noqa: BLE001 — aún no llega; sin sesión se queda en el acceso pidiendo la contraseña
            if page.locator("input[type=password]:visible").count():
                return False
    else:
        return False
    for _ in range(10):
        time.sleep(1.5)
        try:
            if APPLIED.search(page.inner_text("body")):
                return True
        except Exception:  # noqa: BLE001 — la página está cambiando (redirección al perfil)
            pass
    return False


def applied_count(page, login_url: str) -> int | None:
    if not open_profile(page, login_url):
        return None
    match = APPLIED.search(page.inner_text("body"))
    return int(match.group(1)) if match else None


def _open_form(page, offer_url: str) -> str:
    """De la oferta al formulario de postulación. Devuelve un motivo si no se pudo."""
    page.goto(offer_url, wait_until="domcontentloaded")
    time.sleep(4)
    menu = page.locator("button:visible, a:visible").filter(has_text=re.compile(r"^\s*Aplicar"))
    if not menu.count():
        return "la oferta no tiene «Aplicar» (¿cerrada?)"
    menu.first.click()
    time.sleep(1.5)
    now = page.locator("a:visible").filter(has_text="Enviar candidatura ahora")
    if now.count():
        now.first.click()
    for _ in range(30):
        time.sleep(2)
        if page.locator("input[type=password]:visible").count():
            return "sin_sesion"
        if page.get_by_text(SECTION, exact=True).count() or ALREADY.search(page.inner_text("body")[:3000]):
            break
        # Sin la sección del puesto (Front Mobile, 2026-11-26): el título del formulario y su botón final
        if page.get_by_text(FORM_TITLE).count() and _apply_button(page).count():
            break
    else:
        return "no abrió el formulario de postulación"
    _expand(page)
    return ""


def _expand(page) -> None:
    """Abre todas las secciones (cerradas, sus campos y el lápiz del currículum no se ven)."""
    expand = page.get_by_text("Ampliar todas las secciones")
    if expand.count():
        expand.first.click()
        time.sleep(3)


def _current_cv(page) -> str:
    """El nombre del currículum que tiene ahora el formulario o el perfil («Currículum Descargar documento X»)."""
    match = CURRENT_CV.search(re.sub(r"\s+", " ", page.inner_text("body")))
    return match.group(1).strip() if match else ""


def _list_options(page, field_id: str) -> list[str]:
    box = page.locator(f"[id='{field_id}']")
    box.scroll_into_view_if_needed()
    box.click()
    time.sleep(0.3)
    box.press("ArrowDown")
    time.sleep(1.5)
    items = [t.strip() for t in page.locator("li.globalMenuItem:visible").all_inner_texts()]
    box.press("Escape")
    return [t for t in items if t and not t.lower().startswith("sin selecci")]


def _choose(page, q: dict, option: str) -> bool:
    if q["kind"] == "radio":
        radio_id = dict(q["options"])[option]
        page.locator(f"[id='{radio_id}_radio']").click()
    elif q["kind"] == "select":
        page.locator(f"[id='{q['id']}']").select_option(label=option)
        page.locator(f"[id='{q['id']}']").evaluate("e => e.dataset.cvoTouched = '1'")
    elif q["kind"] == "lista":
        box = page.locator(f"[id='{q['id']}']")
        box.click()
        box.fill("")
        box.type(option[:5], delay=50)
        time.sleep(1.2)
        item = page.locator("li.globalMenuItem:visible").filter(has_text=re.compile(r"^\s*" + re.escape(option) + r"\s*$"))
        if not item.count():
            return False
        item.first.click()
    time.sleep(0.5)
    return True


def _replace_cv(page, cv_pdf: Path) -> bool:
    icon = page.locator("[id$='_attachIcon']:visible")
    if not icon.count():
        return False
    icon.first.scroll_into_view_if_needed()
    icon_id = icon.first.get_attribute("id") or ""
    icon.first.click()
    time.sleep(1.5)
    match = re.match(r"(\d+):_attachIcon$", icon_id)  # su campo de archivo es el siguiente: «41:_attachIcon» → «42:_file»
    own = page.locator(f"[id='{int(match.group(1)) + 1}:_file']") if match else None
    (own if own is not None and own.count() else page.locator("input[type=file]").first).set_input_files(str(cv_pdf))
    for _ in range(15):
        time.sleep(1)
        shown = _current_cv(page)
        if shown == cv_pdf.name or (not shown and cv_pdf.name in page.inner_text("body")):
            return True
    return False


def _sign(page, full_name: str) -> bool:
    field = page.locator("input[name='disclaimerAcknowledge'], input[id*='disclaimer' i]")
    if not field.count():
        return True  # este formulario no la pide
    field.first.scroll_into_view_if_needed()
    field.first.fill(full_name)
    field.first.dispatch_event("change")
    field.first.press("Tab")
    return field.first.input_value() == full_name


def _apply_button(page):
    """El botón final del formulario: «Aplicar» o, en algunas ofertas (Front Mobile, 2026-11-26), «Solicitar»."""
    return page.locator("span:visible, button:visible, a:visible, input[type=button]:visible").filter(
        has_text=re.compile(r"^\s*(Aplicar|Solicitar)\s*$"))


def _type(page, field_id: str, value: str) -> None:
    """Escribe y sale del campo: el formulario guarda el valor en su evento «change» (al perder el foco)."""
    box = page.locator(f"[id='{field_id}']")
    box.scroll_into_view_if_needed()
    box.fill(value)
    box.dispatch_event("change")
    box.press("Tab")


def _settle(page, *, rounds: int = 8, pause: float = 2) -> None:
    """Subir el CV o elegir en una lista redibuja el formulario y por unos segundos campos del perfil ya llenos se ven
    vacíos (pasó con «País de nacimiento» y «Nacionalidad»): se espera a que los obligatorios vacíos dejen de cambiar."""
    last = None
    for _ in range(rounds):
        time.sleep(pause)
        now = [q["label"] for q in _pending(page)]
        if now == last:
            return
        last = now


def _pending(page) -> list[dict]:
    """Obligatorias y vacías. Las etiquetas sin control (o de un tipo que no se maneja, como las fechas) se omiten:
    el perfil ya las trae llenas y el portal avisa si falta algo. Una misma pregunta puede repetirse (los cinco «código
    de la práctica» de las prácticas de Bancolombia): `n` es su lugar entre las de igual etiqueta y `count` cuántas hay
    (los ids cambian al redibujar; el orden no)."""
    questions = page.evaluate(_QUESTIONS)
    seen: dict[str, int] = {}
    for q in questions:
        q["n"] = seen.get(q["label"], 0)
        seen[q["label"]] = q["n"] + 1
    for q in questions:
        q["count"] = seen[q["label"]]
    return [q for q in questions if q["required"] and q["id"] and q["kind"] != "otro" and not q["value"].strip()]


def apply(page, offer_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, full_name: str,
          overrides: dict[str, str], login_url: str) -> ApplyResult:
    """Postula a una oferta con la sesión ya abierta. `overrides`: respuestas propias del portal (patrón → opción).

    Orden (verificado el 2026-11-22: el primer intento real perdió respuestas): primero el CV; luego cada pregunta
    obligatoria vacía, en el orden del formulario (las listas en cascada, como «Detalles», dependen de la anterior);
    luego la firma; y solo si ya no queda nada obligatorio vacío, «Aplicar»."""
    before = applied_count(page, login_url) if submit else None
    reason = _open_form(page, offer_url)
    if reason == "sin_sesion":
        return ApplyResult("sin_sesion", "La sesión del portal venció: vuelve a entrar")
    if reason:
        return ApplyResult("saltada", reason)
    if ALREADY.search(page.inner_text("body")[:3000]):
        return ApplyResult("ya_postulada")
    if not _replace_cv(page, cv_pdf):
        return ApplyResult("saltada", "No quedó adjunto el CV de esta vacante (no se envía con otro)")
    _settle(page)
    missing: list[str] = []
    asked: set[tuple[str, int]] = set()
    for _ in range(40):  # una pregunta a la vez: la siguiente lista puede depender de la anterior
        todo = [q for q in _pending(page) if (q["label"], q["n"]) not in asked and "Declaración de Conformidad" not in q["label"]]
        if not todo:
            break
        q = todo[0]
        if not q["job"]:  # un campo del perfil vacío puede ser el redibujo: se mira otra vez antes de responderlo
            _settle(page, rounds=3)
            if all(p["label"] != q["label"] for p in _pending(page)):
                continue
        asked.add((q["label"], q["n"]))
        if q["kind"] == "lista":
            q["options"] = [[o, o] for o in _list_options(page, q["id"])]
        question = Question("radio" if q["options"] else ("textarea" if q["kind"] == "textarea" else "text"),
                            q["label"], True, "", [o for o, _ in q["options"]], [q["id"]])
        value = (bank_answer(question.label, overrides) or answerer([question]).get(question.label) or "").strip()
        if q["count"] > 1 and "|" in value:  # «SIS29|SIS22» en cinco campos iguales: uno por campo, en orden y repitiendo
            parts = [v.strip() for v in value.split("|") if v.strip()]
            value = parts[q["n"] % len(parts)]
        if q["options"]:
            option = pick_option(value, question.options) if value else None
            wrong = not option or (negative(option) and not value.lower().startswith("no"))  # nunca un «no» que no se dijo
            if wrong or not _choose(page, q, option):
                missing.append(question.label)
        elif value:
            _type(page, q["id"], value[:1000])
        else:
            missing.append(question.label)
        _settle(page, rounds=3, pause=1)
    if missing:
        return ApplyResult("saltada", "Preguntas del puesto sin respuesta en tu banco ni en tu perfil", unanswered=missing)
    if not _sign(page, full_name):
        return ApplyResult("error", "No pude firmar la declaración de conformidad")
    still = [q["label"] for q in _pending(page)]
    if still:
        return ApplyResult("saltada", "Quedaron campos obligatorios vacíos (no se envía)", unanswered=still[:6])
    if not submit:
        return ApplyResult("revisada", "Modo prueba: formulario lleno y no se envió")
    button = _apply_button(page)
    if not button.count():
        return ApplyResult("error", "No encontré el botón «Aplicar» o «Solicitar» del formulario")
    button.last.click()
    time.sleep(6)
    confirm = page.get_by_role("button", name=re.compile(r"^(Aceptar|Sí|Si|Aplicar|Solicitar|Confirmar|Enviar)$", re.I))
    if confirm.count():
        confirm.first.click()
        time.sleep(6)
    errors = [t.strip() for t in page.locator(".rcmValidationMsgArea:visible, [role=alert]:visible").all_inner_texts() if t.strip()]
    if any(re.search(r"corrija|obligatori|error", t, re.I) for t in errors):
        return ApplyResult("error", "El portal no aceptó el formulario: " + "; ".join(errors)[:600])
    after = applied_count(page, login_url)
    if before is not None and after is not None and after > before:
        return ApplyResult("enviada", f"Confirmada: «Puestos solicitados» pasó de {before} a {after}")
    return ApplyResult("enviada", "El portal aceptó el envío, pero no pude confirmarlo en «Puestos solicitados»: revísalo tú")


def restore_cv(page, login_url: str, cv_pdf: Path, *, shot: Path | None = None) -> str:
    """Deja en el perfil el CV general (después de un lote cada postulación ya llevó el suyo). Devuelve "" si quedó o
    el paso en que falló (y deja una captura en `shot`). Se confirma recargando el perfil, no por el aviso."""
    problem = _restore(page, page.url, cv_pdf) if open_profile(page, login_url) else (
        f"el perfil no abrió con la sesión ({page.url[:80]})")
    if problem and shot:
        try:
            shot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot), full_page=True)
        except Exception:  # noqa: BLE001 — la captura es solo para revisar
            pass
    return problem


def _notices(page) -> str:
    texts = page.locator(".rcmValidationMsgArea:visible, [role=alert]:visible, .globalMessage:visible").all_inner_texts()
    return "; ".join(re.sub(r"\s+", " ", t).strip() for t in texts if t.strip())[:300]


def _restore(page, profile_url: str, cv_pdf: Path) -> str:
    """`profile_url`: la dirección del perfil con el código de la sesión (la de la página abierta)."""
    _expand(page)
    if _current_cv(page) == cv_pdf.name:
        return ""
    if not page.locator("[id$='_attachIcon']:visible").count():
        return f"no vi el lápiz de «Mis documentos» (el perfil muestra «{_current_cv(page) or '?'}»)"
    if not _replace_cv(page, cv_pdf):
        return f"el archivo no quedó cargado (el perfil muestra «{_current_cv(page) or '?'}»; avisos: {_notices(page) or 'ninguno'})"
    save = page.locator("span.rcmSaveButton:visible, [id$='_saveBtn']:visible")
    if not save.count():
        return "no encontré «Guardar» en el perfil"
    save.first.click()
    for _ in range(15):
        time.sleep(1)
        if "guardado correctamente" in page.inner_text("body"):
            break
    notices = _notices(page)
    page.goto(profile_url, wait_until="domcontentloaded")
    time.sleep(5)
    _expand(page)
    shown = _current_cv(page)
    if shown == cv_pdf.name:
        return ""
    return f"tras guardar, el perfil sigue con «{shown or '?'}» (avisos: {notices or 'ninguno'})"
