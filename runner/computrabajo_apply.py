"""Postular en Computrabajo con la sesión de la persona (navegador del bot).

Lo verificado con la cuenta del dueño, sin postular (2026-11-18):
- «Aplicar» (`a[data-href-offer-apply]`) lleva a `/match/?oi=<código>` y postula de inmediato: no hay revisión.
  Si la oferta tiene preguntas de filtro, antes pasa por `/candidate/apply-kq`; si ya se había postulado,
  `/candidate/apply-exists`.
- La empresa ve la hoja de vida en línea (siempre la última versión) y el PDF marcado «por defecto» en
  `/candidate/cv/uploadcv`, que admite como máximo 10.
- Por eso el bot sube el CV de la vacante, lo marca por defecto, postula y deja otra vez por defecto el CV
  general. Para hacer espacio borra el PDF más viejo que subió él; nunca el general ni uno que no subió él.
- En modo prueba deja listo el CV y vuelve al general sin pulsar «Aplicar».
- Ante captcha o verificación se detiene; nunca la resuelve.
"""

import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from runner.answers import pick_option
from runner.linkedin import _FIELDS_JS, ApplyResult, Question

CANDIDATE = "https://candidato.co.computrabajo.com"
DOCS = CANDIDATE + "/candidate/cv/uploadcv"
MAX_DOCS = 10
SENT = re.compile(r"(te has postulado|ya (te )?postulaste|postulaci[oó]n (enviada|realizada|exitosa)|"
                  r"hoja de vida (fue )?enviada|has aplicado|aplicaste|candidatura (enviada|realizada))", re.I)
SUBMIT = re.compile(r"^(enviar|postularme|postular|aplicar|continuar|finalizar)", re.I)

Answerer = Callable[[list[Question]], dict[str, str]]


class ComputrabajoError(RuntimeError):
    """Algo de Computrabajo no salió como se esperaba: el mensaje dice qué; `status` es el resultado que se informa."""

    def __init__(self, message: str, status: str = "error"):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Doc:
    id: str
    name: str
    default: bool


_DOCS_JS = """() => [...document.querySelectorAll('input[name=rbPrincipal]')].map(r => {
  const link = r.closest('ul')?.querySelector('a[data-filecandidateid]');
  return {id: r.value, name: (link?.innerText || '').trim(), checked: r.checked};
}).filter(d => d.id && d.id !== '0')"""


def same_name(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return unicodedata.normalize("NFC", s).strip().lower()
    return norm(a) == norm(b)


def _challenge(page) -> bool:
    return page.locator("iframe[src*='captcha'], iframe[title*='captcha' i], iframe[src*='challenges.cloudflare']").count() > 0


def _logged_in(page) -> bool:
    try:
        return bool(page.evaluate("() => typeof window._IsUserLogged === 'function' && window._IsUserLogged()"))
    except Exception:  # noqa: BLE001
        return False


def _open_docs(page) -> None:
    page.goto(DOCS, wait_until="domcontentloaded")
    time.sleep(2)
    if "/acceso" in page.url or "/login" in page.url:
        raise ComputrabajoError("El navegador del bot no tiene sesión de Computrabajo: python -m runner entrar computrabajo",
                                "sin_sesion")


def documents(page) -> list[Doc]:
    if not page.url.startswith(DOCS):
        _open_docs(page)
    return [Doc(d["id"], d["name"], d["checked"]) for d in page.evaluate(_DOCS_JS)]


def set_default(page, doc_id: str) -> None:
    _open_docs(page)
    radio = page.locator(f"input[name=rbPrincipal][value='{doc_id}']")
    if not radio.count():
        raise ComputrabajoError("No encontré ese PDF en Computrabajo")
    if not radio.is_checked():
        # Un clic simple: la página se recarga al elegir, y check() de Playwright esperaría en vano que el botón
        # viejo quedara marcado (pasó en el Computrabajo real). Lo que cuenta se verifica abajo.
        with page.expect_navigation(wait_until="domcontentloaded"):
            radio.click(force=True)
        time.sleep(2)
    if not any(d.id == doc_id and d.default for d in documents(page)):
        raise ComputrabajoError("Computrabajo no dejó ese PDF por defecto")


def delete(page, doc: Doc) -> None:
    _open_docs(page)
    page.locator(f"[data-filecandidateid='{doc.id}']#it-delete").first.click()
    confirm = page.locator("#btDelete")
    confirm.wait_for(state="visible", timeout=15_000)
    with page.expect_navigation(wait_until="domcontentloaded"):
        confirm.click()
    time.sleep(2)
    if any(d.id == doc.id for d in documents(page)):
        raise ComputrabajoError(f"No se pudo borrar «{doc.name}»")


def upload(page, pdf: Path) -> Doc:
    _open_docs(page)
    with page.expect_navigation(wait_until="domcontentloaded", timeout=120_000):
        page.locator("[input-file]").set_input_files(str(pdf))  # el formulario se envía solo al elegir el archivo
    time.sleep(2)
    found = [d for d in documents(page) if same_name(d.name, pdf.name)]
    if not found:
        error = page.locator("#it-error").inner_text().strip() if page.locator("#it-error").count() else ""
        raise ComputrabajoError(f"Computrabajo no aceptó «{pdf.name}»{': ' + error if error else ''}")
    return found[-1]


def ensure_default(page, pdf: Path, uploaded: list[str], general: str) -> Doc:
    """Deja `pdf` como el PDF por defecto. `uploaded`: los que subió el bot, del más viejo al más nuevo (se actualiza)."""
    docs = documents(page)
    if same_name(pdf.name, general) and (mine := [d for d in docs if same_name(d.name, general)]):
        set_default(page, mine[0].id)
        return mine[0]
    for old in [d for d in docs if same_name(d.name, pdf.name)]:  # mismo nombre, quizá otro contenido: se sube de nuevo
        delete(page, old)
        uploaded[:] = [n for n in uploaded if not same_name(n, old.name)]
    docs = documents(page)
    while len(docs) >= MAX_DOCS:
        victim = next((d for name in uploaded for d in docs
                       if same_name(d.name, name) and not same_name(name, general)), None)
        if victim is None:
            raise ComputrabajoError("Computrabajo ya tiene 10 PDF y ninguno lo subió el bot: libera espacio en "
                                    "Hoja de vida → Hoja de Vida en Word/PDF", "sin_espacio")
        delete(page, victim)
        uploaded[:] = [n for n in uploaded if not same_name(n, victim.name)]
        docs = documents(page)
    doc = upload(page, pdf)
    if not same_name(pdf.name, general):
        uploaded.append(doc.name)
    set_default(page, doc.id)
    return doc


def _applied(page) -> bool:
    button = page.locator("[already-applied-btn]")
    return bool(button.count() and button.first.is_visible())


def _kq_form(page):
    """El formulario de las preguntas de filtro (no el buscador del encabezado, que también es un formulario)."""
    marked = page.locator("[form-apply-kq]")
    return marked.first if marked.count() else page.locator("#MainContainer form, main form").first


def _answer_questions(page, answerer: Answerer) -> list[str]:
    """Responde las preguntas de filtro. Devuelve las que quedaron sin respuesta (entonces no se envía)."""
    form = _kq_form(page)
    questions = [Question(q["kind"], q["label"], True, q["value"], q["options"], q["ids"], q.get("numeric", False))
                 for q in form.evaluate(_FIELDS_JS) if q["kind"] != "checkbox" and q["label"]]
    empty = [q for q in questions if not q.value]
    answers = answerer(empty) if empty else {}
    missing = []
    for q in empty:
        answer = answers.get(q.label, "")
        target = form.locator(f"[data-cvo='{q.ids[0]}']")
        if not answer:
            missing.append(q.label)
        elif q.kind in ("text", "textarea"):
            target.fill(answer)
        elif q.kind == "select" and (option := pick_option(answer, q.options)):
            target.select_option(label=option)
        elif q.kind == "radio" and (option := pick_option(answer, q.options)):
            form.locator(f"[data-cvo='{q.ids[q.options.index(option)]}']").check(force=True)
        else:
            missing.append(q.label)
    return missing


def apply(page, offer_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, general: Path,
          uploaded: list[str]) -> ApplyResult:
    page.goto(offer_url, wait_until="domcontentloaded")
    time.sleep(4)
    if _challenge(page):
        return ApplyResult("verificacion", page.url)
    if not _logged_in(page):
        return ApplyResult("sin_sesion", "El navegador del bot no tiene sesión de Computrabajo")
    if _applied(page):
        return ApplyResult("ya_postulada")
    if not page.locator("a[data-href-offer-apply]").count():
        return ApplyResult("saltada", "La oferta no tiene «Aplicar» (¿cerrada?)")
    try:
        ensure_default(page, cv_pdf, uploaded, general.name)
        if not submit:
            return ApplyResult("revisada", "Modo prueba: el CV quedó listo y no se pulsó «Aplicar»")
        page.goto(offer_url, wait_until="domcontentloaded")
        time.sleep(3)
        with page.expect_navigation(wait_until="domcontentloaded", timeout=90_000):
            page.locator("a[data-href-offer-apply]").first.click()
        time.sleep(3)
        for _ in range(3):
            if _challenge(page):
                return ApplyResult("verificacion", page.url)
            if "/acceso" in page.url or "/login" in page.url:
                return ApplyResult("sin_sesion", "Computrabajo pidió iniciar sesión")
            if "/apply-exists" in page.url:
                return ApplyResult("ya_postulada")
            if "/apply-kq" not in page.url:
                break
            if missing := _answer_questions(page, answerer):
                return ApplyResult("saltada", "Preguntas de filtro sin respuesta en tu perfil ni en tu banco",
                                   unanswered=missing)
            with page.expect_navigation(wait_until="domcontentloaded", timeout=90_000):
                _kq_form(page).get_by_role("button", name=SUBMIT).last.click()
            time.sleep(3)
        # Confirmación: el aviso de la página o la oferta marcada «Postulado».
        if page.get_by_text(SENT).count():
            return ApplyResult("enviada")
        page.goto(offer_url, wait_until="domcontentloaded")
        time.sleep(4)
        if _applied(page):
            return ApplyResult("enviada", "Confirmada en la oferta")
        return ApplyResult("error", f"No se confirmó la postulación (terminó en {page.url[:80]}): revísala en Computrabajo")
    except ComputrabajoError as e:
        return ApplyResult(e.status, str(e))
    except PlaywrightError as e:  # algo de la página cambió: esa vacante queda en error y la vuelta sigue
        return ApplyResult("error", f"La página de Computrabajo no respondió como se esperaba: {str(e).splitlines()[0][:150]}")
    finally:
        try:  # el CV general vuelve a quedar por defecto (para lo que postules tú a mano)
            ensure_default(page, general, uploaded, general.name)
        except ComputrabajoError as e:
            print(f"    Aviso: no se pudo dejar el CV general por defecto: {e}")
