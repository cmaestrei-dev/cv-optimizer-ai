import html

import streamlit as st

from core.profile import service
from models import UserProfile


def render_tab_educacion(profile: UserProfile | None) -> None:
    st.header(":material/school: Educación y Certificaciones")
    st.markdown("Administra tu historial educativo y certificaciones profesionales.")

    col_e1, col_e2 = st.columns(2)

    with col_e1:
        nuevo_titulo = st.text_input(
            "Título o Certificación",
            placeholder="Ej: Ingeniero de Sistemas, AWS Certified Developer",
            key="edu_titulo",
        )
        institucion = st.text_input(
            "Institución / Entidad",
            placeholder="Ej: Universidad Nacional, Amazon Web Services",
            key="edu_institucion",
        )

    with col_e2:
        periodo_educacion = st.text_input(
            "Año o Periodo",
            placeholder="Ej: 2018-2022, Julio 2023",
            key="edu_periodo",
        )
        descripcion_educacion = st.text_area(
            "Descripción Adicional (Opcional)",
            placeholder="Ej: Especialización en Machine Learning, Certificación en Cloud",
            key="edu_descripcion",
        )

    if st.button("Añadir Educación/Certificación", type="primary"):
        if profile is None:
            st.error(":material/warning: Primero crea o selecciona un perfil en la barra lateral.")
        elif not nuevo_titulo.strip() or not institucion.strip() or not periodo_educacion.strip():
            st.warning(":material/warning: Por favor, llena el Título/Certificación, Institución y Año/Periodo.")
        else:
            service.add_education(
                profile.username,
                title=nuevo_titulo,
                institution=institucion,
                period_text=periodo_educacion,
                description=descripcion_educacion,
            )
            st.rerun()

    st.markdown("---")
    st.subheader(":material/list_alt: Tu Historial Educativo")

    if profile is None:
        st.info("Selecciona un perfil para ver tu historial educativo.")
        return

    entries = service.list_education(profile.username)
    if not entries:
        st.info("Aún no tienes educación o certificaciones registradas. ¡Agrega la primera arriba!")
        return

    confirm_key = "edu_confirm_delete"
    for entry in entries:
        card_html = (
            '<div style="background:rgba(22,27,34,0.4);border:1px solid rgba(88,166,255,0.15);'
            'border-radius:8px;padding:12px 16px;margin-bottom:10px;">'
            '<div style="font-size:15px;font-weight:600;color:var(--color-accent,#58a6ff);">'
            f"{html.escape(entry.title)}</div>"
            '<div style="font-size:13px;color:var(--color-text,#c9d1d9);margin-top:2px;">'
            f"{html.escape(entry.institution)}</div>"
            '<div style="font-size:12px;color:rgba(201,209,217,0.6);margin-top:1px;">'
            f"{html.escape(entry.period_text)}</div>"
        )
        if entry.description:
            card_html += (
                '<div style="font-size:13px;color:rgba(201,209,217,0.8);margin-top:6px;">'
                f"{html.escape(entry.description)}</div>"
            )
        st.markdown(card_html + "</div>", unsafe_allow_html=True)

        if st.button(":material/delete: Eliminar", key=f"del_edu_{entry.id}", type="secondary"):
            st.session_state[confirm_key] = (profile.username, entry.id, entry.title)
            st.rerun()

    pending = st.session_state.get(confirm_key)
    if pending is not None and pending[0] != profile.username:
        pending = st.session_state[confirm_key] = None  # pertenecía a otro perfil
    if pending is not None:
        _, education_id, title = pending
        st.warning(f"¿Eliminar **{title}** de tu historial educativo?")
        col_y, col_n = st.columns(2)
        with col_y:
            if st.button("Sí, eliminar", key="confirm_edu_del", type="primary"):
                service.delete_education(profile.username, education_id)
                st.session_state[confirm_key] = None
                st.rerun()
        with col_n:
            if st.button("Cancelar", key="cancel_edu_del"):
                st.session_state[confirm_key] = None
                st.rerun()
