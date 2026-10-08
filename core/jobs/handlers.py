"""Lo que hace cada tipo de trabajo. La IA siempre va medida contra el cupo de la cuenta."""

from collections.abc import Callable
from dataclasses import asdict

from core import applying, discovery, onboarding
from core import llm as llm_module
from core.jobs.service import ClaimedJob
from core.profile import service as profiles
from core.usage import QuotaExceededError, metered


def _llm(task: str, username: str):
    return metered(lambda: llm_module.get_llm(task), username)


def generate_cv(job: ClaimedJob, report: Callable[[dict], None]) -> dict:
    return applying.generate_cv(
        job.username, int(job.payload["application_id"]), focus=str(job.payload.get("focus", "")),
        write_llm=_llm("write", job.username), extract_llm=_llm("extract", job.username),
    )


def triage(job: ClaimedJob, report: Callable[[dict], None]) -> dict:
    """Bandeja por lotes: reporta el avance tras cada enlace (la persona ve cómo se llena)."""
    urls = [str(u) for u in job.payload["urls"]][: discovery.MAX_BATCH]
    results: list[dict] = []
    state = {"total": len(urls), "done": 0, "results": results}
    snapshot = profiles.snapshot(job.username)
    for result in discovery.triage(job.username, urls, _llm("extract", job.username), snapshot):
        results.append(asdict(result))
        state["done"] = len(results)
        report(state)
    return state


def triage_alerts(job: ClaimedJob, report: Callable[[dict], None]) -> dict:
    """Vacantes de las alertas por correo. Si se acaba el cupo de IA, las que faltan vuelven a la espera
    de la cuenta (se analizan otro día) en vez de perderse."""
    from core.alerts import service as alerts

    progress: dict = {}

    def keep(state: dict) -> None:
        progress.update(state)
        report(state)

    try:
        return triage(job, keep)
    except QuotaExceededError:
        rest = [str(u) for u in job.payload["urls"]][progress.get("done", 0):]
        alerts.defer(job.username, rest)
        return {**progress, "deferred": len(rest)}


def read_cv(job: ClaimedJob, report: Callable[[dict], None]) -> dict:
    return onboarding.read_import(job.username, str(job.payload["pdf_text"]), _llm("extract", job.username))


HANDLERS: dict[str, Callable[[ClaimedJob, Callable[[dict], None]], dict]] = {
    "cv": generate_cv,
    "bandeja": triage,
    "alerta": triage_alerts,
    "importar": read_cv,
}
# Su entrada tiene datos personales que no se necesitan después (el texto del CV): se borra al terminar.
PRIVATE_PAYLOAD = {"importar"}
