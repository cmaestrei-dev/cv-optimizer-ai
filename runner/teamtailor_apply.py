"""Postular en el portal de empleos Teamtailor de una empresa (Periferia IT, Alegra, Siigo, Bluetab), sin cuenta.

Verificado el 2026-11-22 en una oferta de Periferia IT, llenando sin enviar:
- El formulario está en `<oferta>/applications/new` (`#job-application-form`), sin cuenta ni captcha.
- Preguntas de la empresa (`div.question`, con `data-question-mandatory`): texto, área de texto u opciones (radios).
  Algunas opciones van en un desplegable: se abre su botón y se elige el `menuitemradio`, que llena el campo oculto
  obligatorio; las demás se marcan con un clic en el radio.
- Nombre, apellidos, correo, teléfono (con su país), el CV (`input[type=file]`) y el consentimiento de la política de
  privacidad (`candidate[consent_given]`), obligatorio para postular. El de «futuras oportunidades» queda sin marcar.
- Antes de enviar, el formulario mismo dice si falta algo (`checkValidity`).
Si aparece una verificación (captcha), el bot se detiene; nunca la resuelve.
"""

import re
import time
from collections.abc import Callable
from pathlib import Path

from runner.answers import bank_answer, negative, pick_option, to_integer
from runner.linkedin import ApplyResult, Question

Answerer = Callable[[list[Question]], dict[str, str]]
FORM = "#job-application-form"
CAPTCHA = "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='turnstile']"
DONE = re.compile(r"gracias por (tu|su) (postulaci|aplicaci|inter)|hemos recibido|thank you for (your )?(applying|application)|"
                  r"application (has been )?(sent|received)|postulaci[oó]n (fue |ha sido )?(enviada|recibida)", re.I)
ALREADY = re.compile(r"ya (te has|se ha|has) (postulado|aplicado)|already applied", re.I)

# Las preguntas de la empresa, en orden, con su tipo, opciones (texto e id del radio) y si ya tienen respuesta.
_QUESTIONS = """() => [...document.querySelectorAll('#job-application-form div.question')].map((q, i) => {
  const head = q.querySelector('legend, label');
  const label = (head ? head.innerText : '').replace(/\\*/g, '').replace(/Obligatorio/g, '').replace(/\\s+/g, ' ').trim();
  const choices = [...q.querySelectorAll('input[type=radio], input[type=checkbox]')];
  const text = q.querySelector('input[type=text], input[type=number], input[type=url], textarea');
  const options = choices.map(c => { const l = q.querySelector('label[for="' + c.id + '"]'); return [(l ? l.innerText : c.value).trim(), c.id]; });
  return {index: i, label, required: q.dataset.questionMandatory === 'true',
          kind: choices.length ? 'radio' : (text ? (text.tagName === 'TEXTAREA' ? 'textarea' : 'text') : 'otro'),
          options, field: text ? text.id : '', dropdown: !!q.querySelector('button[aria-haspopup=menu]'),
          numeric: !!(text && text.type === 'number'),
          answered: choices.some(c => c.checked) || !!(text && text.value.trim())};
})"""

# Lo que el navegador no dejaría enviar (campos obligatorios vacíos o inválidos), con su etiqueta.
_INVALID = """() => [...document.querySelectorAll('#job-application-form input, #job-application-form textarea, #job-application-form select')]
  .filter(e => !e.disabled && e.type !== 'hidden' && !e.checkValidity())
  .map(e => { const q = e.closest('div.question'); const head = q && q.querySelector('legend, label');
              const own = e.id && document.querySelector('label[for="' + e.id + '"]');
              return ((head || own) ? (head || own).innerText : (e.name || e.id)).replace(/\\*|Obligatorio/g, '').replace(/\\s+/g, ' ').trim(); })"""


def application_url(offer_url: str) -> str:
    url = offer_url.split("?")[0].rstrip("/")
    return url if url.endswith("/applications/new") else url + "/applications/new"


def _split_name(full_name: str) -> tuple[str, str]:
    words = full_name.split()
    if len(words) >= 4:
        return " ".join(words[:2]), " ".join(words[2:])
    return (words[0], " ".join(words[1:])) if len(words) > 1 else (full_name, "")


def _choose(page, q: dict, option: str) -> bool:
    option_id = dict(q["options"]).get(option)
    if not option_id:
        return False
    block = page.locator(f"{FORM} div.question").nth(q["index"])
    if q["dropdown"]:
        button = block.locator("button[aria-haspopup=menu]").first
        button.scroll_into_view_if_needed()
        button.click()
        time.sleep(0.6)
        item = page.locator(f"[id='{button.get_attribute('aria-controls')}']").get_by_role("menuitemradio", name=option, exact=True)
        if not item.count():
            return False
        item.first.click()
    else:
        page.evaluate("id => document.getElementById(id).click()", option_id)
    time.sleep(0.4)
    return page.evaluate("id => document.getElementById(id).checked", option_id)


def apply(page, offer_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, contact: dict,
          overrides: dict[str, str]) -> ApplyResult:
    """Postula a una oferta de Teamtailor con el CV de la vacante. `contact`: full_name, email y phone."""
    response = page.goto(application_url(offer_url), wait_until="domcontentloaded")
    time.sleep(3)
    if response is not None and response.status in (404, 410):
        return ApplyResult("saltada", "La oferta ya no está publicada")
    if page.locator(CAPTCHA).count():
        return ApplyResult("verificacion", "El portal pidió una verificación (captcha): postúlate tú")
    if not page.locator(FORM).count():
        return ApplyResult("saltada", "La oferta no tiene formulario de postulación (¿cerrada o en otro sitio?)")
    decline = page.get_by_role("button", name=re.compile(r"Rechazar cookies", re.I))
    if decline.count() and decline.first.is_visible():
        decline.first.click()
        time.sleep(0.5)

    missing = []
    for q in page.evaluate(_QUESTIONS):
        if not q["required"] or q["answered"] or q["kind"] == "otro" or not q["label"]:
            continue
        options = [o for o, _ in q["options"]]
        question = Question("radio" if options else q["kind"], q["label"], True, "", options, [q["field"]], numeric=q["numeric"])
        value = (bank_answer(q["label"], overrides) or answerer([question]).get(q["label"]) or "").strip()
        if options:
            option = pick_option(value, options) if value else None
            if not option or (negative(option) and not value.lower().startswith("no")) or not _choose(page, q, option):
                missing.append(q["label"])
        elif q["numeric"] and not to_integer(value):
            missing.append(q["label"])  # el campo solo acepta un número
        elif value:
            value = to_integer(value) if q["numeric"] else value
            field = page.locator(f"[id='{q['field']}']")
            field.scroll_into_view_if_needed()
            field.fill(value[:1000])
        else:
            missing.append(q["label"])
    if missing:
        return ApplyResult("saltada", "Preguntas de la empresa sin respuesta en tu banco ni en tu perfil", unanswered=missing)

    first, last = _split_name(contact.get("full_name", ""))
    for selector, value in (("#candidate_first_name", first), ("#candidate_last_name", last),
                            ("#candidate_email", contact.get("email", "")), ("#candidate_phone", contact.get("phone", ""))):
        field = page.locator(selector)
        if field.count() and value and not field.input_value().strip():
            field.fill(value)
            field.press("Tab")
    upload = page.locator(f"{FORM} input[type=file]")
    if not upload.count():
        return ApplyResult("error", "No encontré dónde subir el CV en el formulario")
    upload.first.set_input_files(str(cv_pdf))
    for _ in range(10):
        time.sleep(1)
        if cv_pdf.name in page.inner_text(FORM):
            break
    else:
        return ApplyResult("saltada", "No quedó adjunto el CV de esta vacante (no se envía con otro)")
    consent = page.locator("#candidate_consent_given")
    if consent.count() and not consent.is_checked():
        page.evaluate("() => document.getElementById('candidate_consent_given').click()")
    invalid = [label for label in page.evaluate(_INVALID) if label]
    if invalid:
        return ApplyResult("saltada", "El formulario no está completo (no se envía)", unanswered=invalid[:6])
    if not submit:
        return ApplyResult("revisada", "Modo prueba: formulario lleno y no se envió")

    page.locator(f"{FORM} input[type=submit], {FORM} button[type=submit]").first.click()
    for _ in range(20):
        time.sleep(1)
        if page.locator(CAPTCHA).count():
            return ApplyResult("verificacion", "Al enviar, el portal pidió una verificación (captcha): termina tú la postulación")
        text = page.inner_text("body")
        if ALREADY.search(text):
            return ApplyResult("ya_postulada")
        if DONE.search(text) or "/applications/new" not in page.url:
            return ApplyResult("enviada", "Confirmada por el portal")
    errors = [t.strip() for t in page.locator(f"{FORM} .error:visible, {FORM} [role=alert]:visible").all_inner_texts() if t.strip()]
    return ApplyResult("error", "El portal no confirmó el envío" + (": " + "; ".join(errors)[:300] if errors else ": revísalo tú"))
