"""Límite diario de llamadas a la IA por cuenta (el costo del SaaS crece con cada llamada).

`metered(llm, username)` envuelve el cliente: antes de cada llamada verifica el cupo y, si la llamada
sale bien, la cuenta. Los errores del proveedor no se cobran. Es un límite suave: una operación en
curso puede pasarse por una llamada.
"""

import os
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base, session_scope
from core.profile.models import User
from core.profile.repository import NotFoundError

DEFAULT_DAILY_CALLS = 200
DEFAULT_GLOBAL_DAILY_CALLS = 1000  # tope de todo el servicio: registrarse es gratis, la IA no


class QuotaExceededError(RuntimeError):
    pass


class AIUsage(Base):
    __tablename__ = "ai_usage"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def daily_limit() -> int:
    return _int_env("AI_DAILY_CALLS", DEFAULT_DAILY_CALLS)


def global_daily_limit() -> int:
    return _int_env("AI_GLOBAL_DAILY_CALLS", DEFAULT_GLOBAL_DAILY_CALLS)


def used_today_by_everyone() -> int:
    with session_scope() as s:
        return s.scalar(select(func.coalesce(func.sum(AIUsage.calls), 0)).where(AIUsage.day == _today())) or 0


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
    if used_today_by_everyone() >= global_daily_limit():
        raise QuotaExceededError("El servicio llegó a su límite diario de uso de la IA. Vuelve a intentarlo mañana.")


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
    """Mismo contrato que LLMClient; cuenta cada llamada exitosa contra el cupo de la cuenta.

    Acepta el cliente o una función que lo crea: así el cliente (y su configuración) solo se exige
    cuando de verdad se llama, después de validar lo que mandó la persona.
    """

    def __init__(self, llm, username: str):
        self._llm = llm
        self._username = username

    def _client(self):
        if callable(self._llm) and not hasattr(self._llm, "complete"):
            self._llm = self._llm()
        return self._llm

    def complete(self, *args, **kwargs):
        check(self._username)
        result = self._client().complete(*args, **kwargs)
        add(self._username)
        return result

    def __getattr__(self, name):
        return getattr(self._client(), name)


def metered(llm, username: str) -> MeteredLLM:
    return MeteredLLM(llm, username)
