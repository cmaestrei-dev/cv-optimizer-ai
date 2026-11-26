"""Postular por correo (autorizado por el dueño el 2026-11-26): cuando una vacante dice «envía tu hoja de vida a…», el
bot manda desde el Gmail de la persona un correo con el CV a la medida y el mensaje que escribe la app (verificado
contra el perfil).

Usa una contraseña de aplicación de Google. La persona la crea en su cuenta y la escribe ella misma con
`python -m runner correo`; se guarda solo en ~/.config/cv-optimizer-bot/correo (0600) y nunca va a la app ni a los
registros. Sin ella, esas vacantes siguen llegando por Telegram para enviarlas a mano."""

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from runner import config as cfg

SECRET_FILE = cfg.CONFIG_DIR / "correo"
HOST, PORT = "smtp.gmail.com", 465
_SUBJECT = re.compile(r"asunto\s*[:\-–—]?\s*[«\"“']?([^\n«»\"“”']{3,90})", re.I)
_NOREPLY = re.compile(r"(no-?reply|no-?responder|mailer-daemon|notifica)", re.I)


class MailError(RuntimeError):
    pass


def password() -> str:
    try:
        return SECRET_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_password(secret: str) -> None:
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(secret.strip() + "\n")
    os.chmod(SECRET_FILE, 0o600)


def requested_subject(text: str) -> str:
    """El asunto que pide la vacante («con el asunto: Desarrollador Junior»), o «» si no pide uno."""
    match = _SUBJECT.search(text or "")
    return match.group(1).strip().rstrip(".,;:)") if match else ""


def recipients(emails: list[str]) -> list[str]:
    """Las direcciones a las que tiene sentido escribir (sin las de «no responder»)."""
    return [e for e in emails if not _NOREPLY.search(e.split("@")[0])]


def build(*, sender: str, name: str, to: str, subject: str, body: str, attachment: Path | None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((name, sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = sender
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg.set_content(body)
    if attachment is not None:
        msg.add_attachment(attachment.read_bytes(), maintype="application", subtype="pdf", filename=attachment.name)
    return msg


def send(sender: str, secret: str, msg: EmailMessage, *, timeout: int = 30) -> None:
    try:
        with smtplib.SMTP_SSL(HOST, PORT, context=ssl.create_default_context(), timeout=timeout) as smtp:
            smtp.login(sender, secret)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise MailError("Gmail rechazó la contraseña de aplicación: vuelve a crearla y corre python -m runner correo") from None
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"no se pudo enviar el correo ({type(e).__name__})") from None


def check_login(sender: str, secret: str, *, timeout: int = 30) -> None:
    try:
        with smtplib.SMTP_SSL(HOST, PORT, context=ssl.create_default_context(), timeout=timeout) as smtp:
            smtp.login(sender, secret)
    except smtplib.SMTPAuthenticationError:
        raise MailError("Gmail no aceptó esa contraseña de aplicación (no es la de tu cuenta: créala en "
                        "myaccount.google.com/apppasswords)") from None
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"no se pudo conectar con Gmail ({type(e).__name__})") from None
