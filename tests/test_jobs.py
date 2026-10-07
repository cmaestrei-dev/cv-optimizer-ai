import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from core.db import session_scope
from core.jobs import service as jobs
from core.jobs import worker
from core.jobs.handlers import HANDLERS
from core.jobs.models import Job
from core.profile import service as profiles


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(profiles, "_ready", False)
    profiles.ensure_ready()
    profiles.create_user("ana")


def _age(job_id: int, minutes: int, attempts: int) -> None:
    with session_scope() as s:
        s.execute(update(Job).where(Job.id == job_id).values(
            status="running", attempts=attempts, started_at=datetime.now(UTC) - timedelta(minutes=minutes)))


def test_queue_order_and_crash_recovery(monkeypatch):
    seen = []
    monkeypatch.setitem(HANDLERS, "eco", lambda job, report: (seen.append(job.payload["n"]), {"ok": job.payload["n"]})[1])
    first, second = jobs.enqueue("ana", "eco", {"n": 1}), jobs.enqueue("ana", "eco", {"n": 2})
    assert worker.run_once() and worker.run_once() and not worker.run_once()
    assert seen == [1, 2] and jobs.get("ana", first).status == "done"

    # Un trabajo que quedó "corriendo" (el proceso murió) se reintenta tras el tiempo de espera...
    _age(second, minutes=30, attempts=1)
    assert worker.run_once() and seen == [1, 2, 2] and jobs.get("ana", second).attempts == 2
    # ...pero tras agotar los intentos se da por fallido y deja de bloquear la cola
    _age(second, minutes=30, attempts=jobs.MAX_ATTEMPTS)
    assert not worker.run_once()
    assert jobs.get("ana", second).status == "failed" and "interrumpió" in jobs.get("ana", second).error
    # Uno que lleva poco corriendo no se toca
    third = jobs.enqueue("ana", "eco", {"n": 3})
    _age(third, minutes=1, attempts=1)
    assert not worker.run_once()


def test_unknown_kind_and_handler_errors_fail_the_job_not_the_worker(monkeypatch):
    def boom(job, report):
        report({"done": 1})
        raise ValueError("detalle interno")

    monkeypatch.setitem(HANDLERS, "boom", boom)
    unknown, failing = jobs.enqueue("ana", "nada", {}), jobs.enqueue("ana", "boom", {})
    worker.run_once()
    worker.run_once()
    assert jobs.get("ana", unknown).status == "failed"
    job = jobs.get("ana", failing)
    assert job.status == "failed" and "detalle interno" not in job.error and '"done": 1' in job.result


def test_background_thread_processes_the_queue(monkeypatch):
    monkeypatch.setitem(HANDLERS, "eco", lambda job, report: {"ok": True})
    job_id = jobs.enqueue("ana", "eco", {})
    thread, stop = worker.start_thread()
    try:
        _wait_done(job_id)
        later = jobs.enqueue("ana", "eco", {})  # en reposo, encolar lo despierta (no espera la siguiente revisión)
        _wait_done(later)
    finally:
        worker.stop_thread(thread, stop)
    assert not thread.is_alive()


def _wait_done(job_id: int) -> None:
    deadline = time.time() + 10
    while jobs.get("ana", job_id).status != "done" and time.time() < deadline:
        time.sleep(0.1)
    assert jobs.get("ana", job_id).status == "done"


def test_one_account_cannot_fill_the_queue():
    from core.errors import UserInputError

    for _ in range(jobs.MAX_ACTIVE_PER_ACCOUNT):
        jobs.enqueue("ana", "eco", {})
    with pytest.raises(UserInputError, match="trabajos en curso"):
        jobs.enqueue("ana", "eco", {})
    profiles.create_user("eve")
    jobs.enqueue("eve", "eco", {})  # el tope es por cuenta


def test_heartbeat_and_stale_attempts_cannot_overwrite(monkeypatch):
    job_id = jobs.enqueue("ana", "eco", {})
    first = jobs.claim()
    _age(job_id, minutes=30, attempts=1)
    jobs.progress(first, {"done": 1})  # el latido renueva started_at: ya no parece colgado
    assert jobs.claim() is None and jobs.get("ana", job_id).result == '{"done": 1}'

    _age(job_id, minutes=30, attempts=1)  # ahora sí quedó colgado: otro proceso lo retoma (intento 2)
    second = jobs.claim()
    assert second.attempt == 2
    jobs.finish(first, {"de": "intento viejo"})  # el proceso viejo despierta tarde: se ignora
    assert jobs.get("ana", job_id).status == "running"
    jobs.finish(second, {"de": "intento 2"})
    assert jobs.get("ana", job_id).status == "done" and "intento 2" in jobs.get("ana", job_id).result
