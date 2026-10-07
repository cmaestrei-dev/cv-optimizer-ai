import hmac
import logging
import os as _os
import time

import streamlit as st

# Los secretos de Streamlit Cloud pasan a variables de entorno ANTES de importar módulos que las leen.
try:
    for _key, _value in st.secrets.items():
        if isinstance(_value, str | int | float | bool):
            _os.environ[_key] = str(_value)
except Exception:
    pass

from core.db import database_url
from core.profile import service as profile_service
from ui.profile_form import render_profile_sidebar
from ui.tab_bandeja import inbox_count, render_tab_bandeja
from ui.tab_cv_inteligente import render_tab_cv_inteligente
from ui.tab_educacion import render_tab_educacion
from ui.tab_experiencia import render_tab_experiencia
from ui.tab_habilidades import render_tab_habilidades
from ui.tab_mercado import render_tab_mercado
from ui.tab_postulaciones import due_count, render_tab_postulaciones

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _uses_production_db() -> bool:
    return database_url().startswith("postgresql")


def _has_app_access() -> bool:
    """Puerta de acceso a toda la app. Con la base de producción (Postgres) y sin contraseña => cerrada."""
    expected = _os.environ.get("APP_ACCESS_PASSWORD", "")
    if not expected:
        if _uses_production_db():
            st.error(
                "La app está desplegada sin contraseña de acceso. "
                "Configura el secreto APP_ACCESS_PASSWORD en Streamlit Cloud."
            )
            return False
        return True
    if st.session_state.get("app_access_granted"):
        return True

    with st.form("app_access_form"):
        password = st.text_input("Contraseña de acceso", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            if hmac.compare_digest(password.encode(), expected.encode()):
                st.session_state["app_access_granted"] = True
                st.rerun()
            time.sleep(1)
            st.error("Contraseña incorrecta.")
    return False


def _ensure_profile_store() -> bool:
    """Aplica migraciones de esquema. Desplegada con contraseña pero sin DATABASE_URL => cerrada."""
    if _os.environ.get("APP_ACCESS_PASSWORD") and not _uses_production_db():
        st.error(
            "Falta el secreto DATABASE_URL (Postgres de Neon). Sin él, los perfiles se guardarían "
            "en un archivo temporal que se borra al reiniciar la app."
        )
        return False
    try:
        profile_service.ensure_ready()
    except Exception:
        logger.exception("No se pudo preparar la base de datos")
        st.error("No se pudo conectar con la base de datos. Revisa DATABASE_URL e inténtalo de nuevo.")
        return False
    return True


def main():
    st.set_page_config(
        page_title="CV Optimizer AI",
        page_icon=None,
        layout="centered",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

        :root {
            --color-canvas: #0d1117;
            --color-surface: #151b24;
            --color-text: #c9d1d9;
            --color-accent: #58a6ff;
            --color-muted: rgba(201,209,217,0.6);
            --color-border: rgba(201,209,217,0.08);
            --radius-sm: 4px;
            --radius-md: 8px;
            --transition-fast: 150ms ease;
        }
        .stApp {
            background-color: var(--color-canvas);
            color: var(--color-text);
            font-family: 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
        }
        .stApp [data-testid="stHeader"] {
            background-color: var(--color-canvas);
        }
        .stApp [data-testid="stSidebar"] {
            background-color: var(--color-surface);
            border-right: 1px solid var(--color-border);
        }
        .stApp [data-testid="stSidebar"] h2,
        .stApp [data-testid="stSidebar"] h3 {
            color: #63b0ff;
        }
        .stApp [data-testid="stTextInput"] > div > input,
        .stApp [data-testid="stPasswordInput"] > div > input {
            background-color: var(--color-canvas);
            color: var(--color-text);
            border-radius: var(--radius-sm);
            transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
        }
        .stApp [data-testid="stTextInput"] > div > input:focus,
        .stApp [data-testid="stPasswordInput"] > div > input:focus {
            border-color: var(--color-accent);
            box-shadow: 0 0 0 2px rgba(88,166,255,0.25);
        }
        .stApp [data-testid="stMarkdownContainer"] h1 {
            color: var(--color-accent);
            text-align: center;
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        .stApp [data-testid="stMarkdownContainer"] h2 {
            color: var(--color-accent);
            font-weight: 600;
            margin-top: 2rem;
        }
        .stApp [data-testid="stMarkdownContainer"] h3 {
            margin-top: 1.5rem;
            font-weight: 600;
        }
        .stApp hr {
            border-color: var(--color-border);
            margin: 2rem 0;
        }
        .stApp [data-testid="stDivider"] {
            border-color: var(--color-border);
        }
        .stApp button {
            transition: filter var(--transition-fast), box-shadow var(--transition-fast);
        }
        .stApp button:hover {
            filter: brightness(1.12);
        }
        .stApp button[kind="primary"] {
            font-weight: 600;
        }
        .stApp [data-testid="stExpander"] {
            border: 1px solid var(--color-border);
            border-radius: var(--radius-md);
        }
        .stApp [data-testid="stExpander"] summary {
            font-weight: 500;
        }
        .stApp [data-testid="stTabs"] button {
            transition: color var(--transition-fast), border-color var(--transition-fast);
        }
        .stApp [data-testid="stProgressBarTrack"] {
            background-color: rgba(201,209,217,0.12);
        }
        .stApp [data-testid="stProgressBarTrack"] > div {
            background-color: var(--color-accent);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("CV Optimizer AI")

    if not _has_app_access() or not _ensure_profile_store():
        return

    with st.sidebar:
        st.header("Configuración")

        if _uses_production_db():
            st.success(":material/cloud_done:  Postgres (nube) — datos persisten")
        else:
            st.warning(":material/folder_data:  SQLite local — solo para desarrollo")

        server_api_key = _os.environ.get("GEMINI_API_KEY", "").strip()
        if server_api_key:
            st.caption("Usando la API Key de Gemini configurada en el servidor.")
            user_api_key = st.text_input(
                "Usar otra API Key de Gemini (opcional)",
                type="password",
                key="api_key_input",
            )
        else:
            user_api_key = st.text_input(
                "Ingresa tu API Key de Gemini",
                type="password",
                help="Puedes obtener tu API Key en https://aistudio.google.com/app/apikey",
                key="api_key_input",
            )
            if not user_api_key:
                st.warning("Por favor, ingresa tu API Key de Gemini para continuar.")

    profile = render_profile_sidebar()

    # Los contadores van fuera de las pestañas: si la etiqueta de una pestaña cambia, Streamlit vuelve a
    # la primera (p. ej. al descartar una vacante en la bandeja).
    due, inbox = due_count(profile), inbox_count(profile)
    pending = [
        f":material/inbox: {inbox} vacante(s) por revisar en la bandeja" if inbox else "",
        f":material/alarm: {due} seguimiento(s) para hoy en «Mis postulaciones»" if due else "",
    ]
    notice = st.container()  # siempre presente: si aparece/desaparece, las pestañas cambian de posición y se reinician
    if any(pending):
        notice.caption(" · ".join(p for p in pending if p))
    tab0, tab_inbox, tab_track, tab_market, tab2, tab3, tab4 = st.tabs([
        ":material/auto_awesome: CV inteligente",
        ":material/inbox: Bandeja de vacantes",
        ":material/work_history: Mis postulaciones",
        ":material/insights: Mi mercado",
        ":material/description: Mi experiencia (importar CV)",
        ":material/build: Gestionar Habilidades",
        ":material/school: Educación y Certificados",
    ])

    overrides = {"gemini": user_api_key.strip()} if user_api_key.strip() else {}
    with tab0:
        render_tab_cv_inteligente(profile, overrides)

    with tab_inbox:
        render_tab_bandeja(profile, overrides)

    with tab_track:
        render_tab_postulaciones(profile)

    with tab_market:
        render_tab_mercado(profile)

    with tab2:
        render_tab_experiencia(profile, overrides)

    with tab3:
        render_tab_habilidades(profile)

    with tab4:
        render_tab_educacion(profile)


if __name__ == "__main__":
    main()
