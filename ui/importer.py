"""Importar un CV o el PDF de LinkedIn al perfil, en pasos claros."""

import hashlib
import logging

import streamlit as st

from core.llm import LLMConfigError, StructuredOutputError, get_llm
from core.profile import service
from core.profile.importer import ImportPlan, extract_cv, plan_import
from models import UserProfile
from utils.pdf_extractor import extract_text_from_pdf
from utils.retry import RetryableError

logger = logging.getLogger(__name__)

_STATE = "import_plan"


def _read_with_ai(profile: UserProfile, pdf_text: str, file_hash: str, api_key_overrides: dict[str, str]) -> None:
    try:
        with st.spinner("Leyendo tu CV... (unos segundos)"):
            imported = extract_cv(get_llm("extract", api_key_overrides), pdf_text)
            plan = plan_import(imported, pdf_text, service.snapshot(profile.username))
    except LLMConfigError as e:
        st.error(f":material/key: {e}")
        return
    except RetryableError:
        st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
        return
    except StructuredOutputError:
        st.error(":material/cancel: La IA no pudo leer bien el CV. Intenta de nuevo.")
        return
    except RuntimeError as e:
        logger.exception("Error importando CV")
        st.error(f":material/cancel: {e}")
        return
    st.session_state[_STATE] = {"username": profile.username, "hash": file_hash, "plan": plan}


def _render_review(profile: UserProfile, plan: ImportPlan) -> None:
    data = plan.data
    n_achievements = sum(len(data.experiences[i].achievements) for i in plan.new_experiences)
    st.markdown("**3. Revisa lo que encontramos** (desmarca lo que no quieras guardar)")
    st.caption(
        f"{len(plan.new_experiences)} experiencia(s) nuevas con {n_achievements} logro(s), "
        f"{len(plan.new_skills)} habilidad(es) y {len(plan.new_education)} estudio(s)."
    )

    if plan.duplicate_experiences:
        roles = ", ".join(data.experiences[i].role for i in plan.duplicate_experiences)
        st.info(f":material/info: Ya tienes en tu perfil: {roles}. No se vuelven a agregar.")
    if plan.discarded:
        with st.expander(f":material/shield: Se descartaron {len(plan.discarded)} dato(s) que no aparecen en tu PDF"):
            for item in plan.discarded:
                st.markdown(f"- {item}")

    with st.form("import_review_form"):
        chosen_exp = []
        for i in plan.new_experiences:
            e = data.experiences[i]
            title = f"{e.role} — {e.company}" if e.company else e.role
            details = " | ".join(p for p in (e.period_text, e.country, e.modality) if p)
            if st.checkbox(f"**{title}**" + (f"  ·  {details}" if details else ""), value=True, key=f"imp_exp_{i}"):
                chosen_exp.append(i)
            if e.achievements:
                st.markdown("\n".join(f"  - {a}" for a in e.achievements))
            else:
                st.caption("Sin descripción en el PDF: después podrás agregarle logros en esta pestaña.")

        chosen_skills = []
        if plan.new_skills:
            options = {i: data.skills[i].name for i in plan.new_skills}
            chosen_skills = st.multiselect(
                "Habilidades", options=list(options), default=list(options),
                format_func=lambda i, names=options: names[i],
            )

        chosen_edu = []
        if plan.new_education:
            st.markdown("**Estudios**")
            for i in plan.new_education:
                e = data.education[i]
                label = " - ".join(p for p in (e.title, e.institution) if p) + (f" | {e.period_text}" if e.period_text else "")
                if st.checkbox(label, value=True, key=f"imp_edu_{i}"):
                    chosen_edu.append(i)

        fill_contact = st.checkbox(
            "Completar mis datos de contacto vacíos (nombre, email, teléfono, LinkedIn) con los del PDF", value=True
        )
        col_save, col_cancel = st.columns(2)
        with col_save:
            save = st.form_submit_button(":material/save: 4. Guardar en mi perfil", type="primary", use_container_width=True)
        with col_cancel:
            cancel = st.form_submit_button("Descartar", use_container_width=True)

    if save:
        counts = service.apply_import(
            profile.username, data, experiences=chosen_exp, skills=chosen_skills,
            education=chosen_edu, fill_contact=fill_contact,
        )
        st.session_state.pop(_STATE, None)
        st.session_state["exp_flash"] = (
            "Importado: " + ", ".join(f"{v} {k}" for k, v in counts.items())
            + ". Siguiente paso: completa y mejora tus logros (justo aquí abajo): LinkedIn suele quedarse corto."
        )
        st.rerun()
    if cancel:
        st.session_state.pop(_STATE, None)
        st.rerun()


def render_import(profile: UserProfile | None, api_key_overrides: dict[str, str], *, expanded: bool) -> None:
    with st.expander(":material/upload_file: Importar mi CV o mi perfil de LinkedIn (PDF)", expanded=expanded):
        if profile is None:
            st.info("Primero crea o selecciona tu perfil en la barra lateral.")
            return
        st.markdown(
            "La forma más rápida de llenar tu perfil. La IA **copia** tus datos del PDF (no inventa nada) "
            "y tú revisas antes de guardar."
        )
        st.caption(
            "¿Cómo obtener el PDF de LinkedIn? Entra a tu perfil de LinkedIn desde un computador → botón "
            "«Más» (o «Recursos») → «Guardar en PDF»."
        )
        pdf = st.file_uploader("1. Sube el PDF", type=["pdf"], key="import_pdf")
        if pdf is None:
            return

        file_bytes = pdf.getvalue()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        state = st.session_state.get(_STATE)
        if state and (state["username"] != profile.username or state["hash"] != file_hash):
            st.session_state.pop(_STATE, None)
            state = None

        if state is None:
            pdf_text = extract_text_from_pdf(file_bytes)
            if not pdf_text or len(pdf_text.strip()) < 50:
                st.error(
                    ":material/cancel: No pudimos leer texto en ese PDF (¿es una imagen escaneada?). "
                    "Prueba con el PDF que exporta LinkedIn o con un CV hecho en Word."
                )
                return
            if st.button(":material/auto_awesome: 2. Leer mi CV con IA", type="primary", key="import_read"):
                _read_with_ai(profile, pdf_text, file_hash, api_key_overrides)
                state = st.session_state.get(_STATE)

        if state is not None:
            _render_review(profile, state["plan"])
