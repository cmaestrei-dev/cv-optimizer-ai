"""Postular en AIRA (Grupo Falabella: Banco Falabella, Falabella.com, Sodimac…) con la sesión de la persona.

Verificado el 2026-11-23 con la cuenta del dueño, enviando una postulación real (Practicante Área de Sistemas):
- La oferta (`falabella.airavirtual.com/postula/<código>`) lleva, con sesión, al formulario (`/test/step/<id>/1`); sin
  sesión, al registro. La persona entra en la ventana del bot (`python -m runner entrar aira`; sin captcha).
- El formulario es una aplicación Vue: «Hoja de vida» (el componente `FileWithPreview` sube el archivo cuando se llama a
  su `changedFile`; AIRA lo guarda como `resume.pdf` de esa postulación y marca `RESUME_SOURCE = UPLOADED`),
  «Expectativa salarial» (obligatoria), preguntas de la empresa (`specific_questions_groups`; los años de experiencia
  son deslizadores `Slider` que avisan con `handleChangeRadiosSlider`), y dos casillas que vienen marcadas: «Guardar hoja
  de vida en mi perfil» (reemplazaría el CV del perfil por el de esta vacante) y «Recibir alertas»: se desmarcan.
- «ENVIAR POSTULACIÓN» guarda el paso 2; si falta algo, la página dice «Campo requerido». Enviada, la oferta muestra el
  «Estado postulación» con las pruebas: Personalidad (D32) e Inteligencia (CAT) las hace la persona (valen 12 meses para
  todas las postulaciones de Falabella); mientras tanto la postulación queda «Pendiente información».
Ante una verificación (captcha) el bot se detiene; nunca la resuelve.
"""

import re
import time
from collections.abc import Callable
from pathlib import Path

from runner.answers import INTERNSHIP_SALARY, bank_answer, to_integer
from runner.linkedin import ApplyResult, Question

Answerer = Callable[[list[Question]], dict[str, str]]
SEND = re.compile(r"enviar postulaci", re.I)
STATUS = "Estado postulación"
TESTS_PENDING = re.compile(r"(Personalidad|Inteligencia)[^.]{0,80}?Pendiente", re.I)

# El componente del formulario (el que tiene `uploadCv`) y sus preguntas, como las tiene la página.
_FORM = """() => {
  let el = document.querySelector('input[type=file]');
  while (el && !el.__vue__) el = el.parentElement;
  let vm = el && el.__vue__;
  while (vm && !(vm.$options.methods && vm.$options.methods.uploadCv)) vm = vm.$parent;
  window.__cvoForm = vm || null;
  if (!vm) return null;
  const general = vm.general_info_group || {};
  const groups = vm.specific_questions_groups || {};
  const questions = [];
  for (const list of Object.values(groups)) for (const q of (list || [])) questions.push({id: q.id, type: q.type, text: q.text,
    answer: q.answer, required: /required/.test((q.data || {}).param_validation || ''),
    options: [...document.querySelectorAll(`input[name='q_${q.id}']`)].map(r => r.value)});
  return {salary: general.SALARY ? general.SALARY.answer : null, source: general.RESUME_SOURCE ? general.RESUME_SOURCE.answer : null,
          questions};
}"""

# Marca un deslizador como lo hace su plugin: el componente `Slider` recibe el radio elegido.
_SLIDE = """([id, value]) => {
  const radio = document.querySelector(`input[name='q_${id}'][value='${value}']`);
  let el = radio; while (el && !(el.__vue__ && el.__vue__.$options.name === 'Slider')) el = el.parentElement;
  if (!radio || !el) return false;
  radio.checked = true; el.__vue__.handleChangeRadiosSlider([radio]); return true;
}"""

_ANSWER = """([id, value]) => { const vm = window.__cvoForm; for (const list of Object.values(vm.specific_questions_groups || {}))
  for (const q of (list || [])) if (q.id === id) { vm.$set(q, 'answer', value); return true; } return false; }"""

_UPLOAD = """() => { let el = document.querySelector('input[type=file]');
  while (el && !(el.__vue__ && el.__vue__.$options.name === 'FileWithPreview')) el = el.parentElement;
  if (!el) return false; el.__vue__.changedFile(); return true; }"""


def _text(page) -> str:
    return re.sub(r"\s+", " ", page.inner_text("body"))


def _form(page) -> dict | None:
    return page.evaluate(_FORM)


def apply(page, offer_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, contact: dict | None = None,
          overrides: dict[str, str] | None = None, cover: Callable[[], str] | None = None) -> ApplyResult:
    """Postula a una oferta de AIRA con el CV de la vacante."""
    overrides = overrides or {}
    page.goto(offer_url, wait_until="domcontentloaded")
    time.sleep(7)
    if "/register" in page.url or page.locator("input[type=password]:visible").count():
        return ApplyResult("sin_sesion", "El navegador del bot no tiene sesión de AIRA (Falabella): python -m runner entrar aira")
    text = _text(page)
    if STATUS in text and not page.locator("a, button").filter(has_text=SEND).count():
        return ApplyResult("ya_postulada")
    if re.search(r"captcha|verifica que eres humano", text, re.I):
        return ApplyResult("verificacion", "AIRA pidió una verificación: entra tú y complétala")
    form = _form(page)
    if not form:
        return ApplyResult("error", "No encontré el formulario de postulación de AIRA")

    missing = []
    for q in form["questions"]:
        if q["answer"] not in (None, ""):
            continue
        if q["type"] == "slider" and q["options"]:
            question = Question("radio", q["text"], True, "", q["options"], [str(q["id"])])
            value = (bank_answer(q["text"], overrides) or answerer([question]).get(q["text"]) or "").strip()
            years = to_integer(value) if value else None
            top = q["options"][-1]
            option = None if years is None else years if years in q["options"] else top if int(years) > int(top) else None
            if option is None or not page.evaluate(_SLIDE, [q["id"], option]):
                missing.append(q["text"])
        elif q["type"] in ("text", "textarea", "number"):
            question = Question("textarea" if q["type"] == "textarea" else "text", q["text"], True, "", [], [str(q["id"])],
                                numeric=q["type"] == "number")
            value = (bank_answer(q["text"], overrides) or answerer([question]).get(q["text"]) or "").strip()
            if not value or not page.evaluate(_ANSWER, [q["id"], value[:1000]]):
                missing.append(q["text"])
        elif q["required"]:
            missing.append(q["text"])  # un tipo de pregunta que el bot aún no sabe llenar
    if missing:
        return ApplyResult("saltada", "Preguntas de la empresa sin respuesta en tu banco ni en tu perfil", unanswered=missing)

    salary = page.locator("input[placeholder*='1.000.000']").first
    if salary.count():  # obligatoria: la de la vacante (rango que publica o 3 millones); en prácticas, el apoyo usual
        asked = Question("text", "Expectativa salarial (bruto mensual pesos COP)", True, "", [], ["salary"], numeric=True)
        amount = to_integer(answerer([asked]).get(asked.label) or "") or str(INTERNSHIP_SALARY)
        salary.fill("")
        salary.type(str(amount), delay=30)
        salary.press("Tab")

    page.locator("input[type=file]").first.set_input_files(str(cv_pdf))
    try:  # el componente sube el archivo de inmediato (guardado parcial del paso 1)
        with page.expect_response(lambda r: "save_answers" in r.url and r.request.method == "POST", timeout=20_000) as saved:
            page.evaluate(_UPLOAD)
        uploaded = saved.value.ok and (_form(page) or {}).get("source") == "UPLOADED"
    except Exception:  # noqa: BLE001 — sin respuesta del guardado no hay certeza de que el CV quedó
        uploaded = False
    if not uploaded:
        return ApplyResult("saltada", "No quedó adjunto el CV de esta vacante (no se envía con otro)")
    page.evaluate("""() => { for (const c of document.querySelectorAll('input[type=checkbox]')) {
        const t = ((c.closest('label, div') || {}).innerText || '');
        if (c.checked && /Guardar hoja de vida|Recibir alertas/.test(t)) c.click(); } }""")
    if not submit:
        return ApplyResult("revisada", "Modo prueba: formulario lleno y no se envió")

    page.locator("a:visible, button:visible").filter(has_text=SEND).first.click()
    for _ in range(20):
        time.sleep(1)
        text = _text(page)
        if "Campo requerido" in text:
            return ApplyResult("error", "AIRA marcó campos requeridos sin llenar: revísalo tú")
        if STATUS in text and not page.locator("a:visible, button:visible").filter(has_text=SEND).count():
            follow = ("Falabella pide dos pruebas (personalidad e inteligencia, 25 minutos, valen 12 meses): hazlas tú en "
                      "«Mis postulaciones» de AIRA; sin ellas la postulación queda «Pendiente información».") if TESTS_PENDING.search(text) else ""
            return ApplyResult("enviada", "Confirmada por AIRA (Estado postulación)", follow_up=follow)
    return ApplyResult("error", "AIRA no confirmó el envío: revísalo tú")
