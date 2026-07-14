import re

import streamlit as st

from config import WORK_MODALITIES
from models import UserProfile
from services.gemini_client import GeminiClient
from storage import (
    append_skill,
    delete_experience_entry,
    get_experience_list,
    prepend_education,
    prepend_knowledge_base,
    update_experience,
)
from utils.pdf_extractor import extract_text_from_pdf
from utils.retry import RetryableError, retry_with_backoff


def _parse_cv_sections(raw: str) -> tuple[list[str], list[str], list[str]]:
    experiences = []
    skills = []
    education = []
    current_section = None
    buf: list[str] = []

    for line in raw.split("\n"):
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("EXPERIENCIAS:") or upper.startswith("EXPERIENCIA"):
            if current_section == "skills" and buf:
                skills.extend(buf)
            elif current_section == "education" and buf:
                education.extend(buf)
            current_section = "experience"
            buf = []
        elif upper.startswith("SKILLS:") or upper.startswith("HABILIDADES:"):
            if current_section == "experience" and buf:
                experiences.append("\n".join(buf).strip())
            elif current_section == "education" and buf:
                education.extend(buf)
            current_section = "skills"
            buf = []
        elif upper.startswith("EDUCACION:") or upper.startswith("EDUCACIÓN:"):
            if current_section == "experience" and buf:
                experiences.append("\n".join(buf).strip())
            elif current_section == "skills" and buf:
                skills.extend(buf)
            current_section = "education"
            buf = []
        elif stripped.startswith("### ") and current_section == "experience" and buf:
            experiences.append("\n".join(buf).strip())
            buf = [stripped]
        elif current_section:
            buf.append(stripped)

    if current_section == "experience" and buf:
        experiences.append("\n".join(buf).strip())
    elif current_section == "skills" and buf:
        skills.extend(buf)
    elif current_section == "education" and buf:
        education.extend(buf)

    return experiences, skills, education


def _render_cv_import(client: GeminiClient | None, profile: UserProfile | None) -> None:
    if profile is None:
        return

    with st.expander(":material/upload_file: Importar desde CV o LinkedIn (PDF)", expanded=False):
        pdf_file = st.file_uploader(
            "Subí tu CV en PDF",
            type=["pdf"],
            key="cv_import_pdf",
            label_visibility="collapsed",
        )
        if pdf_file is None:
            return

        if client is None:
            st.error(":material/warning: Ingresá tu API Key en la barra lateral primero.")
            return

        file_bytes = pdf_file.read()
        with st.spinner("Extrayendo texto del PDF..."):
            cv_markdown = extract_text_from_pdf(file_bytes)
        if not cv_markdown:
            st.error(":material/cancel: No se pudo extraer texto del PDF. ¿Es un documento escaneado?")
            return

        with st.expander(":material/preview: Texto extraído del PDF", expanded=False):
            st.text(cv_markdown[:5000] + ("..." if len(cv_markdown) > 5000 else ""))

        if st.button(":material/magic_button: Analizar CV con IA", key="parse_cv_btn", type="primary"):
            with st.spinner("Parseando CV con Gemini..."):
                try:
                    @retry_with_backoff()
                    def _parse():
                        return client.parse_cv_document(cv_markdown)

                    raw = _parse()
                except Exception as e:
                    st.error(f":material/cancel: Error al procesar el CV: {e}")
                    return

            st.session_state["cv_parsed"] = raw
            st.rerun()

    parsed = st.session_state.get("cv_parsed", "")
    if not parsed:
        return

    experiences, skills, education = _parse_cv_sections(parsed)

    st.markdown("---")
    st.subheader(":material/preview: Datos encontrados en el CV")

    import_exp = import_skills = import_edu = False
    if experiences:
        import_exp = st.checkbox(f":material/check: Importar {len(experiences)} experiencia(s)", value=True, key="imp_exp")
        if import_exp:
            with st.expander(":material/preview: Vista previa de experiencias"):
                for exp_text in experiences:
                    st.markdown(exp_text)
                    st.divider()
    else:
        st.info("No se encontraron experiencias en el CV.")

    if skills:
        import_skills = st.checkbox(f":material/check: Importar {len(skills)} skill(s)", value=True, key="imp_skills")
        if import_skills:
            with st.expander(":material/preview: Vista previa de skills"):
                for s in skills:
                    st.markdown(s)
    else:
        st.info("No se encontraron skills en el CV.")

    if education:
        import_edu = st.checkbox(f":material/check: Importar {len(education)} entrada(s) de educación", value=True, key="imp_edu")
        if import_edu:
            with st.expander(":material/preview: Vista previa de educación"):
                for e in education:
                    st.markdown(e)
                    st.divider()

    if not any([import_exp, import_skills, import_edu]):
        return

    if st.button(":material/check: Importar seleccionados a mi perfil", type="primary", key="do_import"):
        imported = 0
        if import_exp:
            for exp_text in experiences:
                exp_text = exp_text.strip()
                if exp_text:
                    prepend_knowledge_base(profile.slug, exp_text)
                    imported += 1
        if import_skills:
            for skill_line in skills:
                skill_line = skill_line.strip()
                if skill_line and re.search(r"\*\*(.+?)\*\*", skill_line):
                    append_skill(profile.slug, skill_line)
                    imported += 1
        if import_edu:
            for edu_text in education:
                edu_text = edu_text.strip()
                if edu_text:
                    prepend_education(profile.slug, edu_text)
                    imported += 1
        st.session_state.pop("cv_parsed", None)
        st.success(f":material/check: {imported} elemento(s) importados correctamente.")
        st.rerun()


def _render_new_experience_form(client: GeminiClient | None, profile: UserProfile | None) -> None:
    col1, col2 = st.columns(2)

    with col1:
        nuevo_cargo = st.text_input("Nombre del Cargo", placeholder="Ej: Analista de Soporte IT")
        nombre_empresa = st.text_input("Empresa", placeholder="Ej: Tech Solutions Inc.")
        periodo = st.text_input("Periodo", placeholder="Ej: Enero 2024 - Presente")

    with col2:
        pais = st.text_input("País", placeholder="Ej: Colombia")
        modalidad = st.selectbox("Modalidad", WORK_MODALITIES)

    logros_crudos = st.text_area(
        "Funciones y Logros (Texto crudo)",
        placeholder="Escribe o pega en bruto lo que hacías. La IA lo pulirá y le dará formato técnico...",
        height=150,
    )

    if st.button("Guardar en Base Maestra", type="primary"):
        if client is None:
            st.error(":material/warning: Por favor, ingresa tu API Key en la barra lateral primero.")
        elif profile is None:
            st.error(":material/warning: Primero crea o selecciona un perfil en la barra lateral.")
        elif not nuevo_cargo or not nombre_empresa or not logros_crudos:
            st.warning(":material/warning: Por favor llena al menos el Cargo, la Empresa y las Funciones.")
        else:
            with st.spinner("Estandarizando y guardando experiencia..."):

                @retry_with_backoff()
                def _call():
                    return client.polish_experience(
                        role=nuevo_cargo,
                        company=nombre_empresa,
                        period=periodo,
                        country=pais,
                        modality=modalidad,
                        raw_details=logros_crudos,
                    )

                try:
                    nueva_exp_pulida = _call()
                    prepend_knowledge_base(profile.slug, nueva_exp_pulida)
                    st.success(":material/check: Nueva experiencia añadida a tu base de conocimiento.")
                    with st.expander(":material/preview: Ver formato guardado"):
                        st.markdown(nueva_exp_pulida)
                except RetryableError:
                    st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
                except RuntimeError:
                    st.error(":material/cancel: Hubo un problema al comunicarse con la IA. Revisa tu API Key e intenta de nuevo.")
                except Exception:
                    st.error(":material/cancel: Ocurrió un error inesperado. Por favor intenta de nuevo.")


def _render_existing_experiences(profile: UserProfile) -> None:
    exp_list = get_experience_list(profile.slug)
    if not exp_list:
        return

    st.markdown("---")
    st.subheader(f":material/list_alt: Experiencias registradas ({len(exp_list)})")

    confirm_del_key = "exp_confirm_delete"
    if confirm_del_key not in st.session_state:
        st.session_state[confirm_del_key] = None

    for i, exp in enumerate(exp_list):
        exp_key = f"exp_{exp['id']}"
        first_line = exp["content"].split("\n")[0].strip()
        label = f"Experiencia #{len(exp_list) - i}"
        if first_line.startswith("### "):
            header = first_line[4:]
            parts = header.split(" - ", 1)
            if len(parts) == 2:
                role = parts[0].strip()
                company = parts[1].split(" | ")[0].strip()
                label = f"{role} @ {company}"

        with st.expander(label, expanded=False):
            st.markdown(exp["content"])

            col_e1, col_e2, col_e3 = st.columns([1, 1, 4])
            with col_e1:
                if st.button(":material/edit: Editar", key=f"edit_{exp_key}"):
                    st.session_state[f"editing_{exp_key}"] = True
                    st.rerun()
            with col_e2:
                if st.button(":material/delete: Borrar", key=f"del_{exp_key}"):
                    st.session_state[confirm_del_key] = exp_key
                    st.rerun()

            if st.session_state[confirm_del_key] == exp_key:
                st.warning("¿Eliminar permanentemente esta experiencia?")
                col_y, col_n = st.columns(2)
                with col_y:
                    if st.button("Sí, eliminar", key=f"confirm_del_{exp_key}", type="primary"):
                        delete_experience_entry(exp["id"])
                        st.session_state[confirm_del_key] = None
                        st.success("Experiencia eliminada.")
                        st.rerun()
                with col_n:
                    if st.button("Cancelar", key=f"cancel_del_{exp_key}"):
                        st.session_state[confirm_del_key] = None
                        st.rerun()

            if st.session_state.get(f"editing_{exp_key}"):
                st.markdown("---")
                edited = st.text_area(
                    "Editar experiencia (formato Markdown)",
                    value=exp["content"],
                    height=300,
                    key=f"ta_{exp_key}",
                )
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    if st.button(":material/check: Guardar cambios", key=f"save_{exp_key}", type="primary"):
                        update_experience(exp["id"], edited.strip())
                        st.session_state[f"editing_{exp_key}"] = False
                        st.success("Experiencia actualizada.")
                        st.rerun()
                with col_s2:
                    if st.button("Cancelar", key=f"cancel_{exp_key}"):
                        st.session_state[f"editing_{exp_key}"] = False
                        st.rerun()


def render_tab_experiencia(client: GeminiClient | None, profile: UserProfile | None) -> None:
    st.header(":material/description: Registrar Nueva Experiencia")
    st.markdown("Añade un nuevo logro o empleo a tu base de datos local permanente.")

    _render_cv_import(client, profile)
    _render_new_experience_form(client, profile)
    if profile:
        _render_existing_experiences(profile)
