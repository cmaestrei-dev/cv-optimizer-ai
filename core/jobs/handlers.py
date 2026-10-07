"""Lo que hace cada tipo de trabajo. La IA siempre va medida contra el cupo de la cuenta."""

from collections.abc import Callable
from dataclasses import asdict

from core import applying, discovery
from core import llm as llm_module
from core.jobs.service import ClaimedJob
from core.profile import service as profiles
from core.usage import metered


def _llm(task: str, username: str):
    return metered(llm_module.get_llm(task), username)


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


HANDLERS: dict[str, Callable[[ClaimedJob, Callable[[dict], None]], dict]] = {
    "cv": generate_cv,
    "bandeja": triage,
}
