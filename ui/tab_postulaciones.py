"""Mis postulaciones: estado, CV exacto enviado, historial, notas y recordatorios."""

from datetime import timedelta

import streamlit as st

from core.tracking import service as tracking
from core.tracking.models import (
    ACTIVE_STATUSES,
    APPLIED_STATUSES,
    PLATFORMS,
    STATUSES,
    TRIAGE_STATUSES,
    Application,
)
from models import UserProfile
from ui.text import md

_EVENT_LABELS = {
    "creada": ":material/add_circle: Creada",
    "cv_generado": ":material/description: CV generado",
    "cv_enviado": ":material/send: Enviada",
    "estado": ":material/swap_horiz: Estado",
    "nota": ":material/sticky_note_2: Nota",
    "recordatorio": ":material/alarm: Recordatorio",
    "datos": ":material/edit: Datos",
}


def _status_label(status: str) -> str:
    label, icon = STATUSES[status]
    return f"{icon} {label}"


def due_count(profile: UserProfile | None) -> int:
    if profile is None:
        return 0
    try:
        return len(tracking.summary(profile.username).due)
    except Exception:  # la pestaña nunca debe tumbar la app
        return 0


def _render_summary(username: str) -> None:
    s = tracking.summary(username)
    cols = st.columns(5)
    cols[0].metric("Postulaciones", s.total)
    cols[1].metric("Enviadas", s.sent)
    cols[2].metric("En proceso", s.by_status["en_revision"] + s.by_status["entrevista"])
    cols[3].metric("Ofertas", s.by_status["oferta"])
    cols[4].metric("Respuesta", "—" if s.response_rate is None else f"{s.response_rate:.0%}")
    if s.due:
        lines = "\n".join(
            f"- **{md(a.role)} — {md(a.company or 'empresa sin nombre')}**: {md(a.next_action or 'hacer seguimiento')} "
            f"(desde el {a.next_action_on.strftime('%d/%m')})"
            for a in s.due
        )
        st.warning(f":material/alarm: **Para hacer hoy**\n{lines}")


def _render_new(username: str) -> None:
    with st.expander(":material/add: Registrar una postulación hecha fuera de la app"), st.form("track_new"):
        col_a, col_b = st.columns(2)
        role = col_a.text_input("Cargo")
        company = col_b.text_input("Empresa")
        platform = col_a.selectbox("Plataforma", PLATFORMS)
        url = col_b.text_input("Enlace (opcional)")
        options = [s for s in STATUSES if s not in TRIAGE_STATUSES]
        status = col_a.selectbox("Estado", options, index=options.index("postulada"), format_func=_status_label)
        applied_on = col_b.date_input("Fecha de envío", value=tracking.today(), format="DD/MM/YYYY")
        if st.form_submit_button("Registrar", type="primary"):
            if not role.strip():
                st.warning("Escribe el cargo.")
            else:
                tracking.create_application(
                    username, role=role, company=company, platform=platform, url=url, status=status,
                    applied_on=applied_on if status in APPLIED_STATUSES else None,
                )
                st.rerun()


def _render_application(username: str, a: Application) -> None:
    date_text = a.applied_on.strftime("%d/%m/%Y") if a.applied_on else a.created_at.strftime("%d/%m/%Y")
    title = f"{_status_label(a.status)} · **{md(a.role)}** — {md(a.company or 'sin empresa')} · {md(a.platform or 'sin plataforma')} · {date_text}"
    if a.match_score is not None:
        title += f" · {a.match_score}/100"
    with st.expander(title):
        if a.next_action_on and a.status in ACTIVE_STATUSES:
            st.caption(f":material/alarm: {a.next_action_on.strftime('%d/%m/%Y')}: {md(a.next_action or 'seguimiento')}")

        with st.form(f"track_status_{a.id}"):
            col_s, col_n = st.columns([1, 2])
            new_status = col_s.selectbox("Estado", list(STATUSES), index=list(STATUSES).index(a.status),
                                         format_func=_status_label, key=f"track_st_{a.id}")
            note = col_n.text_input("Nota (opcional)", key=f"track_note_{a.id}",
                                    placeholder="Ej.: me llamaron de RRHH, entrevista el jueves")
            if st.form_submit_button("Guardar"):
                if new_status != a.status:
                    tracking.change_status(username, a.id, new_status, note)
                elif note.strip():
                    tracking.add_note(username, a.id, note)
                st.rerun()

        if a.cvs:
            st.markdown("**CV enviados y generados**")
            for cv in reversed(a.cvs):
                intact = tracking.verify_cv(cv)
                sent = f"enviado el {cv.sent_at.strftime('%d/%m/%Y')}" if cv.sent_at else "no enviado"
                st.caption(
                    f"CV #{cv.id} · {cv.created_at.strftime('%d/%m/%Y %H:%M')} · {sent} · huella `{cv.pdf_sha256[:12]}` · "
                    + (":material/verified: íntegro" if intact else ":material/error: no coincide con su huella")
                )
                col_pdf, col_docx = st.columns(2)
                col_pdf.download_button("PDF", cv.pdf, file_name=cv.filename, mime="application/pdf",
                                        key=f"track_pdf_{cv.id}", on_click="ignore", width="stretch")
                col_docx.download_button(
                    "DOCX", cv.docx, file_name=cv.filename.rsplit(".", 1)[0] + ".docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"track_docx_{cv.id}", on_click="ignore", width="stretch",
                )
            if not any(cv.sent_at for cv in a.cvs) and a.status in ("guardada", "cv_generado"):
                with st.form(f"track_send_{a.id}"):
                    st.markdown("**¿Ya la enviaste?** Elige el CV exacto que enviaste.")
                    col_cv, col_date, col_pl = st.columns(3)
                    cv_id = col_cv.selectbox("CV", [c.id for c in reversed(a.cvs)], format_func=lambda i: f"CV #{i}",
                                             key=f"track_cv_{a.id}")
                    sent_on = col_date.date_input("Fecha", value=tracking.today(), format="DD/MM/YYYY", key=f"track_sd_{a.id}")
                    platform = col_pl.selectbox("Plataforma", PLATFORMS,
                                                index=PLATFORMS.index(a.platform) if a.platform in PLATFORMS else 0,
                                                key=f"track_pl_{a.id}")
                    if st.form_submit_button(":material/send: Registrar envío", type="primary"):
                        tracking.mark_sent(username, a.id, cv_id, sent_on=sent_on, platform=platform)
                        st.rerun()

        with st.form(f"track_follow_{a.id}"):
            st.markdown("**Recordatorio**")
            col_d, col_w = st.columns([1, 2])
            default_day = a.next_action_on or (tracking.today() + timedelta(days=7))
            when = col_d.date_input("Fecha", value=default_day, format="DD/MM/YYYY", key=f"track_fd_{a.id}")
            what = col_w.text_input("¿Qué hacer?", value=a.next_action, key=f"track_fw_{a.id}",
                                    placeholder="Ej.: escribirle a la reclutadora por LinkedIn")
            col_set, col_clear = st.columns(2)
            if col_set.form_submit_button("Guardar recordatorio"):
                tracking.set_follow_up(username, a.id, when, what)
                st.rerun()
            if col_clear.form_submit_button("Quitar recordatorio"):
                tracking.set_follow_up(username, a.id, None)
                st.rerun()

        with st.form(f"track_details_{a.id}"):
            st.markdown("**Datos**")
            col_a, col_b = st.columns(2)
            contact = col_a.text_input("Contacto (reclutador, correo, teléfono)", value=a.contact, key=f"track_ct_{a.id}")
            url = col_b.text_input("Enlace", value=a.url, key=f"track_url_{a.id}")
            if st.form_submit_button("Guardar datos"):
                tracking.update_details(username, a.id, contact=contact, url=url)
                st.rerun()
        if a.url.startswith(("https://", "http://")):
            st.link_button(":material/open_in_new: Abrir la vacante", a.url)

        if a.vacancy_text and st.toggle("Ver el texto de la vacante", key=f"track_vt_{a.id}"):
            st.text(a.vacancy_text)

        st.markdown("**Historial**")
        for e in reversed(a.events):
            change = ""
            if e.kind == "estado":
                change = f"{STATUSES.get(e.from_status, ('?', ''))[0]} → {STATUSES.get(e.to_status, ('?', ''))[0]}"
            detail = " · ".join(p for p in (change, e.detail) if p)
            st.caption(f"{e.created_at.strftime('%d/%m/%Y %H:%M')} · {_EVENT_LABELS.get(e.kind, e.kind)}" + (f" · {md(detail)}" if detail else ""))

        confirm_key = f"track_del_{a.id}"
        if st.session_state.get(confirm_key):
            st.warning("¿Eliminar esta postulación con sus CV e historial? No se puede deshacer.")
            col_y, col_n = st.columns(2)
            if col_y.button("Sí, eliminar", key=f"track_del_yes_{a.id}", type="primary"):
                tracking.delete_application(username, a.id)
                st.session_state.pop(confirm_key, None)
                st.rerun()
            if col_n.button("Cancelar", key=f"track_del_no_{a.id}"):
                st.session_state.pop(confirm_key, None)
                st.rerun()
        elif st.button(":material/delete: Eliminar", key=f"track_del_btn_{a.id}"):
            st.session_state[confirm_key] = True
            st.rerun()


def render_tab_postulaciones(profile: UserProfile | None) -> None:
    st.header(":material/work_history: Mis postulaciones")
    if profile is None:
        st.info("Selecciona tu perfil en la barra lateral.")
        return
    st.markdown(
        "Cada vacante a la que aplicas, con el **CV exacto que enviaste**, su estado y lo que pasó después. "
        "Se guardan solas desde «CV inteligente»; también puedes registrar las que hiciste por fuera."
    )
    _render_summary(profile.username)
    _render_new(profile.username)

    view = st.radio("Mostrar", ["Activas", "Cerradas", "Todas"], horizontal=True, key="track_view")
    # La bandeja (por revisar) vive en su propia pestaña; aquí solo lo que ya se decidió preparar.
    closed = tuple(s for s in STATUSES if s not in ACTIVE_STATUSES and s not in TRIAGE_STATUSES)
    statuses = {"Activas": ACTIVE_STATUSES, "Cerradas": closed, "Todas": ACTIVE_STATUSES + closed}[view]
    applications = [  # lo descartado sin enviar vive en la bandeja, no aquí
        a for a in tracking.list_applications(profile.username, statuses)
        if not (a.status == "descartada" and a.applied_on is None)
    ]
    if not applications:
        st.info(
            "Aún no hay postulaciones aquí. Prepara una desde la «Bandeja de vacantes» o analiza una en "
            "«CV inteligente» y guárdala o regístrala al enviarla."
        )
    for a in applications:
        _render_application(profile.username, a)
