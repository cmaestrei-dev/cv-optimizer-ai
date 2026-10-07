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

import storage
from core.db import database_url
from core.profile import service as profile_service
from services.gemini_client import GeminiClient
from ui.profile_form import render_profile_sidebar
from ui.tab_cv_inteligente import render_tab_cv_inteligente
from ui.tab_educacion import render_tab_educacion
from ui.tab_experiencia import render_tab_experiencia
from ui.tab_habilidades import render_tab_habilidades
from ui.tab_vacante import render_tab_vacante

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _has_app_access() -> bool:
    """Puerta de acceso a toda la app. Desplegada (Turso) sin contraseña => cerrada."""
    expected = _os.environ.get("APP_ACCESS_PASSWORD", "")
    if not expected:
        if _os.environ.get("TURSO_DB_URL"):
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
    """Prepara la base del perfil estructurado y migra (una sola vez) los datos del modelo anterior."""
    if _os.environ.get("TURSO_DB_URL") and not _os.environ.get("DATABASE_URL"):
        st.error(
            "Falta el secreto DATABASE_URL (Postgres de Neon). Sin él, los perfiles se guardarían "
            "en un archivo temporal que se borra al reiniciar la app."
        )
        return False
    # A Postgres solo se migra desde Turso (los datos de producción). Si alguien corre la app en
    # local con la DATABASE_URL de producción, su SQLite local (más viejo) no debe colarse.
    legacy_is_turso = bool(_os.environ.get("TURSO_DB_URL") and _os.environ.get("TURSO_AUTH_TOKEN"))
    migrate_legacy = legacy_is_turso or not database_url().startswith("postgresql")
    try:
        reports = profile_service.ensure_ready(
            storage.list_profiles, storage.export_profile_rows, migrate_legacy=migrate_legacy
        )
    except Exception:
        logger.exception("No se pudo preparar la base de datos del perfil")
        st.error("No se pudo conectar con la base de datos. Revisa DATABASE_URL e inténtalo de nuevo.")
        return False
    migrated = [r for r in reports if not r.skipped]
    if migrated:
        st.toast(f"Se migraron {len(migrated)} perfil(es) al nuevo modelo de datos.")
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
        .stApp .stProgress > div > div {
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

        if database_url().startswith("postgresql"):
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
        gemini_api_key = user_api_key.strip() or server_api_key

    profile = render_profile_sidebar()

    client = GeminiClient(api_key=gemini_api_key.strip()) if gemini_api_key else None

    tab0, tab1, tab2, tab3, tab4 = st.tabs([
        ":material/auto_awesome: CV inteligente (nuevo)",
        ":material/inbox: Generador clásico",
        ":material/description: Mi experiencia (importar CV)",
        ":material/build: Gestionar Habilidades",
        ":material/school: Educación y Certificados",
    ])

    overrides = {"gemini": user_api_key.strip()} if user_api_key.strip() else {}
    with tab0:
        render_tab_cv_inteligente(profile, overrides)

    with tab1:
        render_tab_vacante(client, profile)

    with tab2:
        render_tab_experiencia(client, profile, overrides)

    with tab3:
        render_tab_habilidades(profile)

    with tab4:
        render_tab_educacion(profile)


if __name__ == "__main__":
    main()
