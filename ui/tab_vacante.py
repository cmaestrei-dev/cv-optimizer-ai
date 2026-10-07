import logging

import streamlit as st

from core.profile import service
from core.profile.repository import skill_key
from models import UserProfile
from services.docx_generator import build_docx_filename, generate_docx
from services.gemini_client import GeminiClient, JobParsingError
from services.pdf_generator import build_pdf_filename, generate_pdf, parse_vacancy_header
from utils.retry import RetryableError, retry_with_backoff

logger = logging.getLogger(__name__)


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
        placeholder="Ej: Destacar liderazgo de equipos, enfocar en atención al cliente, resaltar manejo de inventarios...",
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

    if btn_solo_procesar or btn_procesar_generar:
        if not has_image and not has_text:
            st.warning(":material/warning: Debes subir una imagen, pegar texto, o ambos.")
        elif client is None:
            st.error(":material/warning: Por favor, ingresa tu API Key en la barra lateral primero.")
        elif btn_solo_procesar:
            _procesar_vacante(client, archivo_imagen, texto_plano)
        else:
            _procesar_y_generar(client, profile, archivo_imagen, texto_plano, enfoque_adicional)

    # Los resultados viven en session_state: así sobreviven a los reruns de Streamlit
    # (descargas, botones de skills) en lugar de desaparecer tras el primer clic.
    _render_results(client, profile)


def _build_multimodal_call(client: GeminiClient, archivo_imagen, texto_plano: str):
    image_bytes = None
    image_mime = ""
    if archivo_imagen is not None:
        image_bytes = archivo_imagen.getvalue()
        image_mime = archivo_imagen.type

    @retry_with_backoff()
    def _call():
        return client.analyze_job_posting(
            text=texto_plano.strip() if texto_plano.strip() else "",
            image_data=image_bytes,
            image_mime=image_mime,
        )

    return _call()


def _store_vacancy_analysis(resultado: str) -> None:
    st.session_state["vacante_analizada"] = resultado
    st.session_state.pop("cv_result", None)
    st.session_state["show_vacancy_skills"] = False
    for key in list(st.session_state.keys()):
        if key.startswith(("_extracted_skills_", "skills_select_")):
            del st.session_state[key]


def _render_skills_from_vacancy(client: GeminiClient, profile: UserProfile) -> None:
    vacancy_result = st.session_state.get("vacante_analizada", "")
    if not vacancy_result:
        return

    existing_keys = {skill_key(s.name) for s in service.list_skills(profile.username)}

    cache_key = f"_extracted_skills_{profile.username}"
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
        st.session_state[cache_key] = sorted(s for s in extracted if skill_key(s) not in existing_keys)

    missing = st.session_state[cache_key]
    if not missing:
        st.success(":material/check: Todas las skills detectadas ya están en tu perfil.")
        return

    with st.expander(":material/build: Skills detectadas en la vacante", expanded=True):
        st.caption("Agrega solo las que realmente dominas: el CV nunca incluye habilidades que no tengas.")
        selected = st.multiselect(
            f"Se encontraron {len(missing)} skills que no tienes registradas. ¿Cuáles quieres agregar?",
            options=missing,
            key=f"skills_select_{profile.username}",
        )
        if selected and st.button(
            f":material/add: Agregar {len(selected)} skill(s) a mi perfil",
            type="primary",
            key=f"add_skills_btn_{profile.username}",
        ):
            for skill in selected:
                service.add_skill(profile.username, skill, "Otros")
            st.session_state[cache_key] = [s for s in missing if s not in selected]
            st.session_state.pop(f"skills_select_{profile.username}", None)
            st.rerun()


def _procesar_vacante(client: GeminiClient, archivo_imagen, texto_plano: str) -> None:
    with st.spinner("Analizando vacante con Gemini..."):
        try:
            resultado = _build_multimodal_call(client, archivo_imagen, texto_plano)
            _store_vacancy_analysis(resultado)
            st.success(":material/check: Vacante procesada con éxito!")
        except RetryableError:
            st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
        except JobParsingError as e:
            st.warning(f":material/warning: {e}")
        except RuntimeError as e:
            logger.error("Error de la API de Gemini: %s", e)
            st.error(f":material/cancel: Error de la API de Gemini: {e}")
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
    if not all(service.profile_status(profile.username)):
        st.warning(":material/warning: Primero registra al menos una Experiencia, una Habilidad y Educación en las otras pestañas.")
        return

    status = st.status("Procesando...", expanded=True)

    with status:
        st.write(":material/search: Analizando vacante...")
        try:
            resultado = _build_multimodal_call(client, archivo_imagen, texto_plano)
            _store_vacancy_analysis(resultado)
        except RetryableError:
            st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
            return
        except JobParsingError as e:
            st.warning(f":material/warning: {e}")
            return
        except RuntimeError as e:
            logger.error("Error de la API de Gemini: %s", e)
            st.error(f":material/cancel: Error de la API de Gemini: {e}")
            return
        except Exception:
            st.error(":material/cancel: Ocurrió un error inesperado. Por favor intenta de nuevo.")
            return

        header = parse_vacancy_header(resultado)
        area = header.get("AREA", "")
        language = header.get("LANGUAGE", "")
        detected = ", ".join(
            part for part in (f"área: {area}" if area else "", f"idioma: {language}" if language else "")
            if part
        )
        st.write(f":material/check_circle: Vacante analizada{f' ({detected})' if detected else ''}.")

        st.write(":material/description: Generando CV adaptado...")
        experiencias, habilidades, educacion = service.legacy_markdown(profile.username)

        @retry_with_backoff()
        def _generate():
            return client.generate_cv(
                job_posting=resultado,
                experiences=experiencias,
                skills=habilidades,
                education=educacion,
                extra_focus=enfoque,
                user_full_name=profile.full_name,
                language=language,
                area=area,
            )

        try:
            cv_final = _generate()
            st.write(":material/check_circle: CV generado.")
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

        st.write(":material/description: Creando PDF y DOCX...")
        filename = build_pdf_filename(profile, header.get("ROLE", ""), header.get("COMPANY", ""))

        try:
            pdf_bytes = generate_pdf(cv_final, profile)
            docx_bytes = generate_docx(cv_final, profile)
        except Exception as e:
            logger.exception("Error al generar los archivos del CV")
            st.error(f":material/cancel: Error al generar los archivos del CV: {e}")
            return

        st.session_state["cv_result"] = {
            "slug": profile.username,
            "cv_markdown": cv_final,
            "pdf_filename": filename,
            "pdf": pdf_bytes,
            "docx_filename": build_docx_filename(filename),
            "docx": docx_bytes,
        }
        status.update(label=":material/check_circle: CV generado con éxito!", state="complete")


def _render_results(client: GeminiClient | None, profile: UserProfile | None) -> None:
    result = st.session_state.get("cv_result")
    if result and profile and result["slug"] == profile.username:
        st.divider()
        with st.expander(":material/preview: Vista previa del CV", expanded=True):
            st.markdown(result["cv_markdown"])

        col_pdf, col_docx = st.columns(2)
        with col_pdf:
            st.download_button(
                label=":material/download: Descargar PDF",
                data=result["pdf"],
                file_name=result["pdf_filename"],
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                on_click="ignore",
            )
        with col_docx:
            st.download_button(
                label=":material/download: Descargar DOCX (Word)",
                data=result["docx"],
                file_name=result["docx_filename"],
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                on_click="ignore",
            )
        st.caption(
            "PDF para enviar por correo o portales que lo acepten; "
            "DOCX para portales que piden Word o si quieres editarlo."
        )

    analysis = st.session_state.get("vacante_analizada", "")
    if not analysis:
        return

    with st.expander(":material/preview: Ver análisis de la vacante", expanded=result is None):
        st.code(analysis, language="markdown")

    if profile is not None and client is not None:
        if st.button(":material/build: Extraer skills de la vacante", key="extract_skills_btn"):
            st.session_state["show_vacancy_skills"] = True
        if st.session_state.get("show_vacancy_skills"):
            _render_skills_from_vacancy(client, profile)
