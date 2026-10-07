"""Pestaña del motor nuevo: analizar → ver compatibilidad y brechas → generar → editar → descargar."""

import json
import logging
import uuid

import streamlit as st

from core.capture import CaptureError, capture_vacancy
from core.engine import pipeline
from core.engine.cover import write_cover_note
from core.engine.document import render
from core.engine.screening import answer_screening
from core.llm import LLMConfigError, StructuredOutputError, get_llm
from core.llm.client import Image
from core.profile import service
from core.profile.completion import split_into_achievements
from core.profile.interview import strength
from core.profile.snapshot import ProfileSnapshot
from core.tracking import service as tracking
from core.tracking.models import PLATFORMS
from core.vacancy import NotAVacancyError
from models import UserProfile
from services.docx_generator import build_docx_filename
from services.pdf_generator import build_pdf_filename
from ui.text import md
from utils.retry import RetryableError

logger = logging.getLogger(__name__)

_LEVEL_ICON = {
    "cubre": ":material/check_circle:",
    "parcial": ":material/contrast:",
    "no": ":material/cancel:",
}


def run_engine(action, spinner: str):
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
    st.markdown(f"#### {md(vacancy.role)}")
    if details:
        st.caption(md(details))

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
        line = f"{_LEVEL_ICON[m.level]} **{md(m.requirement.text)}** · _{kind}_"
        if m.evidence:
            line += "  \n  ↳ " + "; ".join(md(_evidence_label(ref, snap)) for ref in m.evidence[:3])
        elif m.note:
            line += f"  \n  ↳ {md(m.note)}"
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
            st.markdown(f"{_LEVEL_ICON[m.level]} **{md(m.requirement.text)}** · _{kind}_")
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
    candidates = run_engine(
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
    analysis = run_engine(
        lambda: pipeline.analyze(get_llm("extract", overrides), snap, state["text"], state["images"]),
        "Recalculando con tu perfil actualizado...",
    )
    if analysis is not None:
        state.update(analysis=analysis, snap=snap)
        if state.get("application_id"):
            tracking.set_match(profile.username, state["application_id"], analysis.match.score,
                               json.dumps(pipeline.match_summary(analysis.match), ensure_ascii=False))
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
            mime="application/pdf", type="primary", width="stretch", on_click="ignore",
        )
    with col_docx:
        st.download_button(
            ":material/download: Descargar DOCX (Word)", data=output.docx,
            file_name=build_docx_filename(filename),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch", on_click="ignore",
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
                        rows, key=f"ci_bullets_{i}", hide_index=True, width="stretch",
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

    for key, value in st.session_state.pop("ci_pending_inputs", {}).items():
        st.session_state[key] = value
    _render_capture()
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
                analysis = run_engine(
                    lambda: pipeline.analyze(get_llm("extract", api_key_overrides), snap, text, images),
                    "Analizando la vacante y tu perfil...",
                )
                if analysis is not None:
                    st.session_state["ci_analysis"] = {
                        "username": profile.username, "analysis": analysis, "snap": snap,
                        "text": text, "images": images, "token": uuid.uuid4().hex,
                        "source": captured if (captured := st.session_state.get("ci_captured")) and captured["text"] == text else None,
                    }
                    st.session_state.pop("ci_cv", None)
                    st.session_state.pop("ci_stale", None)

    state = st.session_state.get("ci_analysis")
    if not state or state["username"] != profile.username:
        return
    if state.get("application_id") and not tracking.exists(profile.username, state["application_id"]):
        state.pop("application_id")  # la borraron en «Mis postulaciones»: se crea de nuevo si hace falta
        for key in ("saved_hash", "sent", "cv_record_id"):
            (st.session_state.get("ci_cv") or {}).pop(key, None)

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
    _render_screening(state, api_key_overrides)
    _render_cover(state, api_key_overrides)
    _render_save_vacancy(state, profile)

    if st.button(":material/description: Generar CV", type="primary", key="ci_generate"):
        analysis: pipeline.Analysis = state["analysis"]
        generated = run_engine(
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
        _render_tracking(state, cv_state, profile)


# ── seguimiento: guardar la vacante y el CV exacto en "Mis postulaciones" ──


_REUSABLE = ("por_revisar", "guardada", "cv_generado")  # aún sin enviar: misma vacante, misma postulación


def _ensure_application(state: dict, profile: UserProfile, platform: str = "", url: str = "") -> int:
    """Una postulación por análisis: se crea la primera vez y se reutiliza."""
    if state.get("application_id"):
        return state["application_id"]
    source = state.get("source") or {}
    platform, url = platform or source.get("platform", ""), url or source.get("url", "")
    existing = tracking.find_by_url(profile.username, url) if url else None
    vacancy = state["analysis"].vacancy
    same = existing is not None and (
        existing.vacancy_text == state.get("text", "") or existing.role.casefold() == vacancy.role.strip().casefold()
    )
    if same and existing.status in _REUSABLE:
        if existing.status == "por_revisar":
            tracking.change_status(profile.username, existing.id, "guardada", "Preparada desde «CV inteligente»")
        state["application_id"] = existing.id
        return existing.id
    state["application_id"] = tracking.create_application(
        profile.username, role=vacancy.role, company=vacancy.company, platform=platform, url=url,
        vacancy_text=state.get("text", ""), analysis_json=vacancy.model_dump_json(),
        match_score=state["analysis"].match.score,
    )
    return state["application_id"]


def _render_save_vacancy(state: dict, profile: UserProfile) -> None:
    if state.get("application_id"):
        st.caption(f":material/bookmark_added: Vacante guardada en «Mis postulaciones» (#{state['application_id']}).")
    elif st.button(":material/bookmark: Guardar esta vacante para después", key="ci_save_vacancy"):
        _ensure_application(state, profile)
        st.session_state["ci_flash"] = "Vacante guardada en «Mis postulaciones»."
        st.rerun()


def _render_tracking(state: dict, cv_state: dict, profile: UserProfile) -> None:
    output = cv_state["cv"].output
    current_hash = tracking.sha256(output.pdf)
    if not cv_state.get("sent"):
        _render_checklist(state, cv_state, profile)
    st.markdown("**Seguimiento**")
    if cv_state.get("saved_hash") == current_hash:
        label = "enviado" if cv_state.get("sent") else "guardado"
        st.success(
            f":material/verified: Este CV quedó {label} en «Mis postulaciones» con la huella `{current_hash[:12]}`. "
            "Allí puedes registrar respuestas, entrevistas y recordatorios."
        )
        if not cv_state.get("sent") and st.button(":material/send: Ya la envié", key="ci_mark_sent"):
            tracking.mark_sent(profile.username, state["application_id"], cv_state["cv_record_id"])
            cv_state["sent"] = True
            st.rerun()
        return

    if cv_state.get("saved_hash"):
        st.info(":material/edit: Editaste el CV después de guardarlo: registra esta versión si es la que vas a enviar.")
    with st.form("ci_track_form"):
        col_platform, col_url = st.columns([1, 2])
        source = state.get("source") or {}
        platform = col_platform.selectbox(
            "¿Por dónde vas a postular?", PLATFORMS, key="ci_track_platform",
            index=PLATFORMS.index(source["platform"]) if source.get("platform") in PLATFORMS else 0,
        )
        url = col_url.text_input("Enlace de la vacante (opcional)", value=source.get("url", ""), key="ci_track_url")
        col_save, col_sent = st.columns(2)
        save = col_save.form_submit_button(":material/bookmark: Guardar en mis postulaciones", width="stretch")
        sent = col_sent.form_submit_button(":material/send: Ya la envié", type="primary", width="stretch")
    if save or sent:
        application_id = _ensure_application(state, profile, platform, url)
        filename = build_pdf_filename(profile, cv_state["role"], cv_state["company"])
        cv_state["cv_record_id"] = tracking.attach_cv(
            profile.username, application_id, pdf=output.pdf, docx=output.docx,
            markdown=cv_state["cv"].document.to_markdown(), language=cv_state["cv"].document.language, filename=filename,
        )
        if sent:
            tracking.mark_sent(profile.username, application_id, cv_state["cv_record_id"], platform=platform)
        cv_state["saved_hash"], cv_state["sent"] = current_hash, sent
        st.rerun()


# ── captura por enlace y preguntas de filtro (fase 3) ─────────────────


def _render_capture() -> None:
    col_url, col_btn = st.columns([4, 1], vertical_alignment="bottom")
    url = col_url.text_input(
        "Enlace de la vacante (LinkedIn, Computrabajo, Magneto, elempleo o la página de la empresa)",
        key="ci_url", placeholder="https://...",
    )
    if col_btn.button(":material/download: Traer", key="ci_fetch", width="stretch"):
        if not url.strip():
            st.warning("Pega primero el enlace de la vacante.")
            return
        try:
            with st.spinner("Leyendo la vacante..."):
                captured = capture_vacancy(url)
        except CaptureError as e:
            st.warning(f":material/link_off: {e}")
            return
        st.session_state["ci_text"] = captured.text
        st.session_state["ci_captured"] = {"text": captured.text, "url": captured.url, "platform": captured.platform}
        how = "datos estructurados del portal" if captured.source == "jobposting" else "el texto de la página"
        st.session_state["ci_flash"] = f"Vacante traída de {captured.platform} ({how}). Revisa el texto y analízala."
        st.rerun()
    flash = st.session_state.get("ci_flash")
    if flash and "Vacante traída" in flash:
        st.session_state.pop("ci_flash")
        st.success(f":material/check: {flash}")


def _render_screening(state: dict, overrides: dict[str, str]) -> None:
    results = st.session_state.get("ci_screening")
    if results and results["token"] != state.get("token"):
        results = None
    with st.expander(":material/quiz: Preguntas del formulario del portal", expanded=results is not None):
        st.caption(
            "Muchos portales hacen preguntas al postular (años de experiencia, herramientas, disponibilidad). "
            "Pégalas aquí, una por línea: respondemos con los datos de tu perfil y marcamos lo que solo tú sabes."
        )
        with st.form("ci_screening_form"):
            questions = st.text_area("Preguntas (una por línea)", key="ci_screening_q", height=110,
                                     placeholder="¿Cuántos años de experiencia tiene en facturación?\n¿Cuál es su aspiración salarial?")
            go = st.form_submit_button(":material/auto_awesome: Proponer respuestas")
        if go and questions.strip():
            answers = run_engine(
                lambda: answer_screening(get_llm("write", overrides), questions.splitlines(), state["snap"], state["analysis"].vacancy),
                "Respondiendo con tu perfil...",
            )
            if answers is not None:
                st.session_state["ci_screening"] = results = {"token": state.get("token"), "answers": answers}
        if results:
            for a in results["answers"]:
                st.markdown(f"**{a.question}**")
                if a.answer.strip():
                    st.code(a.answer, language=None, wrap_lines=True)
                if a.needs_you:
                    st.caption(f":material/person: Respóndela tú: {a.note or 'depende de ti'}")
                elif a.note:
                    st.caption(a.note)


def _render_cover(state: dict, overrides: dict[str, str]) -> None:
    cover = st.session_state.get("ci_cover")
    if cover and cover["token"] != state.get("token"):
        cover = None
    with st.expander(":material/mail: Mensaje para el reclutador", expanded=cover is not None):
        st.caption(
            "Para el campo «carta de presentación» del portal, un correo o un mensaje por LinkedIn. "
            "Solo usa datos de tu perfil."
        )
        label = ":material/refresh: Escribir otro" if cover else ":material/auto_awesome: Escribir mensaje"
        if st.button(label, key="ci_cover_btn"):
            analysis: pipeline.Analysis = state["analysis"]
            note = run_engine(
                lambda: write_cover_note(get_llm("write", overrides), analysis.vacancy, analysis.match, state["snap"]),
                "Escribiendo el mensaje...",
            )
            if note is not None:
                st.session_state["ci_cover"] = cover = {"token": state.get("token"), "note": note}
        if cover:
            st.code(cover["note"].text, language=None, wrap_lines=True)
            if cover["note"].fallback:
                st.caption(
                    ":material/shield: El borrador de la IA mencionaba datos que no están en tu perfil; este mensaje "
                    "usa solo tus datos. Ajústalo a tu gusto antes de enviarlo."
                )


def _render_checklist(state: dict, cv_state: dict, profile: UserProfile) -> None:
    """Lo que la persona hace en el portal: la app nunca envía por ella."""
    filename = build_pdf_filename(profile, cv_state["role"], cv_state["company"])
    url = (state.get("source") or {}).get("url", "")
    st.markdown("**Antes de enviar en el portal**")
    steps = [
        f"Sube **{md(filename)}** (o su versión DOCX): es el CV hecho para esta vacante.",
        "Responde las preguntas del formulario (sección «Preguntas del formulario del portal»).",
        "Si el portal lo permite, pega el mensaje para el reclutador.",
        "Vuelve aquí y marca **Ya la envié**: queda registrado qué CV exacto enviaste.",
    ]
    st.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(steps, start=1)))
    if url:
        st.link_button(":material/open_in_new: Abrir la vacante para postular", url)
