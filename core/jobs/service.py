"""Operaciones de la cola. Cada función abre y confirma su propia transacción."""

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update

from core.db import session_scope
from core.errors import UserInputError
from core.jobs.models import Job
from core.profile.models import User
from core.profile.repository import NotFoundError

STALE_AFTER = timedelta(minutes=10)  # un trabajo "corriendo" sin latido en este tiempo se dio por perdido
MAX_ATTEMPTS = 3
MAX_ACTIVE_PER_ACCOUNT = 3  # una cuenta no puede llenar la cola y hacer esperar a las demás

new_job = threading.Event()  # despierta al trabajador del mismo proceso (sin sondear la base)


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    username: str
    kind: str
    payload: dict
    attempt: int  # las escrituras de un intento viejo (que se dio por perdido) se ignoran


def _now() -> datetime:
    return datetime.now(UTC)


def _user_id(session, username: str) -> int:
    user_id = session.scalar(select(User.id).where(User.username == username))
    if user_id is None:
        raise NotFoundError(f"Usuario {username}")
    return user_id


def enqueue(username: str, kind: str, payload: dict) -> int:
    with session_scope() as s:
        user_id = _user_id(s, username)
        active = s.scalar(select(func.count(Job.id)).where(Job.user_id == user_id, Job.status.in_(("queued", "running"))))
        if active >= MAX_ACTIVE_PER_ACCOUNT:
            raise UserInputError("Ya tienes trabajos en curso. Espera a que terminen y vuelve a intentarlo.")
        job = Job(user_id=user_id, kind=kind, payload=json.dumps(payload, ensure_ascii=False))
        s.add(job)
        s.flush()
        job_id = job.id
    new_job.set()
    return job_id


def get(username: str, job_id: int) -> Job:
    with session_scope() as s:
        job = s.scalar(select(Job).where(Job.id == job_id, Job.user_id == _user_id(s, username)))
        if job is None:
            raise NotFoundError(f"Trabajo {job_id}")
        return job


def claim() -> ClaimedJob | None:
    """Toma el trabajo pendiente más antiguo (o uno que quedó colgado) y lo marca como corriendo."""
    now = _now()
    with session_scope() as s:
        s.execute(  # colgados que ya agotaron sus intentos: fallidos, para que no bloqueen la cola
            update(Job)
            .where(Job.status == "running", Job.started_at < now - STALE_AFTER, Job.attempts >= MAX_ATTEMPTS)
            .values(status="failed", error="El trabajo se interrumpió varias veces", finished_at=now)
        )
        job = s.scalar(
            select(Job)
            .where(or_(Job.status == "queued",
                       and_(Job.status == "running", Job.started_at < now - STALE_AFTER)))
            .order_by(Job.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status, job.started_at, job.attempts = "running", now, job.attempts + 1
        username = s.scalar(select(User.username).where(User.id == job.user_id))
        return ClaimedJob(job.id, username, job.kind, json.loads(job.payload or "{}"), job.attempts)


def _set(job: ClaimedJob, **values) -> None:
    with session_scope() as s:
        s.execute(update(Job).where(Job.id == job.id, Job.status == "running", Job.attempts == job.attempt)
                  .values(**values))


def progress(job: ClaimedJob, result: dict) -> None:
    """Guarda el avance y renueva el latido: un trabajo largo que avanza no se da por perdido."""
    _set(job, result=json.dumps(result, ensure_ascii=False), started_at=_now())


def finish(job: ClaimedJob, result: dict) -> None:
    _set(job, status="done", result=json.dumps(result, ensure_ascii=False), finished_at=_now())


def fail(job: ClaimedJob, message: str, result: dict | None = None) -> None:
    values = {"status": "failed", "error": message, "finished_at": _now()}
    if result is not None:
        values["result"] = json.dumps(result, ensure_ascii=False)
    _set(job, **values)
