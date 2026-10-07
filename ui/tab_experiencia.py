import logging
import re

import streamlit as st

from config import WORK_MODALITIES
from core.llm import get_llm
from core.profile import service
from core.profile.completion import split_into_achievements
from core.profile.periods import parse_period
from core.profile.snapshot import ExperienceSnap
from models import UserProfile
from ui.importer import render_import
from ui.profile_coach import call_llm, render_profile_coach

logger = logging.getLogger(__name__)



def _lines(text: str) -> list[str]:
    """Una viñeta por línea; quita marcas de viñeta que el usuario haya pegado."""
    return [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line).strip() for line in text.splitlines() if line.strip()]


def _render_new_experience_form(profile: UserProfile | None, api_key_overrides: dict[str, str]) -> None:
    col1, col2 = st.columns(2)

    with col1:
        nuevo_cargo = st.text_input("Nombre del Cargo", placeholder="Ej: Auxiliar Administrativa")
        nombre_empresa = st.text_input("Empresa", placeholder="Ej: Logística SAS")
        periodo = st.text_input("Periodo", placeholder="Ej: Enero 2024 - Presente")

    with col2:
        pais = st.text_input("País", placeholder="Ej: Colombia")
        modalidad = st.selectbox("Modalidad", WORK_MODALITIES)

    logros_crudos = st.text_area(
        "Funciones y Logros (una por línea, o en texto libre)",
        placeholder="Escribe lo que hacías. Puedes guardarlo tal cual, o pulirlo con IA "
        "(redacción profesional, sin inventar datos)...",
        height=150,
    )

    col_ai, col_raw = st.columns(2)
    with col_ai:
        save_polished = st.button("Pulir con IA y guardar", type="primary", width="stretch")
    with col_raw:
        save_raw = st.button("Guardar tal cual", width="stretch")
    if not (save_polished or save_raw):
        return

    if profile is None:
        st.error(":material/warning: Primero crea o selecciona un perfil en la barra lateral.")
        return
    if not nuevo_cargo.strip() or not logros_crudos.strip():
        st.warning(":material/warning: Por favor llena al menos el Cargo y las Funciones.")
        return

    achievements = _lines(logros_crudos)
    if save_polished:
        draft = ExperienceSnap(0, nuevo_cargo.strip(), nombre_empresa.strip(), periodo.strip(), parse_period(periodo))
        candidates = call_llm(
            lambda: split_into_achievements(get_llm("extract", api_key_overrides), draft, logros_crudos),
            "Puliendo la redacción (sin inventar datos)...",
        )
        if candidates is None:
            return
        verified = [c.text for c in candidates if c.ok]
        if verified:
            achievements = verified  # si la IA no aportó nada verificable, se guarda el texto tal cual

    # Cargo, empresa y fechas salen del formulario, nunca de la IA.
    service.add_experience(
        profile.username, role=nuevo_cargo, company=nombre_empresa, period_text=periodo,
        country=pais, modality=modalidad, achievements=achievements,
    )
    st.session_state["exp_flash"] = f"Experiencia '{nuevo_cargo.strip()}' guardada con {len(achievements)} logro(s)."
    st.rerun()


def _render_existing_experiences(profile: UserProfile) -> None:
    experiences = service.list_experiences(profile.username)
    if not experiences:
        return

    st.markdown("---")
    st.subheader(f":material/list_alt: Experiencias registradas ({len(experiences)})")

    confirm_del_key = "exp_confirm_delete"
    for exp in experiences:
        exp_key = f"exp_{exp.id}"
        label = f"{exp.role} @ {exp.company}" if exp.company else exp.role
        if exp.period_text:
            label += f" — {exp.period_text}"

        with st.expander(label, expanded=False):
            details = " | ".join(part for part in (exp.period_text, exp.country, exp.modality) if part)
            if details:
                st.caption(details)
            for achievement in exp.achievements:
                st.markdown(f"- {achievement.text}")

            col_e1, col_e2, _ = st.columns([1, 1, 4])
            with col_e1:
                if st.button(":material/edit: Editar", key=f"edit_{exp_key}"):
                    st.session_state[f"editing_{exp_key}"] = True
                    st.rerun()
            with col_e2:
                if st.button(":material/delete: Borrar", key=f"del_{exp_key}"):
                    st.session_state[confirm_del_key] = exp.id
                    st.rerun()

            if st.session_state.get(confirm_del_key) == exp.id:
                st.warning("¿Eliminar permanentemente esta experiencia y sus logros?")
                col_y, col_n = st.columns(2)
                with col_y:
                    if st.button("Sí, eliminar", key=f"confirm_del_{exp_key}", type="primary"):
                        service.delete_experience(profile.username, exp.id)
                        st.session_state[confirm_del_key] = None
                        st.rerun()
                with col_n:
                    if st.button("Cancelar", key=f"cancel_del_{exp_key}"):
                        st.session_state[confirm_del_key] = None
                        st.rerun()

            if st.session_state.get(f"editing_{exp_key}"):
                _render_experience_editor(profile, exp, exp_key)


def _render_experience_editor(profile: UserProfile, exp, exp_key: str) -> None:
    st.markdown("---")
    with st.form(f"form_{exp_key}"):
        col1, col2 = st.columns(2)
        with col1:
            role = st.text_input("Cargo", value=exp.role)
            company = st.text_input("Empresa", value=exp.company)
            period = st.text_input("Periodo", value=exp.period_text)
        with col2:
            country = st.text_input("País", value=exp.country)
            modality_options = list(dict.fromkeys([*WORK_MODALITIES, exp.modality] if exp.modality else WORK_MODALITIES))
            modality = st.selectbox(
                "Modalidad", modality_options,
                index=modality_options.index(exp.modality) if exp.modality in modality_options else 0,
            )
        achievements = st.text_area(
            "Logros (uno por línea)",
            value="\n".join(a.text for a in exp.achievements),
            height=260,
        )
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            saved = st.form_submit_button(":material/check: Guardar cambios", type="primary")
        with col_s2:
            cancelled = st.form_submit_button("Cancelar")

    if saved:
        if not role.strip():
            st.warning("El cargo no puede quedar vacío.")
            return
        service.update_experience(
            profile.username, exp.id, achievements=_lines(achievements),
            role=role, company=company, period_text=period, country=country, modality=modality,
        )
    if saved or cancelled:
        st.session_state[f"editing_{exp_key}"] = False
        st.rerun()


def render_tab_experiencia(profile: UserProfile | None, api_key_overrides: dict[str, str]) -> None:
    st.header(":material/description: Tu experiencia")
    st.markdown("Cada logro se guarda por separado para elegir los mejores en cada CV.")

    flash = st.session_state.pop("exp_flash", None)
    if flash:
        st.success(f":material/check: {flash}")

    empty = profile is not None and not service.profile_status(profile.username)[0]
    if profile is not None and not empty:
        render_profile_coach(profile, api_key_overrides)  # el siguiente paso natural tras importar
    render_import(profile, api_key_overrides, expanded=empty)
    st.markdown("**O agrega una experiencia a mano**")
    _render_new_experience_form(profile, api_key_overrides)
    if profile:
        _render_existing_experiences(profile)
