import streamlit as st

from models import UserProfile
from storage import delete_education_entry, prepend_education, read_education


def _parse_education_entries(raw: str) -> list[dict]:
    entries = []
    current = None
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("### "):
            if current:
                entries.append(current)
            header = stripped[4:]
            parts = header.split(" | ", 1)
            title_inst = parts[0].rsplit(" - ", 1)
            if len(title_inst) == 2:
                titulo, institucion = title_inst
            else:
                titulo, institucion = header, ""
            periodo = parts[1] if len(parts) > 1 else ""
            current = {
                "titulo": titulo.strip(),
                "institucion": institucion.strip(),
                "periodo": periodo.strip(),
                "descripcion": "",
                "raw_line": stripped,
            }
        elif stripped.startswith("- ") and current:
            current["descripcion"] += stripped[2:] + " "
        elif stripped == "":
            continue
    if current:
        entries.append(current)
    return entries


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
            nueva_linea = f"### {nuevo_titulo.strip()} - {institucion.strip()} | {periodo_educacion.strip()}\n"
            if descripcion_educacion.strip():
                nueva_linea += f"- {descripcion_educacion.strip()}\n"
            nueva_linea += "\n"

            prepend_education(profile.slug, nueva_linea)
            st.success(":material/check: Educación/Certificación añadida correctamente.")
            st.rerun()

    st.markdown("---")
    st.subheader(":material/list_alt: Tu Historial Educativo")

    if profile is None:
        st.info("Selecciona un perfil para ver tu historial educativo.")
        return

    contenido = read_education(profile.slug)
    if contenido.strip():
        entries = _parse_education_entries(contenido)
        if entries:
            confirm_key = "edu_confirm_delete"
            if confirm_key not in st.session_state:
                st.session_state[confirm_key] = None

            for i, entry in enumerate(entries):
                border_color = "rgba(88,166,255,0.15)"
                card_html = (
                    f'<div style="'
                    f'background:rgba(22,27,34,0.4);'
                    f'border:1px solid {border_color};'
                    f'border-radius:8px;'
                    f'padding:12px 16px;'
                    f'margin-bottom:10px;'
                    f'">'
                    f'<div style="font-size:15px;font-weight:600;color:var(--color-accent,#58a6ff);">'
                    f'{entry["titulo"]}</div>'
                    f'<div style="font-size:13px;color:var(--color-text,#c9d1d9);margin-top:2px;">'
                    f'{entry["institucion"]}</div>'
                    f'<div style="font-size:12px;color:rgba(201,209,217,0.6);margin-top:1px;">'
                    f'{entry["periodo"]}</div>'
                )
                if entry["descripcion"].strip():
                    card_html += (
                        f'<div style="font-size:13px;color:rgba(201,209,217,0.8);margin-top:6px;">'
                        f'{entry["descripcion"].strip()}</div>'
                    )
                card_html += '</div>'
                st.markdown(card_html, unsafe_allow_html=True)

                if st.button(":material/delete: Eliminar", key=f"del_edu_{i}", type="secondary"):
                    st.session_state[confirm_key] = i
                    st.rerun()

            if st.session_state[confirm_key] is not None:
                idx = st.session_state[confirm_key]
                if idx < len(entries):
                    target = entries[idx]
                    st.warning(f"¿Eliminar **{target['titulo']}** de tu historial educativo?")
                    col_y, col_n = st.columns(2)
                    with col_y:
                        if st.button("Sí, eliminar", key="confirm_edu_del", type="primary"):
                            delete_education_entry(profile.slug, idx)
                            st.session_state[confirm_key] = None
                            st.success(f"'{target['titulo']}' eliminada.")
                            st.rerun()
                    with col_n:
                        if st.button("Cancelar", key="cancel_edu_del"):
                            st.session_state[confirm_key] = None
                            st.rerun()
        else:
            st.markdown(contenido)
    else:
        st.info("Aún no tienes educación o certificaciones registradas. ¡Agrega la primera arriba!")
