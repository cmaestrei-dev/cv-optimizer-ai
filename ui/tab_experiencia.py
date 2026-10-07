import logging
import re

import streamlit as st

from config import WORK_MODALITIES
from core.profile import service
from core.profile.legacy import parse_education_markdown, parse_experience_markdown
from models import UserProfile
from services.gemini_client import GeminiClient
from utils.pdf_extractor import extract_text_from_pdf
from utils.retry import RetryableError, retry_with_backoff

logger = logging.getLogger(__name__)

_SKILL_LINE = re.compile(r"\*\*(.+?)\*\*\s*(?:->\s*\[?([^\]]+?)\]?)?\s*$")


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
            for parsed in parse_experience_markdown("\n".join(experiences)):
                service.add_experience(
                    profile.username, role=parsed.role, company=parsed.company,
                    period_text=parsed.period_text, country=parsed.country,
                    modality=parsed.modality, achievements=parsed.achievements,
                )
                imported += 1
        if import_skills:
            for skill_line in skills:
                match = _SKILL_LINE.search(skill_line)
                if match and service.add_skill(profile.username, match.group(1), match.group(2) or "Otros"):
                    imported += 1
        if import_edu:
            for parsed in parse_education_markdown("\n".join(education)):
                service.add_education(
                    profile.username, title=parsed.title, institution=parsed.institution,
                    period_text=parsed.period_text, description=parsed.description,
                )
                imported += 1
        st.session_state.pop("cv_parsed", None)
        st.session_state["exp_flash"] = f"{imported} elemento(s) importados correctamente."
        st.rerun()


def _lines(text: str) -> list[str]:
    """Una viñeta por línea; quita marcas de viñeta que el usuario haya pegado."""
    return [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line).strip() for line in text.splitlines() if line.strip()]


def _render_new_experience_form(client: GeminiClient | None, profile: UserProfile | None) -> None:
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
        save_polished = st.button("Pulir con IA y guardar", type="primary", use_container_width=True)
    with col_raw:
        save_raw = st.button("Guardar tal cual", use_container_width=True)
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
        if client is None:
            st.error(":material/warning: Por favor, ingresa tu API Key en la barra lateral primero.")
            return
        with st.spinner("Puliendo la redacción..."):

            @retry_with_backoff()
            def _call():
                return client.polish_experience(
                    role=nuevo_cargo, company=nombre_empresa, period=periodo,
                    country=pais, modality=modalidad, raw_details=logros_crudos,
                )

            try:
                parsed = parse_experience_markdown(_call())
            except RetryableError:
                st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
                return
            except RuntimeError as e:
                logger.error("Error de la API de Gemini: %s", e)
                st.error(f":material/cancel: Error de la API de Gemini: {e}")
                return
            except Exception:
                st.error(":material/cancel: Ocurrió un error inesperado. Por favor intenta de nuevo.")
                return
        if parsed and parsed[0].achievements:
            achievements = parsed[0].achievements

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


def render_tab_experiencia(client: GeminiClient | None, profile: UserProfile | None) -> None:
    st.header(":material/description: Registrar Nueva Experiencia")
    st.markdown("Añade un empleo con sus logros. Cada logro se guarda por separado para elegir los mejores en cada CV.")

    flash = st.session_state.pop("exp_flash", None)
    if flash:
        st.success(f":material/check: {flash}")

    _render_cv_import(client, profile)
    _render_new_experience_form(client, profile)
    if profile:
        _render_existing_experiences(profile)
