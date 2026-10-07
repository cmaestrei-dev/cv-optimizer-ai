"""Entrevista guiada para fortalecer los logros de un cargo con datos reales del usuario."""

import logging

import streamlit as st

from core.llm import LLMConfigError, StructuredOutputError, get_llm
from core.profile import service
from core.profile.interview import (
    generate_questions,
    merge_achievements,
    propose_improvements,
    strength,
)
from models import UserProfile
from utils.retry import RetryableError

logger = logging.getLogger(__name__)

_STATE = "interview"


def _call(action, spinner: str):
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
        logger.exception("Error en la entrevista guiada")
        st.error(f":material/cancel: {e}")
    return None


def render_interview(profile: UserProfile, api_key_overrides: dict[str, str]) -> None:
    snap = service.snapshot(profile.username)
    experiences = [e for e in snap.experiences if e.achievements or e.role]
    if not experiences:
        return
    with_metrics = sum(strength(e)[0] for e in experiences)
    total = sum(strength(e)[1] for e in experiences)

    state = st.session_state.get(_STATE)
    if state and state["username"] != profile.username:
        st.session_state.pop(_STATE, None)
        state = None

    label = ":material/forum: Mejorar mis logros con una entrevista guiada"
    if total:
        label += f" · {with_metrics} de {total} logros tienen cifras"
    weak = total == 0 or with_metrics / total < 0.5 or any(not e.achievements for e in experiences)
    with st.expander(label, expanded=state is not None or weak):
        st.markdown(
            "Los reclutadores se fijan en **cifras y resultados**. Te haremos unas preguntas cortas sobre un "
            "empleo y, con tus respuestas, propondremos viñetas más fuertes. Solo se usa lo que tú respondas."
        )
        by_id = {e.id: e for e in experiences}
        ordered = sorted(experiences, key=lambda e: strength(e)[0] / max(strength(e)[1], 1))  # los más débiles primero
        exp_id = st.selectbox(
            "¿Qué empleo quieres mejorar?",
            options=[e.id for e in ordered],
            format_func=lambda i: f"{by_id[i].role} — {by_id[i].company} ({strength(by_id[i])[0]}/{strength(by_id[i])[1]} con cifras)",
            key="interview_exp",
        )
        if state and state["exp"].id != exp_id:
            st.session_state.pop(_STATE, None)
            state = None

        if state is None:
            if st.button(":material/help: 1. Hazme las preguntas", type="primary", key="interview_start"):
                exp = by_id[exp_id]
                questions = _call(lambda: generate_questions(get_llm("extract", api_key_overrides), exp),
                                  "Preparando preguntas...")
                if questions:
                    for key in [k for k in st.session_state if str(k).startswith(("interview_q_", "interview_p_"))]:
                        del st.session_state[key]  # sin respuestas de una entrevista anterior
                    st.session_state[_STATE] = {"username": profile.username, "exp": exp, "questions": questions, "proposals": None}
                    st.rerun()
                elif questions is not None:
                    st.info("Este empleo ya tiene logros muy completos; no hay preguntas que hacer.")
            return

        exp, questions = state["exp"], state["questions"]
        if state["proposals"] is None:
            with st.form("interview_answers"):
                st.caption("Responde lo que sepas. Si no sabes o no aplica, déjalo vacío.")
                answers = [
                    st.text_input(q.question, placeholder=f"Ej.: {q.example}" if q.example else "", key=f"interview_q_{i}")
                    for i, q in enumerate(questions)
                ]
                col_go, col_cancel = st.columns(2)
                with col_go:
                    go = st.form_submit_button(":material/auto_fix_high: 2. Proponer mejoras", type="primary", use_container_width=True)
                with col_cancel:
                    cancel = st.form_submit_button("Cancelar", use_container_width=True)
            if cancel:
                st.session_state.pop(_STATE, None)
                st.rerun()
            if go:
                proposals = _call(
                    lambda: propose_improvements(get_llm("write", api_key_overrides), exp, list(zip(questions, answers, strict=True))),
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
                before = p.original or "_(logro nuevo)_"
                if p.ok:
                    if st.checkbox(f"**Después:** {p.proposed}", value=True, key=f"interview_p_{i}"):
                        accepted.append(p)
                    st.caption(f"Antes: {before}")
                else:
                    st.markdown(f":material/block: ~~{p.proposed}~~")
                    st.caption(f"Descartada: {'; '.join(p.problems)}")
            col_save, col_cancel = st.columns(2)
            with col_save:
                save = st.form_submit_button(":material/save: 3. Guardar mejoras", type="primary", use_container_width=True)
            with col_cancel:
                discard = st.form_submit_button("Descartar", use_container_width=True)
        if save and accepted:
            service.update_experience(profile.username, exp.id, achievements=merge_achievements(exp, accepted))
            st.session_state["exp_flash"] = f"Se mejoraron {len(accepted)} logro(s) de {exp.role}."
        if save or discard:
            st.session_state.pop(_STATE, None)
            st.rerun()
