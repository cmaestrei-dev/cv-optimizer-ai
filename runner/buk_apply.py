"""Postulaciones en Buk (Nequi, Ceiba, Quipux/LINQ, La Pipol…), semiautomáticas (autorizado por el dueño el 2026-11-27).

El primer paso lo hace la persona: «Postular» con su correo. Desde el navegador del bot, Buk muestra un captcha visible,
y el bot nunca los resuelve. Luego manda al bot de Telegram `/buk <enlace del formulario>` (lo que queda en la barra de
direcciones) y el bot hace lo demás:

1. Llena el formulario con sus datos, su banco de respuestas y el CV de esa vacante.
2. Lo envía («Enviar Respuesta» → «Enviar» → «Éxito»).
3. Aprueba el correo «Confirma tu correo para completar tu postulación» que Buk manda desde noreply@buk.co. Solo ese:
   remitente autenticado por el primer `Authentication-Results`, enviado por la misma empresa del formulario, y el botón
   «Confirmar correo» con destino en buk.co. Lo lee por IMAP en modo solo lectura, con la contraseña de aplicación.

Buk guarda cada campo al cambiarlo, pero el CV solo cuando se envía (verificado en Ceiba y Quipux, 2026-11-27)."""

import email
import html
import imaplib
import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from runner import config as cfg
from runner.answers import bank_answer, negative, normalize, pick_option
from runner.linkedin import ApplyResult, Question

Answerer = Callable[[list[Question]], dict[str, str]]

FORM_URL = re.compile(r"^https://([a-z0-9-]+)\.buk\.co/recruiting/surveys/[0-9a-f]{20,}/attempt_tokens/[0-9a-f]{20,}/edit_attempt/?$")
OFFER_URL = re.compile(r"^https://([a-z0-9-]+)\.buk\.co/(s|seleccions|trabaja-con-nosotros|work)/\S+$")
SENT = re.compile(r"(éxito|exito|respuesta enviada|ya (has )?(enviado|respondido))", re.I)
DOC_TYPES = re.compile(r"c[eé]dula de ciudadan[ií]a", re.I)

# Las preguntas del formulario, agrupadas por su id (`attempt[ID][answer_…]`), en orden. La pregunta es la primera
# línea del bloque que solo contiene los campos de ese id; «*» marca las obligatorias.
_FORM_JS = """() => {
  const clean = t => (t || '').replace(/\\s+/g, ' ').trim();
  const groups = new Map();
  document.querySelectorAll('[name^="attempt["]').forEach(el => {
    const m = el.name.match(/^attempt\\[(\\d+)\\]\\[(answer_\\w+)\\]/);
    if (!m || el.type === 'hidden' || !el.offsetParent) return;
    if (!groups.has(m[1])) groups.set(m[1], []);
    groups.get(m[1]).push(el);
  });
  const all = [...document.querySelectorAll('[name^="attempt["]')];
  const out = [];
  for (const [id, els] of groups) {
    let box = els[0].parentElement;
    while (box && !els.every(e => box.contains(e))) box = box.parentElement;
    while (box && box.parentElement && all.filter(e => box.parentElement.contains(e)).every(e => e.name.startsWith(`attempt[${id}]`)))
      box = box.parentElement;
    const first = (box ? box.innerText : '').split('\\n').map(clean).find(Boolean) || '';
    const el = els[0];
    const q = {id, label: clean(first.replace(/\\*/g, '')), required: first.includes('*') || els.some(e => e.required
               || e.getAttribute('aria-required') === 'true'), kind: 'texto', name: el.name, options: [], value: '', max: 0};
    if (el.type === 'radio') {
      q.kind = 'radio';
      q.options = els.map(r => clean(r.value));
      const on = els.find(r => r.checked); q.value = on ? clean(on.value) : '';
    } else if (el.type === 'checkbox') {
      q.kind = 'casillas'; q.options = els.map(r => clean(r.value)); q.value = els.filter(r => r.checked).map(r => r.value).join(';');
    } else if (el.tagName === 'SELECT') {
      q.kind = 'lista'; q.options = [...el.options].filter(o => o.value).map(o => clean(o.text));
      q.value = el.value ? clean(el.options[el.selectedIndex].text) : '';
    } else if (el.type === 'file') {
      q.kind = 'archivo';
    } else {
      q.kind = el.tagName === 'TEXTAREA' ? 'parrafo' : (el.type === 'number' ? 'numero' : 'texto');
      q.value = el.value; q.max = el.maxLength > 0 ? el.maxLength : 0;
    }
    out.push(q);
  }
  return out;
}"""


@dataclass
class Form:
    host: str  # «ceiba» de ceiba.buk.co
    company: str
    role: str
    questions: list[dict] = field(default_factory=list)


def form_host(url: str) -> str:
    match = FORM_URL.match(url.strip())
    return match.group(1) if match else ""


def read_form(page, url: str) -> Form:
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector('[name^="attempt["]', state="attached", timeout=30_000)
    time.sleep(1.5)
    title = page.title()
    company = re.sub(r"^\s*Buk\s*-\s*", "", title).strip()
    header = page.locator("text=/Postulando a/").first
    role = re.sub(r"^\s*Postulando a\s*", "", header.inner_text()).split("|")[0].strip() if header.count() else ""
    return Form(form_host(url), company, role, page.evaluate(_FORM_JS))


def _names(full: str) -> tuple[str, str, str]:
    """«Camilo Andres Maestre Iglesias» → («Camilo Andres», «Maestre», «Iglesias»): en Colombia, dos nombres y dos
    apellidos; con tres palabras, un nombre."""
    parts = full.split()
    if len(parts) >= 4:
        return " ".join(parts[:-2]), parts[-2], parts[-1]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else ""), ""


def contact_answer(label: str, contact: dict, legal_name: str) -> str | None:
    """Datos de contacto por la etiqueta exacta del campo (Nombre, Primer Apellido, Celular…)."""
    q = normalize(label)
    first, last1, last2 = _names(legal_name or contact.get("full_name", ""))
    phone = re.sub(r"\D", "", contact.get("phone", ""))
    phone = phone[2:] if phone.startswith("57") and len(phone) == 12 else phone
    rules = [
        (r"^(nombres?|primer nombre)$", first),
        (r"^nombre completo$", " ".join(x for x in (first, last1, last2) if x)),
        (r"^(primer apellido|apellido)$", last1),
        (r"^apellidos$", " ".join(x for x in (last1, last2) if x)),
        (r"^segundo apellido$", last2),
        (r"^(email|e-mail|correo|correo electronico)$", contact.get("email", "")),
        (r"^(celular|telefono celular|movil|numero de celular|telefono|telefono de contacto|numero de telefono)$", phone),
        (r"^(linkedin|perfil de linkedin|url de linkedin)$", contact.get("linkedin_url", "")),
        (r"^(ciudad|ciudad de residencia|municipio de residencia|ciudad donde vives)$", contact.get("city", "")),
    ]
    return next((value for pattern, value in rules if re.match(pattern, q)), None)


def answer(form: Form, answerer: Answerer, *, contact: dict, overrides: dict[str, str], bank: dict[str, str],
           legal_name: str) -> tuple[dict[str, str], list[str]]:
    """Qué poner en cada pregunta obligatoria vacía (o con algo útil en las opcionales de contacto). Devuelve las
    respuestas por id y las preguntas obligatorias sin respuesta."""
    out, missing = {}, []
    for q in form.questions:
        if q["kind"] == "archivo" or (q["value"] or "").strip():
            continue
        label = q["label"]
        value = contact_answer(label, contact, legal_name)
        if not q["required"]:  # las opcionales solo con datos de contacto (nada de adivinar dirección o fecha)
            if value:
                out[q["id"]] = value
            continue
        if value is None and re.search(r"(numero|n[°º]) de (documento|identificacion|cedula)|^documento$|^cedula", normalize(label)):
            value = bank_answer("numero de cedula", bank) or bank_answer("numero de documento de identidad", bank)
        if value is None and q["kind"] in ("radio", "lista") and any(DOC_TYPES.search(o) for o in q["options"]):
            value = next(o for o in q["options"] if DOC_TYPES.search(o))
        if value is None:
            value = bank_answer(label, overrides)
        if value is None:
            question = Question("radio" if q["options"] else ("textarea" if q["kind"] == "parrafo" else "text"), label, True,
                                "", q["options"], [q["name"]], numeric=q["kind"] == "numero")
            value = answerer([question]).get(label)
        value = (value or "").strip()
        if q["options"] and value:
            option = pick_option(value, q["options"])
            value = option if option and not (negative(option) and not normalize(value).startswith("no")) else ""
        if value:
            out[q["id"]] = value[: q["max"]] if q.get("max") else value
        else:
            missing.append(label)
    return out, missing


def _fill(page, form: Form, answers: dict[str, str], cv_pdf: Path) -> None:
    for q in form.questions:
        value = answers.get(q["id"])
        if q["kind"] == "archivo":
            page.locator(f'[name="{q["name"]}"]').set_input_files(str(cv_pdf))
            time.sleep(1.5)
            continue
        if not value:
            continue
        if q["kind"] == "radio":
            page.locator(f'input[type=radio][name="{q["name"]}"][value="{value}"]').check(force=True)
            page.locator(f'input[type=radio][name="{q["name"]}"][value="{value}"]').dispatch_event("change")
        elif q["kind"] == "lista":
            page.locator(f'select[name="{q["name"]}"]').select_option(label=value)
        else:
            box = page.locator(f'[name="{q["name"]}"]')
            box.fill(value)
            box.dispatch_event("change")
            box.press("Tab")
        time.sleep(0.8)  # Buk guarda cada campo al cambiarlo


def apply(page, form_url: str, cv_pdf: Path, answerer: Answerer, *, submit: bool, contact: dict, overrides: dict[str, str],
          bank: dict[str, str], legal_name: str = "") -> ApplyResult:
    """Llena y envía el formulario de Buk (la confirmación por correo va aparte: `confirm_by_email`)."""
    if not form_host(form_url):
        return ApplyResult("error", "El enlace no es un formulario de Buk")
    form = read_form(page, form_url)
    if SENT.search(page.inner_text("body")[:2000]) and not form.questions:
        return ApplyResult("ya_postulada", "Este formulario ya estaba enviado")
    answers, missing = answer(form, answerer, contact=contact, overrides=overrides, bank=bank, legal_name=legal_name)
    if missing:
        return ApplyResult("saltada", "Preguntas sin respuesta en tu banco ni en tu perfil", unanswered=missing)
    _fill(page, form, answers, cv_pdf)
    if not submit:
        return ApplyResult("revisada", "Modo prueba: formulario lleno y no se envió")
    page.get_by_role("button", name=re.compile(r"^\s*Enviar Respuesta\s*$", re.I)).click()
    confirm = page.get_by_role("button", name=re.compile(r"^\s*(Enviar|Sí, enviar|Confirmar)\s*$", re.I))
    try:
        confirm.first.wait_for(state="visible", timeout=8_000)
        confirm.first.click()
    except Exception:  # noqa: BLE001 — algunos formularios envían sin confirmar
        pass
    for _ in range(20):
        time.sleep(1)
        body = page.inner_text("body")
        if SENT.search(body):
            return ApplyResult("enviada", "Buk respondió «Éxito»; falta confirmar el correo")
        if re.search(r"(no puede estar en blanco|es obligatori|requerid)", body, re.I):
            return ApplyResult("error", "Buk pidió campos obligatorios: " + " ".join(re.findall(r"[^.\n]*(?:en blanco|obligatori|requerid)[^.\n]*", body, re.I))[:300])
    return ApplyResult("error", "Buk no mostró «Éxito» después de enviar")


# --- el correo de confirmación ---

CONFIRM_SUBJECT = "Confirma tu correo"
_ANCHOR = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)


def authenticated(msg) -> bool:
    """El primer `Authentication-Results` (el de Gmail, que el remitente no puede falsificar) dice que buk.co firmó."""
    first = (msg.get_all("Authentication-Results") or [""])[0]
    return first.strip().startswith("mx.google.com") and bool(
        re.search(r"dkim=pass[^;]*header\.(d|i)=@?buk\.co\b", first) or re.search(r"dmarc=pass[^;]*header\.from=buk\.co\b", first))


def confirm_link(msg, host: str) -> str:
    """El botón «Confirmar correo» de un correo de Buk enviado por esa empresa (`host`.buk.co), o «»."""
    body = next((p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace")
                 for p in msg.walk() if p.get_content_type() == "text/html"), "")
    visible = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))
    if f"{host}.buk.co" not in visible:
        return ""
    for href, inner in _ANCHOR.findall(body):
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", inner))).strip()
        parsed = urlparse(html.unescape(href))
        if re.fullmatch(r"confirmar correo", text, re.I) and parsed.scheme == "https" and (
                parsed.hostname or "").endswith(".buk.co"):
            return html.unescape(href)
    return ""


def find_confirmation(sender: str, secret: str, host: str, since: datetime, *, timeout: int = 30) -> str:
    """El enlace de confirmación más reciente de esa empresa, llegado después de `since` (solo lectura: no marca nada)."""
    with imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=timeout) as box:
        box.login(sender, secret)
        box.select("INBOX", readonly=True)
        _, data = box.search(None, f'(FROM "noreply@buk.co" SINCE {since:%d-%b-%Y})')
        for num in reversed(data[0].split()[-20:]):
            _, raw = box.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(raw[0][1])
            if CONFIRM_SUBJECT.lower() not in str(make_header(decode_header(msg.get("Subject", "")))).lower():
                continue
            try:
                received = parsedate_to_datetime(msg.get("Date", ""))
            except (TypeError, ValueError):
                continue
            if received.tzinfo is None:
                received = received.replace(tzinfo=UTC)
            if received < since - timedelta(minutes=2) or not authenticated(msg):
                continue
            if link := confirm_link(msg, host):
                return link
    return ""


def confirm_by_email(page, sender: str, secret: str, host: str, since: datetime, *, wait_seconds: int = 240,
                     finder=find_confirmation) -> str:
    """Espera el correo de Buk y pulsa «Confirmar correo». Devuelve «» si quedó confirmada o el motivo si no."""
    deadline = time.monotonic() + wait_seconds
    link = ""
    while not link and time.monotonic() < deadline:
        try:
            link = finder(sender, secret, host, since)
        except (imaplib.IMAP4.error, OSError) as e:
            return f"no pude leer tu correo ({type(e).__name__})"
        if not link:
            time.sleep(15)
    if not link:
        return "no llegó el correo de confirmación de Buk"
    page.goto(link, wait_until="domcontentloaded")
    time.sleep(3)
    final = (urlparse(page.url).hostname or "")
    if not final.endswith(".buk.co"):
        return f"la confirmación terminó fuera de Buk ({final})"
    return ""


def since_now() -> datetime:
    return datetime.now(UTC)


# --- la cola de formularios que manda la persona por Telegram (`/buk`) ---

QUEUE = cfg.DATA_DIR / "buk_cola.json"


def read_queue() -> list[dict]:
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [x for x in data if isinstance(x, dict) and form_host(x.get("form", ""))]


def write_queue(items: list[dict]) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(QUEUE.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, QUEUE)


def enqueue(form: str, offer: str = "") -> bool:
    """Agrega un formulario a la cola (False si ya estaba pendiente)."""
    items = read_queue()
    if any(x["form"] == form and x.get("estado") == "pendiente" for x in items):
        return False
    items = [x for x in items if x["form"] != form]
    items.append({"form": form, "offer": offer, "cuando": datetime.now(UTC).isoformat(timespec="seconds"), "estado": "pendiente"})
    write_queue(items)
    return True
