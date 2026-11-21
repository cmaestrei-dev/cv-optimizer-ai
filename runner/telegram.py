"""Bot de Telegram del dueño: avisos de lo que solo él puede hacer y control del bot desde el celular.

- Corre en el computador del dueño (`python -m runner telegram`), con long polling: no abre puertos ni webhooks.
- Solo atiende el chat que se emparejó con un código de un solo uso; los mensajes de cualquier otro chat se ignoran.
- El token se pide oculto y queda en un archivo 0600; nunca se imprime ni se envía a la app.
- No escribe el estado del bot (lo escriben las vueltas): las pausas van a `control.json` y las respuestas nuevas a
  `respuestas_extra.json`, que el bot lee al empezar. Así una vuelta en curso nunca pisa lo que se pidió aquí.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from runner import config as cfg
from runner.answers import normalize
from runner.state import State

TOKEN_FILE = cfg.CONFIG_DIR / "telegram"
CHAT_FILE = cfg.CONFIG_DIR / "telegram_chat"
CODE_FILE = cfg.CONFIG_DIR / "telegram_codigo"  # código de emparejamiento pendiente (se borra al usarlo)
CONTROL_FILE = cfg.DATA_DIR / "control.json"
EXTRA_ANSWERS = cfg.EXTRA_ANSWERS_FILE
MANUAL_FILE = cfg.DATA_DIR / "manuales.json"  # las agrega el bot (`python -m runner manual`)
MANUAL_DONE = cfg.DATA_DIR / "manuales_hechas.json"  # las marca la persona por Telegram
API = "https://api.telegram.org/bot{token}/{method}"
TOKEN_RE = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{30,}$")
HELP = """Comandos:
/estado: qué hizo hoy el bot, pausas y sesiones
/hoy: las postulaciones enviadas hoy
/vuelta: correr una vuelta ahora
/pausar [horas]: no correr vueltas (24 h si no dices)
/reanudar: quitar la pausa
/preguntas: preguntas de filtro que el bot no supo responder
/responder N texto: tu respuesta a la pregunta N (queda en tu banco y esas vacantes se reintentan)
/manuales: postulaciones que debes enviar tú (captcha, cédula o cuenta en su sitio)
/hecha N: marcar como enviada la postulación manual N"""


class TelegramError(RuntimeError):
    """Telegram no respondió como se esperaba (el mensaje nunca incluye el token)."""


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


class Client:
    def __init__(self, token: str, *, timeout: float = 70):
        self.token, self.timeout = token, timeout

    def call(self, method: str, **params) -> object:
        data = json.dumps(params).encode()
        request = urllib.request.Request(API.format(token=self.token, method=method), data=data,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise TelegramError(f"Telegram respondió {e.code} a {method}") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            raise TelegramError(f"No se pudo hablar con Telegram ({method})") from None
        if not body.get("ok"):
            raise TelegramError(f"Telegram rechazó {method}: {str(body.get('description', ''))[:100]}")
        return body.get("result")

    def send(self, chat_id: int, text: str) -> None:
        for start in range(0, len(text), 3900):  # Telegram admite 4096 caracteres por mensaje
            self.call("sendMessage", chat_id=chat_id, text=text[start:start + 3900], disable_web_page_preview=True)

    def send_document(self, chat_id: int, path: Path, caption: str = "") -> None:
        """Envía un archivo (p. ej. el CV en PDF). Telegram admite hasta 50 MB."""
        import secrets as _secrets

        boundary = "----cvo" + _secrets.token_hex(12)
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode()]
        if caption:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1000]}\r\n'.encode())
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{path.name}"\r\n'
                      "Content-Type: application/pdf\r\n\r\n").encode() + path.read_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        request = urllib.request.Request(API.format(token=self.token, method="sendDocument"), data=b"".join(parts),
                                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            raise TelegramError("No se pudo enviar el archivo por Telegram") from None
        if not body.get("ok"):
            raise TelegramError(f"Telegram rechazó el archivo: {str(body.get('description', ''))[:100]}")

    def updates(self, offset: int, wait: int = 50) -> list[dict]:
        return self.call("getUpdates", offset=offset, timeout=wait, allowed_updates=["message"]) or []


# ---------- configuración ----------

def save_token(token: str) -> None:
    token = token.strip()
    if not TOKEN_RE.match(token):
        raise TelegramError("Ese no parece un token de BotFather (números, dos puntos y una clave larga).")
    _write_private(TOKEN_FILE, token + "\n")


def token() -> str:
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def chat_id() -> int | None:
    try:
        return int(CHAT_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def pair(client: Client, code: str, *, minutes: float = 10, offset: int = 0) -> int | None:
    """Espera «/start <código>» y guarda ese chat como el único que el bot atiende."""
    deadline = time.monotonic() + minutes * 60
    while time.monotonic() < deadline:
        try:
            updates = client.updates(offset, wait=20)
        except TelegramError as e:
            print(e)
            time.sleep(15)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message") or {}
            text, chat_info = (message.get("text") or "").strip(), message.get("chat", {})
            if chat_info.get("type") != "private":
                continue
            if text == f"/start {code}":
                chat = int(chat_info["id"])
                _write_private(CHAT_FILE, f"{chat}\n")
                CODE_FILE.unlink(missing_ok=True)
                client.call("getUpdates", offset=offset, timeout=0)  # marca como leídos los mensajes de antes
                return chat
            if text.startswith("/start"):  # p. ej. el botón «Iniciar», que no lleva el código
                client.send(int(chat_info["id"]), "Para emparejar, escribe /start seguido del código que muestra tu computador.")
    return None


def pending_code() -> str:
    try:
        return CODE_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def save_code(code: str) -> None:
    _write_private(CODE_FILE, code + "\n")


def new_code() -> str:
    return f"{secrets.randbelow(900000) + 100000}"


# ---------- control y respuestas que lee el bot ----------

def paused_until() -> datetime | None:
    raw = _read_json(CONTROL_FILE, {}).get("pausa_hasta")
    until = datetime.fromisoformat(raw) if raw else None
    return until if until and until > datetime.now(UTC) else None


def extra_answers() -> dict[str, str]:
    data = _read_json(EXTRA_ANSWERS, {})
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def manual_items() -> list[dict]:
    """Las postulaciones manuales pendientes (las que la persona no ha marcado como enviadas)."""
    done = set(_read_json(MANUAL_DONE, []))
    items = _read_json(MANUAL_FILE, [])
    return [i for i in items if isinstance(i, dict) and i.get("id") not in done] if isinstance(items, list) else []


def manual_message(item: dict) -> str:
    lines = [f"Postulación para enviar TÚ: {item.get('titulo', '')} — {item.get('empresa', '')}"]
    if item.get("puntaje") is not None:
        lines[0] += f" (compatibilidad {item['puntaje']})"
    lines.append(item.get("url", ""))
    if item.get("motivo"):
        lines.append(f"Por qué tú: {item['motivo']}")
    if item.get("nota"):
        lines.append(item["nota"])
    lines.append("Cuando la envíes: /manuales y luego /hecha N")
    return "\n".join(line for line in lines if line)


def send_manual(item: dict) -> bool:
    """Envía por Telegram una postulación manual con su CV. Nunca falla la vuelta."""
    tok, chat = token(), chat_id()
    if not tok or not chat:
        return False
    client = Client(tok, timeout=60)
    try:
        client.send(chat, manual_message(item))
        if item.get("cv") and Path(item["cv"]).is_file():
            client.send_document(chat, Path(item["cv"]), caption=f"CV para {item.get('empresa', '')}")
        if item.get("respuestas") and Path(item["respuestas"]).is_file():
            client.send(chat, "Respuestas sugeridas (ajústalas a tu voz):\n\n" + Path(item["respuestas"]).read_text(encoding="utf-8")[:3500])
        return True
    except TelegramError as e:
        print(f"Postulación manual no enviada por Telegram: {e}")
        return False


def notify(text: str) -> bool:
    """Envía un aviso al dueño si Telegram está configurado. Nunca falla la vuelta."""
    tok, chat = token(), chat_id()
    if not tok or not chat:
        return False
    try:
        Client(tok, timeout=20).send(chat, text)
        return True
    except TelegramError as e:
        print(f"Aviso por Telegram no enviado: {e}")
        return False


# ---------- comandos ----------

def pending_questions(state: State) -> list[str]:
    """Las preguntas de filtro de las vacantes saltadas que todavía no tienen respuesta en el banco."""
    from runner.answers import bank_answer

    bank = {**_bank(), **extra_answers()}
    seen, out = set(), []
    for v in state.data["vistas"].values():
        if v.get("estado") != "saltada":
            continue
        for q in v.get("preguntas") or []:
            key = normalize(q)
            if key and key not in seen and bank_answer(q, bank) is None:
                seen.add(key)
                out.append(q)
    return out


def _bank() -> dict[str, str]:
    try:
        return cfg.load().answers
    except cfg.ConfigError:
        return {}


def _status_text(state: State) -> str:
    lines = [f"Hoy ({date.today():%d/%m}):"]
    def key(kind: str, portal: str) -> str:
        return kind if portal == "linkedin" else f"{kind}_{portal}"

    for portal, name in cfg.PORTALS.items():
        sent, ready = state.today(key("enviadas", portal)), state.today(key("preparadas", portal))
        waiting = sum(1 for v in state.data["vistas"].values() if v.get("estado") == "preparada"
                      and v.get("portal", "linkedin") == portal)
        lines.append(f"· {name}: {sent} enviadas, {ready} preparadas hoy, {waiting} en espera")
        for kind in ("cuenta", "busqueda"):
            until = state.pause_until(key(kind, portal))
            if until and until > datetime.now(UTC):
                lines.append(f"  en pausa ({kind}) hasta {until.astimezone():%d/%m %H:%M}: {state.pause_reason(key(kind, portal))[:80]}")
    if until := paused_until():
        lines.append(f"Vueltas en pausa (por ti) hasta {until.astimezone():%d/%m %H:%M}.")
    if lost := state.data.get("sesion_perdida"):
        lines.append("Sesión perdida en: " + ", ".join(cfg.PORTALS.get(p, p) for p in lost) + " (entra tú en el navegador del bot).")
    if questions := pending_questions(state):
        lines.append(f"{len(questions)} preguntas sin respuesta: /preguntas")
    lines.append(f"Próxima vuelta: {_next_round() or 'no programada'}")
    return "\n".join(lines)


def _next_round() -> str:
    if not shutil.which("systemctl"):
        return ""
    try:
        out = subprocess.run(["systemctl", "--user", "list-timers", "cv-optimizer-bot.timer", "--no-pager"],
                             capture_output=True, text=True, timeout=15, check=False).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return ""
    return " ".join(out[1].split()[:4]) if len(out) > 1 and "cv-optimizer-bot" in out[1] else ""


def _today_sent(state: State) -> str:
    today = date.today().isoformat()
    sent = [v for v in state.data["vistas"].values() if v.get("estado") == "enviada" and str(v.get("cuando", "")).startswith(today)]
    if not sent:
        return "Hoy todavía no hay postulaciones enviadas."
    rows = [f"· {cfg.PORTALS.get(v.get('portal', 'linkedin'), '')} ({v.get('puntaje', '—')}): {v.get('url', '')}" for v in sent]
    return f"Enviadas hoy ({len(sent)}):\n" + "\n".join(rows)


def _start_round() -> str:
    if not shutil.which("systemctl"):
        return "Este computador no tiene systemd: corre tú «python -m runner diario»."
    done = subprocess.run(["systemctl", "--user", "start", "--no-block", "cv-optimizer-bot.service"],
                          capture_output=True, text=True, timeout=20, check=False)
    return "Vuelta iniciada: te aviso al terminar." if done.returncode == 0 else "No pude iniciar la vuelta (¿está programado el bot?)."


def handle(text: str, state: State, listed: list[str]) -> tuple[str, list[str]]:
    """La respuesta a un mensaje del dueño y la lista de preguntas mostrada (para /responder N)."""
    text = (text or "").strip()
    command, _, rest = text.partition(" ")
    command = command.split("@")[0].lower()
    if command in ("/start", "/ayuda", "/help"):
        return HELP, listed
    if command == "/estado":
        return _status_text(state), listed
    if command == "/manuales":
        items = manual_items()
        if not items:
            return "No tienes postulaciones manuales pendientes.", listed
        rows = [f"{n}. {i.get('titulo', '')} — {i.get('empresa', '')}\n   {i.get('url', '')}" for n, i in enumerate(items, 1)]
        return "Pendientes de enviar tú (marca con /hecha N):\n" + "\n".join(rows), listed
    if command == "/hecha":
        items = manual_items()
        if not rest.strip().isdigit() or not 1 <= int(rest) <= len(items):
            return "Escribe /hecha N (N es el número de /manuales).", listed
        item = items[int(rest) - 1]
        done = _read_json(MANUAL_DONE, [])
        done.append(item["id"])
        _write_private(MANUAL_DONE, json.dumps(done))
        return f"¡Bien! Marqué como enviada: {item.get('titulo', '')} — {item.get('empresa', '')}.", listed
    if command == "/hoy":
        return _today_sent(state), listed
    if command == "/vuelta":
        return _start_round(), listed
    if command == "/pausar":
        hours = int(rest) if rest.strip().isdigit() else 24
        hours = max(1, min(hours, 24 * 14))
        until = datetime.now(UTC) + timedelta(hours=hours)
        _write_private(CONTROL_FILE, json.dumps({"pausa_hasta": until.isoformat(timespec="seconds")}))
        return f"Listo: no corro vueltas hasta {until.astimezone():%d/%m %H:%M}. /reanudar para quitarlo.", listed
    if command == "/reanudar":
        CONTROL_FILE.unlink(missing_ok=True)
        return "Listo: las vueltas siguen a sus horas.", listed
    if command == "/preguntas":
        listed = pending_questions(state)
        if not listed:
            return "No hay preguntas pendientes.", listed
        rows = [f"{n}. {q}" for n, q in enumerate(listed, 1)]
        return "Sin respuesta (contesta con /responder N texto):\n" + "\n".join(rows[:30]), listed
    if command == "/responder":
        number, _, answer = rest.strip().partition(" ")
        if not number.isdigit() or not answer.strip():
            return "Escribe /responder N texto (N es el número de /preguntas).", listed
        if not listed:
            listed = pending_questions(state)
        index = int(number) - 1
        if not 0 <= index < len(listed):
            return "Ese número no está en la lista: pide /preguntas otra vez.", listed
        question = listed[index]
        answers = extra_answers()
        answers[normalize(question)] = answer.strip()[:500]
        _write_private(EXTRA_ANSWERS, json.dumps(answers, ensure_ascii=False, indent=1))
        return f"Guardado: «{question}» → «{answer.strip()[:120]}». Las vacantes con esa pregunta se reintentan en la próxima vuelta.", listed
    return "No entendí. " + HELP, listed


def serve(client: Client, chat: int, *, once: bool = False) -> None:
    """Escucha mensajes del dueño (long polling) y responde. `once`: una sola ronda (pruebas)."""
    offset, listed = 0, []
    while True:
        try:
            updates = client.updates(offset)
        except TelegramError as e:
            print(e)
            if once:
                return
            time.sleep(30)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message") or {}
            if int(message.get("chat", {}).get("id", 0)) != chat or not message.get("text"):
                continue  # solo el chat emparejado
            state = State(cfg.DATA_DIR / "estado.json")
            reply, listed = handle(message["text"], state, listed)
            try:
                client.send(chat, reply)
            except TelegramError as e:
                print(e)
        if once:
            return
