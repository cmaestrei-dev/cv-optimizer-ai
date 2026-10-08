"""Buzón de la app por IMAP (Gmail con contraseña de aplicación). Lee y manda a la papelera: no guarda correos."""

import imaplib
import re
from collections.abc import Iterator
from contextlib import contextmanager, suppress

TIMEOUT = 20


class MailboxError(RuntimeError):
    pass


class ImapMailbox:
    def __init__(self, conn: imaplib.IMAP4_SSL) -> None:
        self._conn = conn
        self._trash = self._find_trash()

    def _find_trash(self) -> str:
        """La papelera por su atributo \\Trash (RFC 6154): su nombre cambia con el idioma de la cuenta."""
        status, folders = self._conn.list()
        if status != "OK":
            return ""
        for line in folders or []:
            text = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
            if "\\Trash" in text and (match := re.search(r'"([^"]+)"\s*$', text)):
                return match.group(1)
        return ""

    def fetch(self, limit: int) -> Iterator[tuple[bytes, bytes]]:
        """(uid, correo) de los más antiguos primero."""
        try:
            status, data = self._conn.uid("SEARCH", None, "ALL")
            if status != "OK":
                raise MailboxError("No se pudo listar el buzón")
            for uid in (data[0] or b"").split()[:limit]:
                status, parts = self._conn.uid("FETCH", uid, "(RFC822)")
                raw = next((p[1] for p in parts or [] if isinstance(p, tuple) and len(p) == 2), None)
                if status == "OK" and raw:
                    yield uid, raw
        except (OSError, imaplib.IMAP4.error) as e:
            raise MailboxError("Se cortó la conexión con el buzón") from e

    def _ok(self, response: tuple, what: str) -> None:
        if response[0] != "OK":  # imaplib solo lanza con BAD; un NO llega como respuesta
            raise MailboxError(f"El buzón rechazó: {what}")

    def discard(self, uid: bytes) -> None:
        try:
            if self._trash:  # en Gmail, borrar de la bandeja de entrada solo archiva: se mueve a la papelera
                self._ok(self._conn.uid("MOVE", uid, f'"{self._trash}"'), "mover a la papelera")
            else:
                self._ok(self._conn.uid("STORE", uid, "+FLAGS", r"(\Deleted)"), "marcar como borrado")
                self._ok(self._conn.expunge(), "borrar")
        except (OSError, imaplib.IMAP4.error) as e:
            raise MailboxError("No se pudo borrar un correo del buzón") from e

    def empty_trash(self) -> None:
        """Borra del todo lo que hay en la papelera (el buzón es solo de la app: ahí solo hay correos ya
        leídos). Sin esto, Gmail los guardaría 30 días, con sus enlaces de inicio de sesión."""
        if not self._trash:
            return
        try:
            self._ok(self._conn.select(f'"{self._trash}"'), "abrir la papelera")
            status, data = self._conn.uid("SEARCH", None, "ALL")
            if status == "OK" and (uids := (data[0] or b"").split()):
                self._ok(self._conn.uid("STORE", b",".join(uids), "+FLAGS", r"(\Deleted)"), "vaciar la papelera")
                self._ok(self._conn.expunge(), "vaciar la papelera")
        except (OSError, imaplib.IMAP4.error) as e:
            raise MailboxError("No se pudo vaciar la papelera del buzón") from e
        finally:
            with suppress(OSError, imaplib.IMAP4.error):
                self._conn.select("INBOX")


@contextmanager
def open_mailbox(address: str, password: str, host: str = "imap.gmail.com") -> Iterator[ImapMailbox]:
    try:
        conn = imaplib.IMAP4_SSL(host, 993, timeout=TIMEOUT)
        conn.login(address, password)
        conn.select("INBOX")
    except (OSError, imaplib.IMAP4.error) as e:
        raise MailboxError("No se pudo abrir el buzón de alertas") from e
    try:
        yield ImapMailbox(conn)
    finally:
        with suppress(OSError, imaplib.IMAP4.error):
            conn.logout()
