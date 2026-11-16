"""Tokens del bot: la persona los crea desde la web (con su sesión) y el programa de su computador los usa.

- El texto completo se muestra una sola vez; en la base solo queda su SHA-256 (un volcado de la base no
  sirve para entrar). Los tokens son aleatorios de 256 bits: no hace falta una derivación lenta.
- Se pueden revocar en cualquier momento; uno revocado deja de funcionar en la siguiente petición.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from core.bot.models import BotToken
from core.db import session_scope
from core.profile.models import User
from core.profile.repository import NotFoundError

PREFIX = "cvb_"
MAX_ACTIVE = 5
_TOUCH_EVERY = timedelta(minutes=5)  # «último uso» sin escribir en la base en cada petición


class TokenLimitError(ValueError):
    """Ya hay demasiados tokens activos: se revoca uno antes de crear otro."""


@dataclass(frozen=True)
class TokenInfo:
    id: int
    label: str
    hint: str
    created_at: datetime
    last_used_at: datetime | None


def _hash(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def looks_like_token(value: str) -> bool:
    return value.startswith(PREFIX)


def _user_id(session, username: str) -> int:
    user_id = session.scalar(select(User.id).where(User.username == username))
    if user_id is None:
        raise NotFoundError("La cuenta no existe")
    return user_id


def _info(token: BotToken) -> TokenInfo:
    return TokenInfo(token.id, token.label, token.hint, token.created_at, token.last_used_at)


def create(username: str, label: str = "") -> tuple[TokenInfo, str]:
    """Crea un token y devuelve (datos, texto completo). El texto no se puede volver a consultar."""
    plain = PREFIX + secrets.token_urlsafe(32)
    with session_scope() as s:
        user_id = _user_id(s, username)
        active = s.scalar(select(func.count()).select_from(BotToken).where(
            BotToken.user_id == user_id, BotToken.revoked_at.is_(None)))
        if active >= MAX_ACTIVE:
            raise TokenLimitError(f"Ya tienes {MAX_ACTIVE} tokens activos: revoca uno antes de crear otro.")
        token = BotToken(user_id=user_id, label=label.strip()[:60] or "Mi computador", token_hash=_hash(plain), hint=plain[-4:])
        s.add(token)
        s.flush()
        s.refresh(token)
        return _info(token), plain


def list_active(username: str) -> list[TokenInfo]:
    with session_scope() as s:
        user_id = _user_id(s, username)
        rows = s.scalars(select(BotToken).where(BotToken.user_id == user_id, BotToken.revoked_at.is_(None))
                         .order_by(BotToken.created_at.desc(), BotToken.id.desc()))
        return [_info(t) for t in rows]


def revoke(username: str, token_id: int) -> None:
    with session_scope() as s:
        token = s.scalar(select(BotToken).where(BotToken.id == token_id, BotToken.user_id == _user_id(s, username),
                                                BotToken.revoked_at.is_(None)))
        if token is None:
            raise NotFoundError("Ese token no existe")
        token.revoked_at = datetime.now(UTC)


def resolve(plain: str) -> str | None:
    """Usuario dueño de un token vigente, o None. Actualiza el último uso como mucho cada 5 minutos."""
    if not looks_like_token(plain) or len(plain) > 100:
        return None
    with session_scope() as s:
        row = s.execute(select(BotToken, User.username).join(User, User.id == BotToken.user_id).where(
            BotToken.token_hash == _hash(plain), BotToken.revoked_at.is_(None))).first()
        if row is None:
            return None
        token, username = row
        now = datetime.now(UTC)
        last = token.last_used_at
        if last is not None and last.tzinfo is None:  # SQLite devuelve fechas sin zona (son UTC)
            last = last.replace(tzinfo=UTC)
        if last is None or now - last > _TOUCH_EVERY:
            token.last_used_at = now
        return username
