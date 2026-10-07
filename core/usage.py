"""Límite diario de llamadas a la IA por cuenta (el costo del SaaS crece con cada llamada).

`metered(llm, username)` envuelve el cliente: antes de cada llamada verifica el cupo y, si la llamada
sale bien, la cuenta. Los errores del proveedor no se cobran. Es un límite suave: una operación en
curso puede pasarse por una llamada.
"""

import os
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base, session_scope
from core.profile.models import User
from core.profile.repository import NotFoundError

DEFAULT_DAILY_CALLS = 200


class QuotaExceededError(RuntimeError):
    pass


class AIUsage(Base):
    __tablename__ = "ai_usage"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)


def daily_limit() -> int:
    try:
        return int(os.environ.get("AI_DAILY_CALLS", DEFAULT_DAILY_CALLS))
    except ValueError:
        return DEFAULT_DAILY_CALLS


def _today() -> date:
    from core.tracking.service import today  # hora de Colombia, como el resto del seguimiento

    return today()


def _user_id(session, username: str) -> int:
    user_id = session.scalar(select(User.id).where(User.username == username))
    if user_id is None:
        raise NotFoundError(f"Usuario {username}")
    return user_id


def used_today(username: str) -> int:
    with session_scope() as s:
        row = s.get(AIUsage, (_user_id(s, username), _today()))
        return row.calls if row else 0


def check(username: str) -> None:
    if used_today(username) >= daily_limit():
        raise QuotaExceededError("Llegaste al límite diario de uso de la IA. Se reinicia mañana (hora de Colombia).")


def add(username: str, calls: int = 1) -> None:
    for _ in range(2):  # la primera llamada del día puede chocar con otra simultánea
        try:
            with session_scope() as s:
                key = (_user_id(s, username), _today())
                row = s.get(AIUsage, key, with_for_update=True)
                if row is None:
                    s.add(AIUsage(user_id=key[0], day=key[1], calls=calls))
                else:
                    row.calls += calls
            return
        except IntegrityError:
            continue


class MeteredLLM:
    """Mismo contrato que LLMClient; cuenta cada llamada exitosa contra el cupo de la cuenta."""

    def __init__(self, llm, username: str):
        self._llm = llm
        self._username = username

    def complete(self, *args, **kwargs):
        check(self._username)
        result = self._llm.complete(*args, **kwargs)
        add(self._username)
        return result

    def __getattr__(self, name):
        return getattr(self._llm, name)


def metered(llm, username: str) -> MeteredLLM:
    return MeteredLLM(llm, username)
