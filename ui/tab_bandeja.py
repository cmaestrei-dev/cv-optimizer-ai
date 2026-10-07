"""Bandeja de vacantes (fase 4): buscar en los portales, traer varias por enlace, ordenarlas por
compatibilidad y decidir cuáles preparar. Nada se envía solo: la persona postula en el portal."""

import json
import logging
import uuid
import zlib
from dataclasses import asdict

import streamlit as st
from pydantic import ValidationError

from core import discovery
from core.engine import pipeline
from core.llm import LLMConfigError, get_llm
from core.llm.client import LLMAuthError
from core.profile import service
from core.tracking import service as tracking
from core.tracking.models import TRIAGE_STATUSES, Application
from core.vacancy import VacancyAnalysis
from models import UserProfile
from ui.tab_cv_inteligente import run_engine
from ui.text import md

logger = logging.getLogger(__name__)
_RESULT_ICON = {"agregada": ":material/add_circle:", "repetida": ":material/content_copy:", "error": ":material/error:"}


def inbox_count(profile: UserProfile | None) -> int:
    if profile is None:
        return 0
    try:
        return tracking.count(profile.username, TRIAGE_STATUSES)
    except Exception:  # la etiqueta de la pestaña nunca debe tumbar la app
        return 0


def _vacancy(a: Application) -> VacancyAnalysis | None:
    try:
        return VacancyAnalysis.model_validate_json(a.analysis_json) if a.analysis_json else None
    except ValidationError:
        return None


# ── 1. buscar en los portales ─────────────────────────────────────────


def _render_search(profile: UserProfile, overrides: dict[str, str], expanded: bool) -> None:
    with st.expander(":material/travel_explore: 1. Buscar vacantes en los portales", expanded=expanded):
        st.caption(
            "Elige un cargo y abre la búsqueda en cada portal (se abre en tu navegador, con tu sesión). "
            "Copia el enlace de cada vacante que te interese y pégalo en el paso 2."
        )
        snap = service.snapshot(profile.username)
        suggested = st.session_state.get("bandeja_titles")
        if suggested and suggested["username"] == profile.username:
            titles = suggested["titles"]
        else:
            titles = list(dict.fromkeys(e.role for e in snap.experiences if e.role.strip()))

        col_city, col_ai = st.columns([3, 2], vertical_alignment="bottom")
        city = col_city.text_input("Ciudad (opcional)", key="bandeja_city", placeholder="Ej.: Bogotá")
        if col_ai.button(":material/auto_awesome: Sugerir cargos afines", key="bandeja_suggest",
                         width="stretch", disabled=not snap.experiences):
            result = run_engine(
                lambda: discovery.suggest_titles(get_llm("extract", overrides), snap), "Buscando cargos afines a tu perfil..."
            )
            if result:
                st.session_state["bandeja_titles"] = {"username": profile.username, "titles": result}
                st.rerun()

        title = None
        if titles:
            title = st.pills("Cargo", titles, default=titles[0], key=f"bandeja_title_{zlib.crc32('|'.join(titles).encode())}")
        custom = st.text_input("U otro cargo", key="bandeja_custom", placeholder="Ej.: Analista de compras")
        query = custom.strip() or title
        if not query:
            st.info("Escribe un cargo o registra tu experiencia para sugerirte cargos.")
            return
        for col, (name, url) in zip(st.columns(4), discovery.search_links(query, city), strict=False):
            col.link_button(f":material/open_in_new: {name}", url, width="stretch")
        if city.strip():
            st.caption("Magneto busca en todo el país: su enlace de búsqueda no admite ciudad.")


# ── 2. traer varias vacantes por enlace ───────────────────────────────


def _render_batch(profile: UserProfile, overrides: dict[str, str]) -> None:
    st.markdown("##### :material/playlist_add: 2. Pega los enlaces que te interesaron")
    with st.form("bandeja_batch"):
        text = st.text_area(
            f"Enlaces de vacantes (hasta {discovery.MAX_BATCH} a la vez, uno por línea)", key="bandeja_links",
            height=120, placeholder="https://co.computrabajo.com/ofertas-de-trabajo/...\nhttps://www.linkedin.com/jobs/view/...",
        )
        go = st.form_submit_button(":material/bolt: Traer y analizar", type="primary")
    if go:
        _process(text, profile, overrides)

    last = st.session_state.get("bandeja_results")
    if last and last["username"] == profile.username:
        added = sum(r["status"] == "agregada" for r in last["results"])
        with st.expander(f":material/fact_check: Última carga: {added} nueva(s) de {len(last['results'])}", expanded=True):
            if last.get("error"):
                st.error(f":material/error: {last['error']}")
            if last.get("skipped"):
                st.info(f"Se procesan {discovery.MAX_BATCH} enlaces por carga: pega los otros {len(last['skipped'])} en una nueva.")
            for r in last["results"]:
                score = f" · {r['score']}/100" if r["score"] is not None else ""
                st.markdown(f"{_RESULT_ICON[r['status']]} {md(r['message'])}{score}")
                st.caption(md(r["url"]))
            if any(r["status"] == "error" for r in last["results"]):
                st.caption(
                    "Las que fallaron suelen pedir iniciar sesión. Ábrelas, copia el texto y analízalas en «CV inteligente»."
                )


def _process(text: str, profile: UserProfile, overrides: dict[str, str]) -> None:
    urls = discovery.parse_links(text)
    if not urls:
        st.warning("No encontramos enlaces. Deben empezar por https:// o http://")
        return
    skipped = urls[discovery.MAX_BATCH:]
    urls = urls[:discovery.MAX_BATCH]
    snap = service.snapshot(profile.username)
    if not snap.experiences:
        st.warning("Registra primero tu experiencia (pestaña «Mi experiencia»): sin ella no hay con qué comparar.")
        return
    try:
        llm = get_llm("extract", overrides)
    except LLMConfigError as e:
        st.error(f":material/key: {e}")
        return

    results, error = [], ""
    bar = st.progress(0.0, text=f"Leyendo 1 de {len(urls)}...")
    try:
        for i, result in enumerate(discovery.triage(profile.username, urls, llm, snap), start=1):
            results.append(asdict(result))
            bar.progress(i / len(urls), text=f"{i} de {len(urls)} listas")
    except (LLMAuthError, LLMConfigError) as e:
        error = str(e)
    except Exception:
        logger.exception("La carga de la bandeja se interrumpió")
        error = "La carga se interrumpió por un error inesperado. Las vacantes ya agregadas quedaron en la bandeja."
    st.session_state["bandeja_results"] = {
        "username": profile.username, "results": results, "error": error, "skipped": skipped,
    }
    st.rerun()


# ── 3. revisar: preparar o descartar ──────────────────────────────────


def _render_inbox(profile: UserProfile, overrides: dict[str, str]) -> None:
    items = sorted(
        tracking.list_applications(profile.username, TRIAGE_STATUSES, with_files=False),
        key=lambda a: (a.match_score if a.match_score is not None else -1, a.id), reverse=True,
    )
    st.markdown(f"##### :material/inbox: 3. Por revisar ({len(items)})")
    if not items:
        st.info("Tu bandeja está vacía. Busca en los portales (paso 1) y pega aquí los enlaces (paso 2).")
        return
    st.caption(
        "Ordenadas por compatibilidad con tu perfil. «Preparar» la lleva a «CV inteligente» con todo listo para "
        "generar el CV; «Descartar» la saca de aquí."
    )
    for a in items:
        _render_item(a, profile, overrides)


def _render_item(a: Application, profile: UserProfile, overrides: dict[str, str]) -> None:
    vacancy = _vacancy(a)
    try:
        summary = json.loads(a.match_json or "{}")
    except json.JSONDecodeError:
        summary = {}
    with st.container(border=True):
        col_info, col_score = st.columns([3, 1], vertical_alignment="center")
        details = [a.company, vacancy.location if vacancy else "", vacancy.modality if vacancy else "", a.platform]
        col_info.markdown(f"**{md(a.role)}**  \n{md(' · '.join(p for p in details if p))}")
        if a.match_score is not None:
            col_score.progress(a.match_score / 100, text=f"Compatibilidad {a.match_score}/100")

        missing, partial = discovery.missing_musts(a.match_json), discovery.missing_musts(a.match_json, "parcial")
        required, years = summary.get("required_years"), summary.get("experience_years")
        if required and years is not None and years < required:
            st.caption(f":material/warning: Pide {required:g} años de experiencia; tienes {years:g}.")
        for icon, label, items in ((":material/cancel:", "Te falta (obligatorio)", missing),
                                   (":material/contrast:", "A medias (obligatorio)", partial)):
            if items:
                more = f" y {len(items) - 3} más" if len(items) > 3 else ""
                st.caption(f"{icon} {label}: " + "; ".join(md(m) for m in items[:3]) + more)
        if summary and not missing and not partial:
            st.caption(":material/check_circle: Cumples los requisitos obligatorios.")

        col_prep, col_open, col_drop = st.columns(3)
        if col_prep.button(":material/edit_document: Preparar postulación", key=f"bandeja_prep_{a.id}",
                           type="primary", width="stretch"):
            _prepare(a, vacancy, profile, overrides)
        if a.url:
            col_open.link_button(":material/open_in_new: Ver la vacante", a.url, width="stretch")
        if col_drop.button(":material/close: Descartar", key=f"bandeja_drop_{a.id}", width="stretch"):
            tracking.change_status(profile.username, a.id, "descartada", "Descartada desde la bandeja")
            st.rerun()


def _prepare(a: Application, vacancy: VacancyAnalysis | None, profile: UserProfile, overrides: dict[str, str]) -> None:
    """Recalcula el match con el perfil de hoy y deja la vacante abierta en «CV inteligente»."""
    if vacancy is None:
        st.warning("Esta vacante no tiene análisis guardado. Copia su texto y analízala en «CV inteligente».")
        return
    snap = service.snapshot(profile.username)
    analysis = run_engine(
        lambda: pipeline.match_only(get_llm("extract", overrides), snap, vacancy), "Comparando con tu perfil actual..."
    )
    if analysis is None:
        return
    source = {"text": a.vacancy_text, "url": a.url, "platform": a.platform}
    st.session_state["ci_analysis"] = {
        "username": profile.username, "analysis": analysis, "snap": snap, "text": a.vacancy_text, "images": (),
        "token": uuid.uuid4().hex, "source": source, "application_id": a.id,
    }
    st.session_state["ci_captured"] = source
    st.session_state["ci_pending_inputs"] = {"ci_text": a.vacancy_text, "ci_url": a.url}
    for key in ("ci_cv", "ci_stale", "ci_screening", "ci_cover"):
        st.session_state.pop(key, None)
    tracking.set_match(profile.username, a.id, analysis.match.score,
                       json.dumps(pipeline.match_summary(analysis.match), ensure_ascii=False))
    tracking.change_status(profile.username, a.id, "guardada", "Elegida en la bandeja para postular")
    st.session_state["ci_flash"] = "Vacante de tu bandeja lista: revisa los requisitos y genera el CV."
    st.session_state["bandeja_flash"] = (
        f"«{md(a.role)}» quedó lista en la pestaña «CV inteligente» (arriba): allí generas el CV, las respuestas "
        "y el mensaje para el reclutador."
    )
    st.rerun()


def _render_discarded(username: str) -> None:
    items = tracking.list_applications(username, ("descartada",), with_files=False)
    if not items:
        return
    with st.expander(f":material/delete_sweep: Descartadas ({len(items)})"):
        for a in items[:30]:
            col_text, col_btn = st.columns([4, 1], vertical_alignment="center")
            score = f" · {a.match_score}/100" if a.match_score is not None else ""
            col_text.caption(f"{md(a.role)} — {md(a.company or 'sin empresa')}{score}")
            if col_btn.button("Recuperar", key=f"bandeja_back_{a.id}"):
                tracking.change_status(username, a.id, "por_revisar", "Recuperada en la bandeja")
                st.rerun()


def render_tab_bandeja(profile: UserProfile | None, overrides: dict[str, str]) -> None:
    st.header(":material/inbox: Bandeja de vacantes")
    if profile is None:
        st.info("Selecciona tu perfil en la barra lateral.")
        return
    st.markdown(
        "Busca en los portales, pega los enlaces que te interesen y te las **ordenamos por compatibilidad** "
        "con tu perfil. Tú decides cuáles preparar; **la postulación la envías tú** en el portal."
    )
    flash = st.session_state.pop("bandeja_flash", None)
    if flash:
        st.success(f":material/check: {flash}")
    pending = inbox_count(profile)
    _render_search(profile, overrides, expanded=pending == 0)
    _render_batch(profile, overrides)
    st.divider()
    _render_inbox(profile, overrides)
    _render_discarded(profile.username)
