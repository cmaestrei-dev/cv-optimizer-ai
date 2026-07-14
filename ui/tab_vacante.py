import streamlit as st

from models import UserProfile
from services.gemini_client import GeminiClient, JobParsingError
from services.pdf_generator import build_pdf_filename, generate_pdf, parse_vacancy_fields
from storage import (
    all_data_files_exist,
    append_skill,
    get_skills_lines,
    read_education,
    read_knowledge_base,
    read_skills,
)
from utils.retry import RetryableError, retry_with_backoff


def render_tab_vacante(client: GeminiClient | None, profile: UserProfile | None) -> None:
    st.header(":material/inbox: Vacante y Generar CV")

    st.markdown("Sube una captura de pantalla, pega el texto de la vacante, o **ambos** para mayor precisión.")

    archivo_imagen = st.file_uploader(
        "Captura de pantalla de la vacante (opcional)",
        type=["png", "jpg", "jpeg", "webp"],
        key="vacante_imagen",
    )

    texto_plano = st.text_area(
        "Texto de la vacante (opcional, complementa la imagen si es necesario)",
        placeholder="Pega aquí el texto de la vacante...",
        key="vacante_texto",
    )

    if archivo_imagen is None and not texto_plano.strip():
        st.info(":material/lightbulb: Sube una imagen, pega texto, o combina ambos para obtener mejores resultados.")

    st.divider()

    st.subheader(":material/track_changes: Ajustes (Opcional)")
    enfoque_adicional = st.text_input(
        "¿Algún enfoque especial para este CV?",
        placeholder="Ej: Destacar liderazgo técnico, enfocar hacia backend, resaltar experiencia en cloud...",
        key="enfoque_vacante",
    )

    col1, col2 = st.columns(2)
    with col1:
        btn_solo_procesar = st.button(
            "Solo procesar vacante",
            type="secondary",
            use_container_width=True,
            key="btn_solo_procesar",
        )
    with col2:
        btn_procesar_generar = st.button(
            "Procesar y Generar CV",
            type="primary",
            use_container_width=True,
            key="btn_procesar_generar",
        )

    has_image = archivo_imagen is not None
    has_text = bool(texto_plano.strip())

    if not has_image and not has_text:
        if btn_solo_procesar or btn_procesar_generar:
            st.warning(":material/warning: Debes subir una imagen, pegar texto, o ambos.")
        return

    if client is None:
        if btn_solo_procesar or btn_procesar_generar:
            st.error(":material/warning: Por favor, ingresa tu API Key en la barra lateral primero.")
        return

    if btn_solo_procesar:
        _procesar_vacante(client, archivo_imagen, texto_plano, profile)

    if btn_procesar_generar:
        _procesar_y_generar(client, profile, archivo_imagen, texto_plano, enfoque_adicional)


def _build_multimodal_call(client: GeminiClient, archivo_imagen, texto_plano: str):
    image_bytes = None
    image_mime = ""
    if archivo_imagen is not None:
        image_bytes = archivo_imagen.read()
        image_mime = archivo_imagen.type

    @retry_with_backoff()
    def _call():
        return client.analyze_job_posting(
            text=texto_plano.strip() if texto_plano.strip() else "",
            image_data=image_bytes,
            image_mime=image_mime,
        )

    return _call()


def _extract_skill_name_from_line(line: str) -> str:
    import re

    match = re.search(r"\*\*(.+?)\*\*", line)
    return match.group(1).strip().lower() if match else ""


def _render_skills_from_vacancy(client: GeminiClient, profile: UserProfile) -> None:
    vacancy_result = st.session_state.get("vacante_analizada", "")
    if not vacancy_result:
        return

    existing_lines = get_skills_lines(profile.slug)
    existing_names = {_extract_skill_name_from_line(line) for line in existing_lines}
    existing_names.discard("")

    cache_key = f"_extracted_skills_{profile.slug}"
    if cache_key not in st.session_state:
        with st.spinner("Extrayendo skills de la vacante..."):
            try:

                @retry_with_backoff()
                def _call():
                    return client.extract_skills_from_vacancy(vacancy_result)

                raw_skills = _call()
            except Exception:
                st.warning("No se pudieron extraer skills automáticamente.")
                return

        extracted = {
            line.strip() for line in raw_skills.split("\n")
            if line.strip() and not line.strip().startswith("#")
        }
        st.session_state[cache_key] = sorted(extracted - existing_names)

    missing = st.session_state[cache_key]
    if not missing:
        st.success(":material/check: Todas las skills detectadas ya están en tu perfil.")
        return

    with st.expander(":material/build: Skills detectadas en la vacante", expanded=True):
        selected = st.multiselect(
            f"Se encontraron {len(missing)} skills que no tenés registradas. ¿Cuáles querés agregar?",
            options=missing,
            key=f"skills_select_{profile.slug}",
        )
        if selected and st.button(
            f":material/add: Agregar {len(selected)} skill(s) a mi perfil",
            type="primary",
            key=f"add_skills_btn_{profile.slug}",
        ):
            for skill in selected:
                append_skill(profile.slug, f"- **{skill}** -> [Otros]\n")
            remaining = [s for s in missing if s not in selected]
            st.session_state[cache_key] = remaining
            st.success(f":material/check: {len(selected)} skill(s) agregadas a tu perfil.")
            st.rerun()


def _procesar_vacante(client: GeminiClient, archivo_imagen, texto_plano: str, profile: UserProfile | None = None) -> None:
    with st.spinner("Analizando vacante con Gemini..."):
        try:
            resultado = _build_multimodal_call(client, archivo_imagen, texto_plano)
            st.session_state["vacante_analizada"] = resultado
            st.success(":material/check: Vacante procesada con éxito!")
            with st.expander(":material/preview: Ver análisis de la vacante", expanded=True):
                st.code(resultado, language="markdown")
            if profile:  # noqa: SIM102
                if st.button(":material/build: Extraer skills de la vacante", key="extract_skills_btn"):
                    _render_skills_from_vacancy(client, profile)
        except RetryableError:
            st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
        except JobParsingError as e:
            st.warning(f":material/warning: {e}")
        except RuntimeError:
            st.error(":material/cancel: Hubo un problema al comunicarse con la IA. Revisa tu API Key e intenta de nuevo.")
        except Exception:
            st.error(":material/cancel: Ocurrió un error inesperado. Por favor intenta de nuevo.")


def _procesar_y_generar(
    client: GeminiClient,
    profile: UserProfile | None,
    archivo_imagen,
    texto_plano: str,
    enfoque: str,
) -> None:
    if profile is None:
        st.error(":material/warning: Primero crea o selecciona un perfil en la barra lateral.")
        return
    if not all_data_files_exist(profile.slug):
        st.warning(":material/warning: Primero registra al menos una Experiencia, una Habilidad y Educación en las otras pestañas.")
        return

    status = st.status("Procesando...", expanded=True)

    with status:
        st.write(":material/search: Analizando vacante...")
        try:
            resultado = _build_multimodal_call(client, archivo_imagen, texto_plano)
            st.session_state["vacante_analizada"] = resultado
            st.write(":material/check_circle: Vacante analizada.")
        except RetryableError:
            st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
            return
        except JobParsingError as e:
            st.warning(f":material/warning: {e}")
            return
        except RuntimeError:
            st.error(":material/cancel: Hubo un problema al comunicarse con la IA. Revisa tu API Key e intenta de nuevo.")
            return
        except Exception:
            st.error(":material/cancel: Ocurrió un error inesperado. Por favor intenta de nuevo.")
            return

        st.write(":material/description: Generando CV adaptado...")
        experiencias = read_knowledge_base(profile.slug)
        habilidades = read_skills(profile.slug)
        educacion = read_education(profile.slug)

        @retry_with_backoff()
        def _generate():
            return client.generate_cv(
                job_posting=resultado,
                experiences=experiencias,
                skills=habilidades,
                education=educacion,
                extra_focus=enfoque,
                user_full_name=profile.full_name,
            )

        try:
            cv_final = _generate()
            st.write(":material/check_circle: CV generado.")
        except RetryableError:
            st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
            return
        except RuntimeError:
            st.error(":material/cancel: Hubo un problema al comunicarse con la IA. Revisa tu API Key e intenta de nuevo.")
            return
        except Exception:
            st.error(":material/cancel: Ocurrió un error inesperado. Por favor intenta de nuevo.")
            return

        st.write(":material/description: Creando PDF...")
        role, company = parse_vacancy_fields(resultado)
        filename = build_pdf_filename(profile, role, company)

        try:
            output_path = generate_pdf(cv_final, profile, output_path=f"output/{filename}")
            st.write(":material/check_circle: PDF listo.")
            status.update(label=":material/check_circle: CV generado con éxito!", state="complete")
        except Exception as pdf_e:
            st.error(f":material/cancel: Error al generar el PDF: {pdf_e}. ¿Tienes wkhtmltopdf instalado?")
            return

    st.divider()

    if st.button(":material/build: Extraer skills de la vacante", key="extract_skills_btn2"):
        _render_skills_from_vacancy(client, profile)

    with st.expander(":material/preview: Vista previa del CV", expanded=True):
        st.markdown(cv_final)

    st.success(f":material/description: Archivo: `{filename}`")

    with open(output_path, "rb") as pdf_file:
        st.download_button(
            label=f":material/download: Descargar {filename}",
            data=pdf_file.read(),
            file_name=filename,
            mime="application/pdf",
            type="primary",
        )

    with st.expander(":material/preview: Ver análisis de la vacante"):
        st.code(resultado, language="markdown")
