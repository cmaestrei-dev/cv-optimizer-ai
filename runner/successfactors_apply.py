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
APPLIED = re.compile(r"Puestos solicitados\s*\((\d+)\)")
ALREADY = re.compile(r"ya (ha|has) (solicitado|aplicado|postulado)|already applied", re.I)

# Las preguntas obligatorias del formulario (las del puesto, `rcmFormQuestionLabel`, y las de la sección
# «Información específica del puesto», `rcmFormFieldLabel`), con su tipo, opciones y valor actual, en orden.
_QUESTIONS = """() => {
  const clean = t => (t || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').replace(/^\\*\\s*/, '').trim();
  return [...document.querySelectorAll('label.rcmFormQuestionLabel, label.rcmFormFieldLabel')].filter(l => l.offsetParent !== null).map(l => {
    const el = document.getElementById(l.htmlFor);
    const q = {label: clean(l.innerText), required: !!l.querySelector('.requiredField'), id: l.htmlFor, kind: 'otro', options: [], value: ''};
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
      q.value = el.selectedIndex >= 0 && el.dataset.cvoTouched ? clean(el.options[el.selectedIndex].text) : '';
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


def applied_count(page, profile_url: str) -> int | None:
    page.goto(profile_url, wait_until="domcontentloaded")
    time.sleep(4)
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
    else:
        return "no abrió el formulario de postulación"
    expand = page.get_by_text("Ampliar todas las secciones")
    if expand.count():
        expand.first.click()
        time.sleep(3)
    return ""


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
    icon.first.click()
    time.sleep(1.5)
    page.locator("input[type=file]").first.set_input_files(str(cv_pdf))
    for _ in range(15):
        time.sleep(1)
        if cv_pdf.name in page.inner_text("body"):
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
    return page.locator("span:visible, button:visible, a:visible, input[type=button]:visible").filter(
        has_text=re.compile(r"^\s*Aplicar\s*$"))


def _type(page, field_id: str, value: str) -> None:
    """Escribe y sale del campo: el formulario guarda el valor en su evento «change» (al perder el foco)."""
    box = page.locator(f"[id='{field_id}']")
    box.scroll_into_view_if_needed()
    box.fill(value)
    box.dispatch_event("change")
    box.press("Tab")


def _pending(page) -> list[dict]:
    return [q for q in page.evaluate(_QUESTIONS) if q["required"] and not q["value"].strip()]


def apply(page, offer_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, full_name: str,
          overrides: dict[str, str], profile_url: str) -> ApplyResult:
    """Postula a una oferta con la sesión ya abierta. `overrides`: respuestas propias del portal (patrón → opción).

    Orden (verificado el 2026-11-22: el primer intento real perdió respuestas): primero el CV; luego cada pregunta
    obligatoria vacía, en el orden del formulario (las listas en cascada, como «Detalles», dependen de la anterior);
    luego la firma; y solo si ya no queda nada obligatorio vacío, «Aplicar»."""
    before = applied_count(page, profile_url) if submit else None
    reason = _open_form(page, offer_url)
    if reason == "sin_sesion":
        return ApplyResult("sin_sesion", "La sesión del portal venció: vuelve a entrar")
    if reason:
        return ApplyResult("saltada", reason)
    if ALREADY.search(page.inner_text("body")[:3000]):
        return ApplyResult("ya_postulada")
    if not _replace_cv(page, cv_pdf):
        return ApplyResult("saltada", "No quedó adjunto el CV de esta vacante (no se envía con otro)")
    time.sleep(2)
    missing: list[str] = []
    asked: set[str] = set()
    for _ in range(40):  # una pregunta a la vez: la siguiente lista puede depender de la anterior
        todo = [q for q in _pending(page) if q["label"] not in asked and "Declaración de Conformidad" not in q["label"]]
        if not todo:
            break
        q = todo[0]
        asked.add(q["label"])
        if q["kind"] == "lista":
            q["options"] = [[o, o] for o in _list_options(page, q["id"])]
        question = Question("radio" if q["options"] else ("textarea" if q["kind"] == "textarea" else "text"),
                            q["label"], True, "", [o for o, _ in q["options"]], [q["id"]])
        value = (bank_answer(question.label, overrides) or answerer([question]).get(question.label) or "").strip()
        if q["options"]:
            option = pick_option(value, question.options) if value else None
            wrong = not option or (negative(option) and not value.lower().startswith("no"))  # nunca un «no» que no se dijo
            if wrong or not _choose(page, q, option):
                missing.append(question.label)
        elif value:
            _type(page, q["id"], value[:1000])
        else:
            missing.append(question.label)
        time.sleep(0.5)
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
        return ApplyResult("error", "No encontré el botón «Aplicar» del formulario")
    button.last.click()
    time.sleep(6)
    confirm = page.get_by_role("button", name=re.compile(r"^(Aceptar|Sí|Si|Aplicar|Confirmar|Enviar)$", re.I))
    if confirm.count():
        confirm.first.click()
        time.sleep(6)
    errors = [t.strip() for t in page.locator(".rcmValidationMsgArea:visible, [role=alert]:visible").all_inner_texts() if t.strip()]
    if any(re.search(r"corrija|obligatori|error", t, re.I) for t in errors):
        return ApplyResult("error", "El portal no aceptó el formulario: " + "; ".join(errors)[:600])
    after = applied_count(page, profile_url)
    if before is not None and after is not None and after > before:
        return ApplyResult("enviada", f"Confirmada: «Puestos solicitados» pasó de {before} a {after}")
    return ApplyResult("enviada", "El portal aceptó el envío, pero no pude confirmarlo en «Puestos solicitados»: revísalo tú")


def restore_cv(page, profile_url: str, cv_pdf: Path) -> bool:
    """Deja en el perfil el CV general (después de un lote cada postulación ya llevó el suyo)."""
    page.goto(profile_url, wait_until="domcontentloaded")
    time.sleep(5)
    if not _replace_cv(page, cv_pdf):
        return False
    save = page.locator("span.rcmSaveButton:visible, [id$='_saveBtn']:visible")
    if not save.count():
        return False
    save.first.click()
    time.sleep(6)
    return "guardado correctamente" in page.inner_text("body")
