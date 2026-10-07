"""Pestaña del motor nuevo: analizar → ver compatibilidad y brechas → generar → editar → descargar."""

import logging

import streamlit as st

from core.engine import pipeline
from core.engine.document import render
from core.llm import LLMConfigError, StructuredOutputError, get_llm
from core.llm.client import Image
from core.profile import service
from core.profile.completion import split_into_achievements
from core.profile.interview import strength
from core.profile.snapshot import ProfileSnapshot
from core.vacancy import NotAVacancyError
from models import UserProfile
from services.docx_generator import build_docx_filename
from services.pdf_generator import build_pdf_filename
from utils.retry import RetryableError

logger = logging.getLogger(__name__)

_LEVEL_ICON = {
    "cubre": ":material/check_circle:",
    "parcial": ":material/contrast:",
    "no": ":material/cancel:",
}


def _run(action, spinner: str):
    """Ejecuta una llamada al motor mostrando errores comprensibles. Devuelve None si falla."""
    try:
        with st.spinner(spinner):
            return action()
    except NotAVacancyError:
        st.warning(":material/warning: El texto o la imagen no parecen una oferta de empleo.")
    except LLMConfigError as e:
        st.error(f":material/key: {e}")
    except RetryableError:
        st.error(":material/cancel: Los servidores de IA están saturados. Espera unos segundos y vuelve a intentarlo.")
    except StructuredOutputError:
        st.error(":material/cancel: La IA devolvió una respuesta inválida. Intenta de nuevo.")
    except (RuntimeError, ValueError) as e:
        logger.exception("Error del motor de CV")
        st.error(f":material/cancel: {e}")
    return None


def _evidence_label(ref: str, snap: ProfileSnapshot) -> str:
    kind, ref_id = ref[0], int(ref[1:])
    if kind == "L" and (found := snap.achievement(ref_id)):
        exp, achievement = found
        text = achievement.text if len(achievement.text) <= 70 else achievement.text[:70] + "…"
        return f"«{text}» ({exp.role})"
    if kind == "H":
        return next((f"habilidad {s.name}" for s in snap.skills if s.id == ref_id), ref)
    if kind == "E":
        return next((f"{e.title}" for e in snap.education if e.id == ref_id), ref)
    return ref


def _render_match(analysis: pipeline.Analysis, snap: ProfileSnapshot) -> None:
    vacancy, match = analysis.vacancy, analysis.match
    details = " · ".join(p for p in (vacancy.company, vacancy.area, vacancy.modality, vacancy.location) if p)
    st.markdown(f"#### {vacancy.role}")
    if details:
        st.caption(details)

    col_score, col_years = st.columns(2)
    with col_score:
        st.metric("Compatibilidad", f"{match.score}/100")
        st.progress(match.score / 100)
    with col_years:
        required = f" (pide {match.required_years:g})" if match.required_years else ""
        st.metric("Tu experiencia", f"{match.experience_years:g} años{required}")
        if match.meets_years is False:
            st.caption(":material/warning: No alcanzas los años pedidos; igual puedes postular si cumples lo demás.")

    st.markdown("**Requisitos de la vacante**")
    for m in match.requirements:
        kind = "obligatorio" if m.requirement.kind == "obligatorio" else "deseable"
        line = f"{_LEVEL_ICON[m.level]} **{m.requirement.text}** · _{kind}_"
        if m.evidence:
            line += "  \n  ↳ " + "; ".join(_evidence_label(ref, snap) for ref in m.evidence[:3])
        elif m.note:
            line += f"  \n  ↳ {m.note}"
        st.markdown(line)



def _render_gaps(state: dict, profile: UserProfile, overrides: dict[str, str]) -> None:
    """Brechas de la vacante, con la opción de contar cómo sí se ha hecho y sumarlo al perfil."""
    gaps = [m for m in state["analysis"].match.requirements if m.level != "cubre"]
    if not gaps:
        return
    missing = [m for m in gaps if m.level == "no"]
    must = [m for m in missing if m.requirement.kind == "obligatorio"]
    title = f":material/lightbulb: Te falta(n) {len(missing)} requisito(s)" if missing else ":material/lightbulb: Requisitos"
    title += f" ({len(must)} obligatorio(s))" if must else ""
    if len(gaps) > len(missing):
        title += f" y {len(gaps) - len(missing)} a medias"
    experiences = state["snap"].experiences
    with st.expander(title, expanded=True):
        st.caption(
            "¿Sí lo has hecho pero no está en tu perfil? Cuéntanos cómo, con tus palabras, y lo agregamos a tu "
            "experiencia. Si no lo has hecho, no pasa nada: el CV nunca incluye lo que no tengas."
        )
        for i, m in enumerate(gaps):
            kind = "obligatorio" if m.requirement.kind == "obligatorio" else "deseable"
            st.markdown(f"{_LEVEL_ICON[m.level]} **{m.requirement.text}** · _{kind}_")
            with st.popover(":material/add: Sí lo he hecho: contarlo"), st.form(f"ci_gap_form_{i}"):
                exp_id = st.selectbox(
                    "¿En qué empleo?", options=[e.id for e in experiences],
                    format_func=lambda eid: next(f"{e.role} — {e.company}" for e in experiences if e.id == eid),
                    key=f"ci_gap_exp_{i}",
                )
                story = st.text_area(
                    "¿Cómo lo hacías?", key=f"ci_gap_text_{i}",
                    placeholder="Ej.: usaba SAP para registrar las facturas de proveedores, unas 50 al mes",
                )
                if st.form_submit_button("Agregar a mi perfil", type="primary"):
                    _add_gap_story(profile, overrides, next(e for e in experiences if e.id == exp_id), m, story)


def _add_gap_story(profile: UserProfile, overrides: dict[str, str], exp, match_item, story: str) -> None:
    if not story.strip():
        st.warning("Cuéntanos cómo lo hacías.")
        return
    candidates = _run(
        lambda: split_into_achievements(
            get_llm("extract", overrides), exp, story, context=f"La vacante pide: {match_item.requirement.text}"
        ),
        "Agregando a tu perfil...",
    )
    if candidates is None:
        return
    texts = [c.text for c in candidates if c.suggested]
    added = service.append_achievements(profile.username, exp.id, texts) if texts else 0
    rejected = [c for c in candidates if not c.ok]
    message = f"Se agregaron {added} logro(s) a {exp.role}." if added else "No se agregó nada nuevo (ya estaba en tu perfil)."
    if rejected:
        message += f" Se descartaron {len(rejected)} por incluir datos que no escribiste."
    st.session_state["ci_flash"] = message
    st.session_state["ci_stale"] = True
    st.rerun()


def _reanalyze(state: dict, profile: UserProfile, overrides: dict[str, str]) -> None:
    snap = service.snapshot(profile.username)
    analysis = _run(
        lambda: pipeline.analyze(get_llm("extract", overrides), snap, state["text"], state["images"]),
        "Recalculando con tu perfil actualizado...",
    )
    if analysis is not None:
        state.update(analysis=analysis, snap=snap)
        st.session_state.pop("ci_cv", None)
        st.session_state.pop("ci_stale", None)
        st.rerun()


def _render_cv(state: dict, profile: UserProfile) -> None:
    generated: pipeline.GeneratedCV = state["cv"]
    doc, output = generated.document, generated.output

    if generated.reverted:
        with st.expander(f":material/shield: {len(generated.reverted)} viñeta(s) usan tu texto original"):
            st.caption("La versión de la IA agregaba datos que no están en tu perfil, así que se descartó.")
            for reasons in generated.reverted.values():
                st.markdown(f"- {'; '.join(reasons)}")
    if generated.summary_replaced:
        st.info(":material/shield: El resumen de la IA mencionaba datos no respaldados; se usó uno armado solo con tus datos.")
    if output.trimmed:
        with st.expander(f":material/content_cut: Para caber en 1 página se quitaron {len(output.trimmed)} elemento(s)"):
            for item in output.trimmed:
                st.markdown(f"- {item}")
    if output.pages > 1:
        st.warning(f":material/warning: El CV ocupa {output.pages} páginas incluso tras recortar.")

    filename = build_pdf_filename(profile, state["role"], state["company"])
    col_pdf, col_docx = st.columns(2)
    with col_pdf:
        st.download_button(
            ":material/download: Descargar PDF", data=output.pdf, file_name=filename,
            mime="application/pdf", type="primary", use_container_width=True, on_click="ignore",
        )
    with col_docx:
        st.download_button(
            ":material/download: Descargar DOCX (Word)", data=output.docx,
            file_name=build_docx_filename(filename),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True, on_click="ignore",
        )

    with st.expander(":material/preview: Vista previa", expanded=True):
        st.markdown(doc.to_markdown())

    with st.expander(":material/edit: Editar antes de descargar"):
        st.caption("Desmarca viñetas o ajusta su texto; luego actualiza el PDF. Lo que edites es tu responsabilidad.")
        with st.form("ci_edit_form"):
            summary = st.text_area("Resumen", value=doc.summary, height=110)
            edits = []
            for i, exp in enumerate(doc.experiences):
                st.markdown(f"**{exp.header}**")
                rows = [{"Incluir": b.included, "Viñeta": b.text} for b in exp.bullets]
                edits.append(
                    st.data_editor(
                        rows, key=f"ci_bullets_{i}", hide_index=True, use_container_width=True,
                        column_config={"Viñeta": st.column_config.TextColumn(width="large")},
                        disabled=False, num_rows="fixed",
                    )
                )
            apply = st.form_submit_button(":material/refresh: Actualizar PDF", type="primary")
        if apply:
            doc.summary = summary.strip()
            for exp, rows in zip(doc.experiences, edits, strict=True):
                for bullet, row in zip(exp.bullets, rows, strict=True):
                    bullet.included = bool(row["Incluir"])
                    bullet.text = str(row["Viñeta"]).strip()
            generated.output = render(doc, profile)
            st.rerun()


def render_tab_cv_inteligente(profile: UserProfile | None, api_key_overrides: dict[str, str]) -> None:
    st.header(":material/auto_awesome: CV inteligente")
    st.markdown(
        "Analiza la vacante, te muestra **qué cumples y qué te falta**, y arma un CV de una página "
        "eligiendo tus logros más relevantes. Todo sale de tu perfil: si la IA agrega algo que no "
        "puedes respaldar, se descarta automáticamente."
    )
    if profile is None:
        st.info("Crea o selecciona un perfil en la barra lateral para empezar.")
        return
    if not service.profile_status(profile.username)[0]:
        st.info(
            ":material/upload_file: **Tu perfil todavía no tiene experiencias.** Ve a la pestaña "
            "«Mi experiencia (importar CV)» y sube tu CV o el PDF de LinkedIn: se llena solo y tú revisas."
        )
    else:
        snap = service.snapshot(profile.username)
        with_metrics, total = (sum(x) for x in zip(*(strength(e) for e in snap.experiences), strict=True))
        if total == 0 or with_metrics / total < 0.5:
            st.info(
                f":material/trending_up: **Solo {with_metrics} de {total} logros tienen cifras.** Para un CV más "
                "fuerte, completa primero tu experiencia en la pestaña «Mi experiencia (importar CV)» (5 minutos)."
            )

    image = st.file_uploader("Captura de la vacante (opcional)", type=["png", "jpg", "jpeg", "webp"], key="ci_image")
    text = st.text_area("Texto de la vacante", placeholder="Pega aquí la oferta completa...", key="ci_text", height=180)
    focus = st.text_input(
        "Enfoque (opcional)", key="ci_focus",
        placeholder="Ej: destacar atención al cliente, enfocar en facturación...",
    )

    if st.button(":material/search: Analizar vacante", type="primary", key="ci_analyze"):
        if image is None and not text.strip():
            st.warning(":material/warning: Pega el texto de la vacante o sube una captura.")
        else:
            snap = service.snapshot(profile.username)
            if not snap.experiences:
                st.warning(":material/warning: Registra al menos una experiencia con sus logros antes de analizar.")
            else:
                images = (Image(image.getvalue(), image.type),) if image is not None else ()
                analysis = _run(
                    lambda: pipeline.analyze(get_llm("extract", api_key_overrides), snap, text, images),
                    "Analizando la vacante y tu perfil...",
                )
                if analysis is not None:
                    st.session_state["ci_analysis"] = {
                        "username": profile.username, "analysis": analysis, "snap": snap,
                        "text": text, "images": images,
                    }
                    st.session_state.pop("ci_cv", None)
                    st.session_state.pop("ci_stale", None)

    state = st.session_state.get("ci_analysis")
    if not state or state["username"] != profile.username:
        return

    st.divider()
    flash = st.session_state.pop("ci_flash", None)
    if flash:
        st.success(f":material/check: {flash}")
    if st.session_state.get("ci_stale"):
        st.warning(":material/update: Tu perfil cambió. Actualiza el puntaje antes de generar el CV.")
        if st.button(":material/refresh: Actualizar puntaje", type="primary", key="ci_reanalyze"):
            _reanalyze(state, profile, api_key_overrides)
    _render_match(state["analysis"], state["snap"])
    _render_gaps(state, profile, api_key_overrides)

    if st.button(":material/description: Generar CV", type="primary", key="ci_generate"):
        analysis: pipeline.Analysis = state["analysis"]
        generated = _run(
            lambda: pipeline.generate(
                get_llm("write", api_key_overrides), state["snap"], profile, analysis, extra_focus=focus
            ),
            "Seleccionando logros, redactando y verificando...",
        )
        if generated is not None:
            for key in [k for k in st.session_state if str(k).startswith("ci_bullets_")]:
                del st.session_state[key]  # el editor no debe mostrar ediciones del CV anterior
            st.session_state["ci_cv"] = {
                "username": profile.username, "cv": generated,
                "role": analysis.vacancy.role, "company": analysis.vacancy.company,
            }

    cv_state = st.session_state.get("ci_cv")
    if cv_state and cv_state["username"] == profile.username:
        st.divider()
        _render_cv(cv_state, profile)
