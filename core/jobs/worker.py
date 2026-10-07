"""Proceso que ejecuta la cola. Corre dentro de la API (hilo) o aparte: `python -m core.jobs.worker`."""

import logging
import os
import threading

from core.errors import describe
from core.jobs import service
from core.jobs.handlers import HANDLERS, PRIVATE_PAYLOAD

logger = logging.getLogger(__name__)


def run_once() -> bool:
    """Ejecuta un trabajo pendiente. False si la cola estaba vacía."""
    job = service.claim()
    if job is None:
        return False
    last: dict = {}

    def report(result: dict) -> None:
        last.clear()
        last.update(result)
        service.progress(job, result)

    try:
        handler = HANDLERS.get(job.kind)
        if handler is None:
            raise RuntimeError(f"Tipo de trabajo desconocido: {job.kind}")
        service.finish(job, handler(job, report), clear_payload=job.kind in PRIVATE_PAYLOAD)
    except Exception as e:  # el trabajo falla con un mensaje para la persona; el proceso sigue
        known = describe(e)
        if known is None:
            logger.exception("Falló el trabajo %s (%s)", job.id, job.kind)
        service.fail(job, known[1] if known else "Error inesperado. Intenta de nuevo.", last or None,
                     clear_payload=job.kind in PRIVATE_PAYLOAD)
    return True


def run_forever(stop: threading.Event, idle_seconds: float) -> None:
    """Vacía la cola y espera. En la API, `enqueue` lo despierta al instante; en reposo solo revisa la
    base cada `idle_seconds` (para no impedir que Neon se duerma: consultarla cada segundo la mantiene
    encendida, gasta el cómputo gratuito y afecta también a la app de Streamlit)."""
    while not stop.is_set():
        try:
            busy = run_once()
        except Exception:  # p. ej. la base no responde: se reintenta sin tumbar el proceso
            logger.exception("Error leyendo la cola de trabajos")
            busy = False
        if not busy:
            _purge()
            service.new_job.wait(idle_seconds)
            service.new_job.clear()


def _purge() -> None:
    try:
        service.purge()
    except Exception:
        logger.exception("No se pudieron borrar los trabajos viejos")


def start_thread(idle_seconds: float = 3600) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    thread = threading.Thread(target=run_forever, args=(stop, idle_seconds), name="cola-de-trabajos", daemon=True)
    thread.start()
    return thread, stop


def stop_thread(thread: threading.Thread, stop: threading.Event) -> None:
    stop.set()
    service.new_job.set()  # que no siga esperando
    thread.join(timeout=10)


if __name__ == "__main__":
    import config  # noqa: F401  (carga .env)
    from core.profile import service as profiles

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    profiles.ensure_ready()
    # Proceso aparte: nadie lo despierta al encolar, así que revisa la cola cada pocos segundos.
    run_forever(threading.Event(), idle_seconds=float(os.environ.get("JOBS_POLL_SECONDS", "5")))
