"""Postular en Gupy (Stefanini y las demás empresas que lo usan) con la sesión de la persona en el navegador del bot.

Verificado el 2026-11-23 con la cuenta del dueño, terminando una postulación real (Help Desk Analyst L1, Stefanini):
- El acceso de Gupy tiene el captcha de Cloudflare, que rechaza la ventana que maneja el bot: la persona entra en un
  Chrome normal con el perfil del bot (`python -m runner entrar gupy`) y el bot usa esa sesión. En las páginas de las
  ofertas no apareció Cloudflare.
- Una cuenta sirve para todas las empresas de Gupy. Gupy envía la hoja de vida de Gupy (no un PDF por vacante): la
  completa la persona una vez (se llenó desde el CV general).
- Pasos: `<sitio>/candidates/jobs/<id>/apply` → (aviso «Actualiza tus datos»: «Recordarme después») → «Continuar» →
  «Información adicional» (¿te indicó alguien de la empresa? No; ¿trabajas en la empresa? No; ¿dónde la encontraste?
  «Sitio de la empresa») → «Guardar y continuar» → «Preguntas creadas por la empresa» («Responder ahora»; las de
  Stefanini no cargaron: su servicio respondió 404 y la página quedó sin preguntas) → «Guardar y continuar» → aviso
  opcional «Preséntate» → «Finalizar candidatura» → «¡Candidatura finalizada!».
- Las respuestas a las preguntas de la empresa no se pueden editar después: si alguna queda sin respuesta, no se
  guarda nada y la postulación queda en curso en Gupy (se reintenta cuando haya respuesta).
Ante una verificación (Cloudflare, captcha) el bot se detiene; nunca la resuelve.
"""

import re
import time
from collections.abc import Callable
from pathlib import Path

from runner.answers import bank_answer, negative, pick_option, to_integer
from runner.linkedin import ApplyResult, Question

Answerer = Callable[[list[Question]], dict[str, str]]
DONE = re.compile(r"candidatura (finalizada|enviada|conclu[ií]da)|postulaci[oó]n (finalizada|enviada)", re.I)
ALREADY = re.compile(r"ya (te )?(postulaste|aplicaste|est[aá]s participando)|ya (has|te has) (postulado|candidatado)|"
                     r"candidatura (ya )?(realizada|en an[aá]lisis)", re.I)
CHALLENGE = re.compile(r"verify you are human|verifica que eres humano|checking your browser|cf-challenge", re.I)
SOURCE = "Sitio de la empresa"  # «¿Dónde encontraste esta vacante?»

# Las preguntas de la empresa que se ven: grupos de opciones (por `name`) y campos de texto, con su enunciado.
_QUESTIONS = """() => {
  const label = el => {
    const own = el.labels && el.labels[0] ? el.labels[0].innerText : '';
    let n = el.closest('fieldset, [role=radiogroup], [role=group]') || el.parentElement;
    for (let i = 0; i < 5 && n; i++, n = n.parentElement) {
      const head = n.querySelector('legend, h2, h3, h4, p, label');
      if (head && head.innerText.trim() && head.innerText.trim() !== own.trim()) return head.innerText;
    }
    return own || el.getAttribute('aria-label') || el.placeholder || '';
  };
  const out = [], seen = new Set();
  for (const el of document.querySelectorAll('input:not([type=hidden]), textarea, select')) {
    if (el.offsetParent === null || el.type === 'search' || /^(radioGroupIs|howDidYouHear|skills)/.test(el.name || el.id)) continue;
    if (el.type === 'radio' || el.type === 'checkbox') {
      if (seen.has(el.name)) continue; seen.add(el.name);
      const group = [...document.querySelectorAll(`input[name="${el.name}"]`)];
      out.push({kind: 'radio', name: el.name, label: label(el).replace(/\\s+/g, ' ').trim(),
                options: group.map(g => [(g.labels && g.labels[0] ? g.labels[0].innerText : g.value).trim(), g.id || g.value]),
                answered: group.some(g => g.checked)});
    } else {
      out.push({kind: el.tagName === 'TEXTAREA' ? 'textarea' : 'text', name: el.name || el.id, id: el.id,
                label: label(el).replace(/\\s+/g, ' ').trim(), numeric: el.type === 'number', options: [],
                answered: !!String(el.value || '').trim()});
    }
  }
  return out;
}"""


def apply_url(offer_url: str) -> str:
    match = re.search(r"^(https://[^/]+)/(?:candidates/)?jobs/(\d+)", offer_url)
    if not match:
        raise ValueError(f"no reconozco la oferta de Gupy: {offer_url}")
    return f"{match.group(1)}/candidates/jobs/{match.group(2)}/apply?jobBoardSource=gupy_public_page"


def _button(page, name: str):
    return page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(name)}\s*$", re.I))


def _text(page) -> str:
    return re.sub(r"\s+", " ", page.inner_text("body"))


def _click(page, name: str, wait: float = 15) -> bool:
    """Pulsa el botón y espera a que Gupy cambie de pantalla (hasta `wait` segundos)."""
    button = _button(page, name)
    if not button.count():
        return False
    before = _text(page)
    button.first.click()
    for _ in range(int(wait * 2)):
        page.wait_for_timeout(500)
        if _text(page) != before:
            break
    page.wait_for_timeout(800)  # que termine de dibujar
    return True


def _additional_info(page) -> None:
    for name in ("radioGroupIsIndicatedTitle", "radioGroupIsCompanyEmployeeTitle"):
        page.evaluate("n => { const r = document.querySelector(`input[type=radio][name='${n}'][value='no']`);"
                      " if (r && !r.checked) r.click(); }", name)
        time.sleep(0.4)
    source = page.locator("input[name='howDidYouHearAboutUs']")
    if source.count() and not source.input_value().strip():
        source.click()
        source.type(SOURCE[:5], delay=60)
        time.sleep(1.2)
        item = page.locator("[role=option]:visible, li:visible").filter(has_text=re.compile(rf"^\s*{SOURCE}\s*$"))
        if item.count():
            item.first.click()
            time.sleep(0.6)


def _answer_questions(page, answerer: Answerer, overrides: dict[str, str]) -> list[str]:
    """Responde las preguntas de la empresa que se ven. Devuelve las que quedaron sin respuesta (no se guarda nada)."""
    plan, missing = [], []
    for q in page.evaluate(_QUESTIONS):
        if q["answered"] or not q["label"]:
            continue
        options = [o for o, _ in q["options"]]
        question = Question("radio" if options else q["kind"], q["label"], True, "", options, [q["name"]],
                            numeric=q.get("numeric", False))
        value = (bank_answer(q["label"], overrides) or answerer([question]).get(q["label"]) or "").strip()
        if options:
            option = pick_option(value, options) if value else None
            if not option or (negative(option) and not value.lower().startswith("no")):
                missing.append(q["label"])
            else:
                plan.append((q, dict(q["options"])[option]))
        elif q.get("numeric") and not to_integer(value):
            missing.append(q["label"])
        elif value:
            plan.append((q, to_integer(value) if q.get("numeric") else value))
        else:
            missing.append(q["label"])
    if missing:
        return missing  # las respuestas no se pueden editar después: nada a medias
    for q, value in plan:
        if q["kind"] == "radio":
            page.evaluate("v => { const r = document.getElementById(v) || document.querySelector(`input[value='${v}']`);"
                          " if (r && !r.checked) r.click(); }", value)
        else:
            field = page.locator(f"[id='{q['id']}']" if q.get("id") else f"[name='{q['name']}']").first
            field.scroll_into_view_if_needed()
            field.fill(str(value)[:2000])
        time.sleep(0.4)
    return []


def apply(page, offer_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, contact: dict | None = None,
          overrides: dict[str, str] | None = None, cover: Callable[[], str] | None = None) -> ApplyResult:
    """Postula a una oferta de Gupy con la hoja de vida de Gupy de la persona. `cv_pdf` no se envía (queda en la app)."""
    overrides = overrides or {}
    page.goto(apply_url(offer_url), wait_until="domcontentloaded")
    time.sleep(6)
    text = _text(page)
    if CHALLENGE.search(text):
        return ApplyResult("verificacion", "Gupy pidió una verificación (Cloudflare): entra tú y complétala")
    if "/signin" in page.url or "login" in page.url or page.locator("input[type=password]:visible").count():
        return ApplyResult("sin_sesion", "El navegador del bot no tiene sesión de Gupy: python -m runner entrar gupy")
    if ALREADY.search(text) or DONE.search(text):
        return ApplyResult("ya_postulada")
    if "completar tu Currículum" in text or "Completar currículum" in text:
        return ApplyResult("perfil", "Gupy pide completar tu hoja de vida antes de postular: complétala en Gupy")
    _click(page, "Recordarme después", 3)
    for _ in range(8):  # cada paso lleva al siguiente; se avanza hasta las preguntas o el final
        text = _text(page)
        if _button(page, "Finalizar candidatura").count():
            break
        if "Información adicional" in text:
            _additional_info(page)
            if not _click(page, "Guardar y continuar", 8):
                return ApplyResult("error", "No encontré «Guardar y continuar» en la información adicional")
            continue
        if _click(page, "Responder ahora", 8):
            missing = _answer_questions(page, answerer, overrides)
            if missing:
                return ApplyResult("saltada", "Preguntas de la empresa sin respuesta en tu banco ni en tu perfil",
                                   unanswered=missing)
            if not submit:
                return ApplyResult("revisada", "Modo prueba: todo listo antes de guardar las respuestas (no se envió)")
            if not _click(page, "Guardar y continuar", 10):
                return ApplyResult("error", "No encontré «Guardar y continuar» en las preguntas")
            continue
        if not (_click(page, "Continuar", 6) or _click(page, "Continuar Candidatura", 6)):
            break
    if not _button(page, "Finalizar candidatura").count():
        return ApplyResult("error", "No llegué a «Finalizar candidatura»: " + _text(page)[:160])
    if not submit:
        return ApplyResult("revisada", "Modo prueba: llegó a «Finalizar candidatura» y no se envió")
    _click(page, "Finalizar candidatura", 10)
    text = _text(page)
    if DONE.search(text):
        follow = "Gupy pide pruebas o pasos adicionales: hazlos tú en tu postulación" if re.search(r"\b(test|prueba)s?\b.*pendiente", text, re.I) else ""
        return ApplyResult("enviada", "Confirmada por Gupy: «Candidatura finalizada»", follow_up=follow)
    return ApplyResult("error", "Gupy no confirmó la postulación: " + text[:200])
