import streamlit as st

from config import SKILL_CATEGORIES
from models import UserProfile
from storage import append_skill, get_skills_lines, overwrite_skills


def _extract_skill_name(line: str) -> str:
    import re

    match = re.search(r"\*\*(.+?)\*\*", line)
    return match.group(1).strip().lower() if match else ""


def render_tab_habilidades(profile: UserProfile | None) -> None:
    st.header(":material/build: Base Maestra de Habilidades (Skills)")
    st.markdown("Administra las tecnologías, herramientas y metodologías que dominas.")

    col_s1, col_s2 = st.columns(2)

    with col_s1:
        nueva_habilidad = st.text_input(
            "Nombre de la Habilidad / Tecnología",
            placeholder="Ej: Python, Docker, Scrum, PostgreSQL",
            key="nueva_habilidad_input",
        )

    with col_s2:
        categoria_habilidad = st.selectbox("Categoría", SKILL_CATEGORIES, key="cat_habilidad")

    if st.button("Añadir Habilidad", type="primary"):
        if profile is None:
            st.error(":material/warning: Primero crea o selecciona un perfil en la barra lateral.")
        elif not nueva_habilidad.strip():
            st.warning(":material/warning: Escribe el nombre de la habilidad.")
        else:
            skill_name = nueva_habilidad.strip()
            existing_lines = get_skills_lines(profile.slug)
            nueva_linea = f"- **{skill_name}** -> [{categoria_habilidad}]\n"

            already_exists = any(
                _extract_skill_name(line) == skill_name.lower()
                for line in existing_lines
            )
            if already_exists:
                st.warning(f":material/warning: '{skill_name}' ya existe en tu base de habilidades.")
            else:
                append_skill(profile.slug, nueva_linea)
                st.success(f":material/check: '{skill_name}' guardada correctamente.")
                st.rerun()

    st.markdown("---")
    st.subheader(":material/list_alt: Tus Habilidades Registradas")

    if profile is None:
        st.info("Selecciona un perfil para ver tus habilidades.")
        return

    lines = get_skills_lines(profile.slug)

    if not lines:
        st.info("Aún no tienes habilidades registradas. ¡Agrega la primera arriba!")
        return

    parsed_skills = []
    for raw_line in lines:
        name = _extract_skill_name(raw_line)
        cat = None
        for c in SKILL_CATEGORIES:
            if f"[{c}]" in raw_line:
                cat = c
                break
        if name and cat:
            parsed_skills.append((name, cat, raw_line))

    if parsed_skills:
        grouped = {}
        for name, cat, raw_line in parsed_skills:
            grouped.setdefault(cat, []).append((name, raw_line))

        confirm_key = "skill_confirm_delete"
        if confirm_key not in st.session_state:
            st.session_state[confirm_key] = None

        for cat, items in grouped.items():
            with st.expander(f":material/category: {cat} ({len(items)})"):
                pills_html = '<div style="display:flex;flex-wrap:wrap;gap:6px;">'
                for _i, (name, _raw_line) in enumerate(items):
                    pills_html += (
                        f'<span style="'
                        f'background:rgba(88,166,255,0.12);'
                        f'color:var(--color-accent,#58a6ff);'
                        f'padding:3px 10px;'
                        f'border-radius:12px;'
                        f'font-size:13px;'
                        f'font-weight:500;'
                        f'white-space:nowrap;'
                        f'">{name}</span> '
                    )
                pills_html += '</div>'
                st.markdown(pills_html, unsafe_allow_html=True)

                col_del, _col_spacer = st.columns([2, 3])
                with col_del:
                    skill_to_delete = st.selectbox(
                        "Seleccionar habilidad para eliminar",
                        options=["—"] + [name for name, _ in items],
                        key=f"skill_select_{cat}",
                        label_visibility="collapsed",
                    )
                    if skill_to_delete != "—" and st.button(
                        ":material/delete: Eliminar", key=f"del_btn_{cat}", type="secondary"
                    ):
                        st.session_state[confirm_key] = (cat, skill_to_delete)
                        st.rerun()

        if st.session_state[confirm_key] is not None:
            cat, name = st.session_state[confirm_key]
            st.warning(f"¿Eliminar **{name}** de {cat}?")
            col_y, col_n = st.columns(2)
            with col_y:
                if st.button("Sí, eliminar", key=f"confirm_del_{cat}_{name}", type="primary"):
                    target_line = next(
                        (rl for n, rl in parsed_skills if n == name), None
                    )
                    if target_line:
                        remaining = [line for line in lines if line != target_line]
                        overwrite_skills(profile.slug, remaining)
                    st.session_state[confirm_key] = None
                    st.success(f"'{name}' eliminada.")
                    st.rerun()
            with col_n:
                if st.button("Cancelar", key=f"cancel_del_{cat}_{name}"):
                    st.session_state[confirm_key] = None
                    st.rerun()
    else:
        skills_to_delete = []
        for cat in SKILL_CATEGORIES:
            skills_cat = [line for line in lines if f"[{cat}]" in line]
            if skills_cat:
                with st.expander(f"{cat} ({len(skills_cat)})"):
                    for i, s in enumerate(skills_cat):
                        col_a, col_b = st.columns([10, 1])
                        with col_a:
                            limpio = s.replace(f" -> [{cat}]", "").strip()
                            st.markdown(limpio)
                        with col_b:
                            if st.button("Eliminar", key=f"del_skill_{cat}_{i}", help="Eliminar"):
                                skills_to_delete.append(s)
        if skills_to_delete:
            remaining = [line for line in lines if line not in skills_to_delete]
            overwrite_skills(profile.slug, remaining)
            st.success(f"{len(skills_to_delete)} habilidad(es) eliminada(s).")
            st.rerun()
