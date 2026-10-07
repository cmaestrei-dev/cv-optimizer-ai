"""Mi mercado: qué piden las vacantes que guardas y qué te funciona, por portal (solo tus datos)."""

import streamlit as st

from core.profile import service
from core.tracking import service as tracking
from core.tracking.insights import MIN_FOR_TRENDS, area_breakdown, build_insights, platforms_in
from models import UserProfile


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def render_tab_mercado(profile: UserProfile | None) -> None:
    st.header(":material/insights: Mi mercado")
    if profile is None:
        st.info("Selecciona tu perfil en la barra lateral.")
        return
    st.markdown(
        "Qué piden las vacantes que analizas y qué te está funcionando, **por portal**. "
        "Se calcula solo con tus postulaciones guardadas: entre más registres (y actualices su estado), más útil es."
    )
    applications = tracking.list_applications(profile.username)
    if not applications:
        st.info("Aún no hay datos. Analiza vacantes en «CV inteligente» y guárdalas o regístralas al enviarlas.")
        return

    platform = st.selectbox("Portal", ["Todos", *platforms_in(applications)], key="market_platform")
    snap = service.snapshot(profile.username)
    insights = build_insights(applications, snap, platform=None if platform == "Todos" else platform)

    cols = st.columns(4)
    cols[0].metric("Vacantes analizadas", insights.analyzed)
    cols[1].metric("Enviadas", insights.sent)
    progressed = sum(p.progressed for p in insights.platforms)
    cols[2].metric("Avanzaron", progressed, help="Pasaron a revisión, entrevista u oferta")
    cols[3].metric("Tasa de avance", _pct(progressed / insights.sent if insights.sent else None))
    if not insights.enough_data:
        st.info(
            f":material/info: Con {insights.sent} postulación(es) enviada(s) todavía es pronto para sacar conclusiones "
            f"sobre qué funciona; desde unas {MIN_FOR_TRENDS}-10 por portal los porcentajes empiezan a decir algo. "
            "Lo que piden las vacantes sí sirve desde ya."
        )

    st.subheader("Lo que más piden")
    if insights.keywords:
        st.dataframe(
            [
                {"Palabra clave": k.keyword, "Vacantes que la piden": k.share, "Cuántas": k.vacancies,
                 "¿La tienes en tu perfil?": "Sí" if k.owned else "Te falta"}
                for k in insights.keywords
            ],
            hide_index=True, use_container_width=True,
            column_config={
                "Vacantes que la piden": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
            },
        )
        gaps = insights.top_gaps[:5]
        if gaps:
            st.caption(
                "Las más pedidas que no aparecen en tu perfil: " + ", ".join(k.keyword for k in gaps) + ". "
                "Si sí las manejas, agrégalas en «Mi experiencia»; si no, son buenas candidatas para aprender."
            )
    else:
        st.caption("Las postulaciones registradas a mano no tienen análisis; analiza vacantes para ver esto.")

    if platform == "Todos" and len(insights.platforms) > 1:
        st.subheader("Por portal")
        st.dataframe(
            [
                {"Portal": p.platform, "Guardadas": p.saved, "Enviadas": p.sent, "Avanzaron": p.progressed,
                 "Tasa de avance": p.progress_rate or 0.0, "Rechazadas": p.rejected,
                 "Compatibilidad promedio": None if p.avg_score is None else round(p.avg_score)}
                for p in insights.platforms
            ],
            hide_index=True, use_container_width=True,
            column_config={"Tasa de avance": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)},
        )

    if insights.sent:
        st.subheader("¿Una compatibilidad más alta te consigue más respuestas?")
        st.dataframe(
            [{"Compatibilidad del CV": label, "Enviadas": sent, "Avanzaron": progressed,
              "Tasa de avance": progressed / sent if sent else 0.0}
             for label, sent, progressed in insights.score_buckets],
            hide_index=True, use_container_width=True,
            column_config={"Tasa de avance": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)},
        )

    areas = area_breakdown(applications if platform == "Todos"
                           else [a for a in applications if (a.platform or "Sin plataforma") == platform])
    if len(areas) > 1:
        st.subheader("Áreas de las vacantes")
        st.dataframe([{"Área": area, "Vacantes": count} for area, count in areas.items()],
                     hide_index=True, use_container_width=True)
