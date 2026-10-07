import html

import streamlit as st

from config import SKILL_CATEGORIES
from core.profile import service
from models import UserProfile


def _categories_for(categories_in_use: list[str]) -> list[str]:
    """Categorías universales + las que el perfil ya usa (para no ocultar habilidades viejas)."""
    categories = list(SKILL_CATEGORIES)
    for category in categories_in_use:
        if category not in categories:
            categories.append(category)
    return categories


def render_tab_habilidades(profile: UserProfile | None) -> None:
    st.header(":material/build: Base Maestra de Habilidades (Skills)")
    st.markdown("Administra las herramientas, conocimientos y competencias que dominas.")

    skills = service.list_skills(profile.username) if profile else []
    categories = _categories_for([s.category for s in skills])

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        nueva_habilidad = st.text_input(
            "Nombre de la habilidad",
            placeholder="Ej: Excel avanzado, SAP, Facturación electrónica, Python",
            key="nueva_habilidad_input",
        )
    with col_s2:
        categoria_habilidad = st.selectbox("Categoría", categories, key="cat_habilidad")

    if st.button("Añadir Habilidad", type="primary"):
        if profile is None:
            st.error(":material/warning: Primero crea o selecciona un perfil en la barra lateral.")
        elif not nueva_habilidad.strip():
            st.warning(":material/warning: Escribe el nombre de la habilidad.")
        elif not service.add_skill(profile.username, nueva_habilidad.strip(), categoria_habilidad):
            st.warning(f":material/warning: '{nueva_habilidad.strip()}' ya existe en tu base de habilidades.")
        else:
            st.rerun()

    st.markdown("---")
    st.subheader(":material/list_alt: Tus Habilidades Registradas")

    if profile is None:
        st.info("Selecciona un perfil para ver tus habilidades.")
        return
    if not skills:
        st.info("Aún no tienes habilidades registradas. ¡Agrega la primera arriba!")
        return

    grouped: dict[str, list] = {}
    for skill in skills:
        grouped.setdefault(skill.category, []).append(skill)

    confirm_key = "skill_confirm_delete"
    for category in categories:
        items = grouped.get(category)
        if not items:
            continue
        with st.expander(f":material/category: {category} ({len(items)})"):
            pills_html = '<div style="display:flex;flex-wrap:wrap;gap:6px;">' + "".join(
                '<span style="background:rgba(88,166,255,0.12);color:var(--color-accent,#58a6ff);'
                "padding:3px 10px;border-radius:12px;font-size:13px;font-weight:500;"
                f'white-space:nowrap;">{html.escape(skill.name)}</span> '
                for skill in items
            ) + "</div>"
            st.markdown(pills_html, unsafe_allow_html=True)

            by_id = {skill.id: skill.name for skill in items}
            col_del, _col_spacer = st.columns([2, 3])
            with col_del:
                to_delete = st.selectbox(
                    "Seleccionar habilidad para eliminar",
                    options=[None, *by_id],
                    format_func=lambda sid, names=by_id: "—" if sid is None else names[sid],
                    key=f"skill_select_{category}",
                    label_visibility="collapsed",
                )
                if to_delete is not None and st.button(
                    ":material/delete: Eliminar", key=f"del_btn_{category}", type="secondary"
                ):
                    st.session_state[confirm_key] = (profile.username, to_delete, by_id[to_delete])
                    st.rerun()

    pending = st.session_state.get(confirm_key)
    if pending is not None and pending[0] != profile.username:
        pending = st.session_state[confirm_key] = None  # pertenecía a otro perfil
    if pending is not None:
        _, skill_id, name = pending
        st.warning(f"¿Eliminar **{name}**?")
        col_y, col_n = st.columns(2)
        with col_y:
            if st.button("Sí, eliminar", key=f"confirm_del_{skill_id}", type="primary"):
                service.delete_skill(profile.username, skill_id)
                st.session_state[confirm_key] = None
                st.rerun()
        with col_n:
            if st.button("Cancelar", key=f"cancel_del_{skill_id}"):
                st.session_state[confirm_key] = None
                st.rerun()
