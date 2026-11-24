"""Postular en Eightfold (Mercado Libre, Softtek) sin cuenta, con el CV de la vacante.

Verificado el 2026-11-24 en ofertas reales de Mercado Libre y Softtek, llenando sin enviar:
- El formulario está en `<sitio>/careers/apply?pid=<id>`: CV (`input[type=file]`), contacto
  (`Informaci_n_de_contacto_email|firstname|lastname|phone|city`; «País» y «Código de país» son listas), LinkedIn
  (opcional) y las preguntas del puesto. Cada pregunta tiene `label#<id>_label[for=<id>]` y es texto (`input#<id>`),
  opciones (`[role=radiogroup]#<id>`, radios «Si»/«No») o lista (`input[role=combobox]` con `aria-labelledby` de la
  pregunta; sus opciones `[role=option]` aparecen en `#<aria-controls>` al abrirla).
- Mercado Libre pide autorizar el contacto por WhatsApp sobre la postulación (casilla obligatoria), aceptar su
  declaración de privacidad y decir si hay un familiar en la empresa. «Guardar mis respuestas para futuras
  solicitudes» queda sin marcar.
- Softtek, al elegir el CV, pide aceptar su «Acuerdo de privacidad de datos» (tratamiento de datos para postular): se
  acepta; las cookies no necesarias se rechazan.
- Tiene reCAPTCHA invisible de Google. El bot no lo toca ni se oculta: si Google muestra un reto, se detiene y la
  vacante pasa a la persona.
"""

import re
import time
from collections.abc import Callable
from pathlib import Path

from runner.answers import bank_answer, negative, normalize, pick_option, to_period
from runner.linkedin import ApplyResult, Question

Answerer = Callable[[list[Question]], dict[str, str]]
CHALLENGE = "iframe[src*='recaptcha/api2/bframe'], iframe[src*='hcaptcha'], iframe[src*='turnstile']"
DONE = re.compile(r"gracias por (tu|su) (postulaci|solicitud|aplicaci|inter)|(solicitud|postulaci[oó]n) (fue |ha sido )?"
                  r"(enviada|recibida|presentada)|hemos recibido|thank you for (applying|your application)|"
                  r"application (has been )?(submitted|received)", re.I)
ALREADY = re.compile(r"ya (te has|se ha|has) (postulado|aplicado|enviado)|already applied", re.I)
SUBMIT = re.compile(r"^\s*(presentar|enviar) solicitud\s*$|^\s*submit( application)?\s*$", re.I)
CONTACT = "Informaci_n_de_contacto_"
CONSENT = re.compile(r"(estoy de acuerdo|acepto|autoriz)", re.I)

# Las preguntas del formulario (sin las de contacto), con su tipo, opciones y respuesta actual.
_QUESTIONS = """() => [...document.querySelectorAll('label[id$="_label"][for]')].map(label => {
  const id = label.getAttribute('for');
  const text = label.innerText.replace(/\\*/g, '').replace(/\\s+/g, ' ').trim();
  const group = document.querySelector(`[role=radiogroup][id="${id}"]`);
  const combo = document.querySelector(`input[role=combobox][aria-labelledby~="${id}_label"]`);
  const field = document.querySelector(`input[id="${id}"]:not([type=radio]):not([type=checkbox]), textarea[id="${id}"]`);
  const boxes = [...document.querySelectorAll(`input[type=checkbox][name="${id}"]`)];
  if (group) {
    const radios = [...group.querySelectorAll('input[type=radio]')];
    return {id, label: text, kind: 'radio', required: radios.some(r => r.getAttribute('aria-required') === 'true'),
            options: radios.map(r => r.value), value: (radios.find(r => r.checked) || {}).value || ''};
  }
  if (combo) return {id, label: text, kind: 'select', combo: combo.id, required: combo.getAttribute('aria-required') === 'true',
                     options: [], value: combo.value || ''};
  if (boxes.length) return {id, label: text, kind: 'checkbox', required: boxes.some(b => b.getAttribute('aria-required') === 'true'),
                            options: boxes.map(b => (document.querySelector(`label[for="${b.id}"]`) || {}).innerText || b.value),
                            value: boxes.some(b => b.checked) ? 'true' : '', boxes: boxes.map(b => b.id)};
  if (field) return {id, label: text, kind: field.tagName === 'TEXTAREA' ? 'textarea' : 'text',
                     required: field.getAttribute('aria-required') === 'true' || field.required, options: [], value: field.value || ''};
  return null;
}).filter(q => q && q.label && !q.id.startsWith('Informaci_n_de_contacto_'))"""

# Casillas obligatorias sin marcar, con su etiqueta. «Guardar mis respuestas para futuras solicitudes» no es obligatoria.
_REQUIRED_BOXES = """() => [...document.querySelectorAll('input[type=checkbox]')]
  .filter(b => !b.checked && (b.getAttribute('aria-required') === 'true' || b.required))
  .map(b => [b.id, ((document.querySelector(`label[for="${b.id}"]`) || {}).innerText || b.getAttribute('aria-label') || '').trim()])"""


def apply_url(offer_url: str) -> str:
    match = re.search(r"^(https://[^/]+)/careers/(?:job/(\d+)|apply\?pid=(\d+))", offer_url)
    if not match:
        raise ValueError(f"no reconozco la oferta de Eightfold: {offer_url}")
    return f"{match.group(1)}/careers/apply?pid={match.group(2) or match.group(3)}"


def _split_name(full_name: str) -> tuple[str, str]:
    words = full_name.split()
    if len(words) >= 4:
        return " ".join(words[:2]), " ".join(words[2:])
    return (words[0], " ".join(words[1:])) if len(words) > 1 else (full_name, "")


def _options(page, combo_id: str) -> list[str]:
    combo = page.locator(f"[id='{combo_id}']")
    combo.scroll_into_view_if_needed()
    combo.click()
    time.sleep(0.8)
    listbox = combo.get_attribute("aria-controls") or ""
    return [o.strip() for o in page.locator(f"[id='{listbox}'] [role=option]").all_inner_texts()] if listbox else []


def _pick(page, combo_id: str, option: str, *, typed: str = "") -> bool:
    """Elige una opción de una lista (escribiendo `typed` antes, para las listas largas como los países)."""
    combo = page.locator(f"[id='{combo_id}']")
    combo.scroll_into_view_if_needed()
    combo.click()
    if typed:
        combo.fill(typed)
    time.sleep(0.8)
    listbox = combo.get_attribute("aria-controls") or ""
    item = page.locator(f"[id='{listbox}'] [role=option]").filter(has_text=re.compile(rf"^\s*{re.escape(option)}\s*$"))
    if not listbox or not item.count():
        page.keyboard.press("Escape")
        return False
    item.first.click()
    time.sleep(0.4)
    return option in (combo.input_value() or "")


_COMBOS = """() => [...document.querySelectorAll('input[role=combobox]')].map(c => ({id: c.id, value: c.value,
  name: (c.getAttribute('aria-label') || (c.getAttribute('aria-labelledby') || '').split(' ')
         .map(i => (document.getElementById(i) || {}).innerText || '').join(' ') || c.placeholder || '').replace(/\\s+/g, ' ').trim()}))"""


def _typed_pick(page, combo_id: str, typed: str, want: Callable[[str], bool]) -> bool:
    """Las listas largas (países) se filtran escribiendo; se elige la primera opción que sirve."""
    combo = page.locator(f"[id='{combo_id}']")
    combo.scroll_into_view_if_needed()
    combo.click()
    combo.fill(typed)
    time.sleep(1)
    listbox = combo.get_attribute("aria-controls") or ""
    items = page.locator(f"[id='{listbox}'] [role=option]")
    for i in range(min(items.count(), 30)):
        if want(items.nth(i).inner_text().strip()):
            items.nth(i).click()
            time.sleep(0.4)
            return bool((combo.input_value() or "").strip())
    page.keyboard.press("Escape")
    return False


def _country(page, country: str) -> bool:
    """«País» → el país del perfil; «Código de país» del teléfono → la opción de ese país (o +57)."""
    for combo in page.evaluate(_COMBOS):
        name = normalize(combo["name"])
        if combo["value"].strip() or not ("codigo" in name or re.fullmatch(r"pais\*?", name)):
            continue
        code = "codigo" in name
        if not _typed_pick(page, combo["id"], country,
                           lambda o, code=code: normalize(country) in normalize(o) or (code and "+57" in o)):
            time.sleep(3)  # Eightfold puede llenarla tarde, al terminar de leer el CV
            if not (page.locator(f"[id='{combo['id']}']").input_value() or "").strip():
                return False
    return True


def apply(page, offer_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, contact: dict,
          overrides: dict[str, str] | None = None, cover: Callable[[], str] | None = None,
          shots: Path | None = None) -> ApplyResult:
    """Postula a una oferta de Eightfold con el CV de la vacante. `contact`: el del perfil (full_name, email, phone,
    city, linkedin_url)."""
    overrides = overrides or {}
    response = page.goto(apply_url(offer_url), wait_until="domcontentloaded")
    time.sleep(6)
    if response is not None and response.status in (404, 410):
        return ApplyResult("saltada", "La oferta ya no está publicada")
    text = page.inner_text("body")
    if ALREADY.search(text):
        return ApplyResult("ya_postulada")
    upload = page.locator("input[type=file]")
    if not upload.count():
        return ApplyResult("saltada", "La oferta no tiene formulario de postulación (¿cerrada?)")

    decline = page.get_by_role("button", name=re.compile(r"^\s*(decline all|rechazar todo|rechazar)\s*$", re.I))
    if decline.count() and decline.first.is_visible():  # cookies: solo las necesarias
        decline.first.click()
        time.sleep(0.5)
    upload.first.set_input_files(str(cv_pdf))  # Eightfold lee el CV y llena el contacto: se revisa después
    for _ in range(15):
        time.sleep(1)
        privacy = page.get_by_role("dialog").filter(has_text=re.compile(r"privacidad|privacy", re.I))
        agree = privacy.get_by_role("button", name=re.compile(r"^\s*(estoy de acuerdo|acepto|i agree|agree)\s*$", re.I))
        if agree.count() and agree.first.is_visible():  # Softtek pide aceptar el tratamiento de datos para subir el CV
            agree.first.click()
            time.sleep(1)
            continue
        if cv_pdf.stem[:40] in page.inner_text("body"):
            break
    else:
        return ApplyResult("saltada", "No quedó adjunto el CV de esta vacante (no se envía con otro)")
    time.sleep(3)

    first, last = _split_name(contact.get("full_name", ""))
    for name, value in (("email", contact.get("email", "")), ("firstname", first), ("lastname", last),
                        ("phone", re.sub(r"\D", "", contact.get("phone", ""))[-10:]), ("city", contact.get("city", ""))):
        field = page.locator(f"input[id='{CONTACT}{name}']")
        if field.count() and value and field.input_value().strip() != value:
            field.fill(value)
            field.press("Tab")
    linkedin = page.locator("input[id$='LinkedIn']")
    profile_url = contact.get("linkedin_url") or contact.get("linkedin") or ""
    if linkedin.count() and profile_url and not linkedin.first.input_value().strip():
        linkedin.first.fill(profile_url)
    if not _country(page, contact.get("country") or "Colombia"):
        return ApplyResult("saltada", "No pude elegir el país o el código del teléfono en el formulario")

    missing = []
    for q in page.evaluate(_QUESTIONS):
        if not q["required"] or q["value"]:
            continue
        if q["kind"] == "checkbox":  # una autorización obligatoria para postular (p. ej. contacto por WhatsApp)
            if len(q["options"]) == 1 and CONSENT.search(q["options"][0]):
                page.evaluate("id => document.getElementById(id).click()", q["boxes"][0])
                continue
            missing.append(q["label"])
            continue
        options = q["options"] or (_options(page, q["combo"]) if q["kind"] == "select" else [])
        if q["kind"] == "select":
            page.keyboard.press("Escape")
        question = Question("radio" if options else q["kind"], q["label"], True, "", options, [q["id"]])
        value = (bank_answer(q["label"], overrides) or answerer([question]).get(q["label"]) or "").strip()
        if options:
            option = pick_option(value, options) if value else None
            if not option or (negative(option) and not value.lower().startswith("no")):
                missing.append(q["label"])
            elif q["kind"] == "radio":
                page.evaluate("([name, v]) => { const r = [...document.getElementsByName(name)].find(e => e.value === v);"
                              " if (r && !r.checked) r.click(); }", [q["id"], option])
            elif not _pick(page, q["combo"], option):
                missing.append(q["label"])
        elif value:
            field = page.locator(f"[id='{q['id']}']")
            field.scroll_into_view_if_needed()
            field.fill((to_period(value) or value) if re.search(r"a[nñ]os|years", q["label"], re.I) else value[:1000])
            field.press("Tab")
        else:
            missing.append(q["label"])
    page.evaluate("""() => { for (const b of document.querySelectorAll('input[type=checkbox]')) {
        const l = (document.querySelector(`label[for="${b.id}"]`) || {}).innerText || '';
        if (b.checked && /guardar mis respuestas|save my (answers|responses)/i.test(l)) b.click(); } }""")
    for box_id, label in page.evaluate(_REQUIRED_BOXES):  # autorizaciones obligatorias fuera de las preguntas
        if CONSENT.search(label):
            page.evaluate("id => document.getElementById(id).click()", box_id)
        else:
            missing.append(label or box_id)
    if missing:
        return ApplyResult("saltada", "Preguntas de la empresa sin respuesta en tu banco ni en tu perfil", unanswered=missing)
    still = [q["label"] for q in page.evaluate(_QUESTIONS) if q["required"] and not q["value"]]
    empty = [n for n in ("email", "firstname", "lastname", "phone", "city")
             if page.locator(f"input[id='{CONTACT}{n}']").count() and not page.locator(f"input[id='{CONTACT}{n}']").input_value().strip()]
    if still or empty:
        return ApplyResult("saltada", "El formulario no está completo (no se envía)", unanswered=(still + empty)[:6])
    if not submit:
        return ApplyResult("revisada", "Modo prueba: formulario lleno y no se envió")

    posts: list[str] = []  # lo que responde el servidor al enviar: si no hay confirmación, queda en el registro
    page.on("response", lambda r: posts.append(f"{r.request.method} {r.url.split('?')[0][-60:]} → {r.status}")
            if r.request.method in ("POST", "PUT") and "google" not in r.url else None)
    buttons = page.get_by_role("button", name=SUBMIT).filter(visible=True)
    if not buttons.count():
        return ApplyResult("error", "No encontré el botón para enviar la solicitud")
    buttons.last.click()
    for _ in range(25):
        time.sleep(1)
        if page.locator(CHALLENGE).filter(visible=True).count():
            return ApplyResult("verificacion", "Al enviar, Google pidió una verificación (captcha): termina tú la postulación")
        text = page.inner_text("body")
        if ALREADY.search(text):
            return ApplyResult("ya_postulada")
        if done := DONE.search(text):
            around = " ".join(text[max(0, done.start() - 40):done.end() + 80].split())
            return ApplyResult("enviada", f"Confirmada por el portal: «{around}»")
    errors = [e for e in page.locator("[role=status], [role=alert]").all_inner_texts() if e.strip()]
    shot = ""
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
        shot = str(shots / f"eightfold-{re.sub(r'[^0-9]', '', apply_url(offer_url))[-12:]}.png")
        page.screenshot(path=shot, full_page=True)
    return ApplyResult("error", "Eightfold no confirmó el envío (revísalo tú): " + "; ".join(errors + posts[-4:])[:300],
                       screenshot=shot)
