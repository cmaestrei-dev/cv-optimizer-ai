"""Completar y mejorar la experiencia de un cargo: cuéntamelo, tareas típicas y entrevista (cifras)."""

import logging

import streamlit as st

from core.llm import LLMConfigError, StructuredOutputError, get_llm
from core.profile import service
from core.profile.completion import (
    Candidate,
    merge_task_details,
    split_into_achievements,
    typical_tasks,
)
from core.profile.interview import (
    generate_questions,
    merge_achievements,
    propose_improvements,
    strength,
)
from core.profile.snapshot import ExperienceSnap
from models import UserProfile
from utils.retry import RetryableError

logger = logging.getLogger(__name__)

MODES = {
    "dump": ":material/edit_note: Cuéntame todo lo que hacías",
    "tasks": ":material/checklist: Tareas típicas de tu cargo",
    "interview": ":material/forum: Entrevista: agrega cifras",
}
_STATES = ("coach_dump", "coach_tasks", "interview")


def call_llm(action, spinner: str):
    """Ejecuta una llamada a la IA mostrando errores comprensibles; None si falla."""
    try:
        with st.spinner(spinner):
            return action()
    except LLMConfigError as e:
        st.error(f":material/key: {e}")
    except RetryableError:
        st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
    except StructuredOutputError:
        st.error(":material/cancel: La IA devolvió una respuesta inválida. Intenta de nuevo.")
    except RuntimeError as e:
        logger.exception("Error de IA al completar el perfil")
        st.error(f":material/cancel: {e}")
    return None


def _state(key: str, profile: UserProfile, exp: ExperienceSnap) -> dict | None:
    state = st.session_state.get(key)
    if state and (state["username"] != profile.username or state["exp_id"] != exp.id):
        st.session_state.pop(key, None)
        return None
    return state


def _clear_widgets(*prefixes: str) -> None:
    for key in [k for k in st.session_state if str(k).startswith(prefixes)]:
        del st.session_state[key]


def render_candidates_review(candidates: list[Candidate], key_prefix: str) -> list[str]:
    """Casillas para aceptar logros; devuelve los marcados. Debe llamarse dentro de un st.form."""
    chosen = []
    for i, c in enumerate(candidates):
        if not c.ok:
            st.markdown(f":material/block: ~~{c.text}~~")
            st.caption(f"Descartado: {'; '.join(c.problems)}")
            continue
        if st.checkbox(c.text, value=c.suggested, key=f"{key_prefix}{i}"):
            chosen.append(c.text)
        if c.duplicate_of:
            st.caption(f"Parecido a lo que ya tienes: «{c.duplicate_of}»")
    return chosen


def _save(profile: UserProfile, exp: ExperienceSnap, texts: list[str], state_key: str) -> None:
    added = service.append_achievements(profile.username, exp.id, texts) if texts else 0
    st.session_state["exp_flash"] = f"Se agregaron {added} logro(s) a {exp.role}." if added else "No se agregó nada."
    st.session_state.pop(state_key, None)
    st.rerun()


def _render_dump(profile: UserProfile, exp: ExperienceSnap, overrides: dict[str, str]) -> None:
    state = _state("coach_dump", profile, exp)
    if state is None:
        with st.form("coach_dump_form"):
            text = st.text_area(
                "Escribe o pega todo lo que hacías en este empleo, como te salga",
                placeholder="Ej.: hacía las facturas de los carros, como 60 al mes; llamaba a los clientes que "
                "debían; llevaba el archivo de las carpetas...",
                height=180,
            )
            go = st.form_submit_button(":material/auto_awesome: Separar en logros", type="primary")
        if go and text.strip():
            candidates = call_llm(
                lambda: split_into_achievements(get_llm("extract", overrides), exp, text), "Ordenando lo que escribiste..."
            )
            if candidates is not None:
                _clear_widgets("coach_dump_c_")
                st.session_state["coach_dump"] = {"username": profile.username, "exp_id": exp.id, "candidates": candidates}
                st.rerun()
        elif go:
            st.warning("Escribe algo primero.")
        return

    if not state["candidates"]:
        st.info("No encontramos tareas en ese texto. Intenta contar qué hacías en un día normal.")
    with st.form("coach_dump_review"):
        st.markdown("**Esto es lo que entendimos.** Desmarca lo que no quieras guardar.")
        chosen = render_candidates_review(state["candidates"], "coach_dump_c_")
        col_save, col_cancel = st.columns(2)
        save = col_save.form_submit_button(":material/save: Agregar a este empleo", type="primary", width="stretch")
        cancel = col_cancel.form_submit_button("Descartar", width="stretch")
    if save:
        _save(profile, exp, chosen, "coach_dump")
    if cancel:
        st.session_state.pop("coach_dump", None)
        st.rerun()


def _render_tasks(profile: UserProfile, exp: ExperienceSnap, overrides: dict[str, str]) -> None:
    state = _state("coach_tasks", profile, exp)
    if state is None:
        st.caption("Te mostramos tareas comunes de tu cargo para ayudarte a recordar. **Marca solo lo que sí hiciste.**")
        if st.button(":material/checklist: Ver tareas típicas", type="primary", key="coach_tasks_start"):
            tasks = call_llm(lambda: typical_tasks(get_llm("extract", overrides), exp), "Buscando tareas típicas de tu cargo...")
            if tasks is not None:
                _clear_widgets("coach_task_")
                st.session_state["coach_tasks"] = {"username": profile.username, "exp_id": exp.id, "tasks": tasks}
                st.rerun()
        return

    if not state["tasks"]:
        st.info("Tu perfil ya cubre las tareas típicas de este cargo.")
    with st.form("coach_tasks_form"):
        st.markdown("**Marca solo lo que realmente hiciste.** Si quieres, agrega un detalle: cifras, programas, frecuencia.")
        picked = []
        for i, task in enumerate(state["tasks"]):
            col_check, col_detail = st.columns([3, 2])
            checked = col_check.checkbox(task, key=f"coach_task_{i}")
            detail = col_detail.text_input("Detalle", key=f"coach_task_d_{i}", label_visibility="collapsed",
                                           placeholder="Detalle (opcional)")
            if checked:
                picked.append((task, detail))
        col_save, col_cancel = st.columns(2)
        save = col_save.form_submit_button(":material/save: Agregar las que marqué", type="primary", width="stretch")
        cancel = col_cancel.form_submit_button("Descartar", width="stretch")
    if cancel:
        st.session_state.pop("coach_tasks", None)
        st.rerun()
    if save:
        if not picked:
            st.warning("No marcaste ninguna tarea.")
            return
        candidates = call_llm(lambda: merge_task_details(get_llm("write", overrides), exp, picked), "Guardando...")
        if candidates is not None:
            rejected = [c for c in candidates if not c.ok]
            if rejected:
                logger.info("Tareas descartadas por verificación: %s", [c.problems for c in rejected])
            _save(profile, exp, [c.text for c in candidates if c.ok and not c.duplicate_of], "coach_tasks")


def _render_interview(profile: UserProfile, exp: ExperienceSnap, overrides: dict[str, str]) -> None:
    state = _state("interview", profile, exp)
    if state is None:
        st.caption("Te hacemos preguntas cortas sobre cifras, herramientas y resultados de este empleo.")
        if st.button(":material/help: Hazme las preguntas", type="primary", key="interview_start"):
            questions = call_llm(lambda: generate_questions(get_llm("extract", overrides), exp), "Preparando preguntas...")
            if questions:
                _clear_widgets("interview_q_", "interview_p_")
                st.session_state["interview"] = {"username": profile.username, "exp_id": exp.id, "exp": exp,
                                                 "questions": questions, "proposals": None}
                st.rerun()
            elif questions is not None:
                st.info("Este empleo ya tiene logros muy completos; no hay preguntas que hacer.")
        return

    questions = state["questions"]
    if state["proposals"] is None:
        with st.form("interview_answers"):
            st.caption("Responde lo que sepas. Si no sabes o no aplica, déjalo vacío.")
            answers = [
                st.text_input(q.question, placeholder=f"Ej.: {q.example}" if q.example else "", key=f"interview_q_{i}")
                for i, q in enumerate(questions)
            ]
            col_go, col_cancel = st.columns(2)
            go = col_go.form_submit_button(":material/auto_fix_high: Proponer mejoras", type="primary", width="stretch")
            cancel = col_cancel.form_submit_button("Cancelar", width="stretch")
        if cancel:
            st.session_state.pop("interview", None)
            st.rerun()
        if go:
            proposals = call_llm(
                lambda: propose_improvements(get_llm("write", overrides), state["exp"], list(zip(questions, answers, strict=True))),
                "Redactando con tus respuestas...",
            )
            if proposals is not None:
                state["proposals"] = proposals
                st.rerun()
        return

    proposals = state["proposals"]
    if not proposals:
        st.info("Con esas respuestas no hay cambios que proponer. Puedes intentarlo con otro empleo.")
    with st.form("interview_review"):
        accepted = []
        for i, p in enumerate(proposals):
            if p.ok:
                if st.checkbox(f"**Después:** {p.proposed}", value=True, key=f"interview_p_{i}"):
                    accepted.append(p)
                st.caption(f"Antes: {p.original or '_(logro nuevo)_'}")
            else:
                st.markdown(f":material/block: ~~{p.proposed}~~")
                st.caption(f"Descartada: {'; '.join(p.problems)}")
        col_save, col_cancel = st.columns(2)
        save = col_save.form_submit_button(":material/save: Guardar mejoras", type="primary", width="stretch")
        discard = col_cancel.form_submit_button("Descartar", width="stretch")
    if save and accepted:
        service.update_experience(profile.username, exp.id, achievements=merge_achievements(state["exp"], accepted))
        st.session_state["exp_flash"] = f"Se mejoraron {len(accepted)} logro(s) de {exp.role}."
    if save or discard:
        st.session_state.pop("interview", None)
        st.rerun()


def render_profile_coach(profile: UserProfile, overrides: dict[str, str]) -> None:
    experiences = list(service.snapshot(profile.username).experiences)
    if not experiences:
        return
    with_metrics = sum(strength(e)[0] for e in experiences)
    total = sum(strength(e)[1] for e in experiences)
    weak = total == 0 or with_metrics / total < 0.5 or any(len(e.achievements) < 3 for e in experiences)
    active = any(st.session_state.get(k) for k in _STATES)

    label = (f":material/trending_up: Completar y mejorar mi experiencia · {total} logros en "
             f"{len(experiences)} empleo(s) · {with_metrics} con cifras")
    with st.expander(label, expanded=active or weak):
        st.markdown(
            "Tu CV solo puede usar lo que está en tu perfil: **entre más completo, mejor sale cada CV**. "
            "No te preocupes por la redacción; cuéntalo con tus palabras y la app lo ordena. "
            "Nunca se agrega nada que no hayas dicho tú."
        )
        by_id = {e.id: e for e in experiences}
        ordered = sorted(experiences, key=lambda e: (len(e.achievements), strength(e)[0]))  # los más flojos primero
        exp_id = st.selectbox(
            "¿Qué empleo quieres completar?",
            options=[e.id for e in ordered],
            format_func=lambda i: f"{by_id[i].role} — {by_id[i].company} ({len(by_id[i].achievements)} logros, "
            f"{strength(by_id[i])[0]} con cifras)",
            key="coach_exp",
        )
        mode = st.radio("¿Cómo quieres hacerlo?", options=list(MODES), format_func=MODES.get, horizontal=True, key="coach_mode")
        exp = by_id[exp_id]
        {"dump": _render_dump, "tasks": _render_tasks, "interview": _render_interview}[mode](profile, exp, overrides)
