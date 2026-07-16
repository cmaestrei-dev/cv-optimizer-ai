import logging
import os as _os

import streamlit as st

try:
    for _key in ("TURSO_DB_URL", "TURSO_AUTH_TOKEN", "GEMINI_API_KEY"):
        if _key in st.secrets:
            _os.environ[_key] = str(st.secrets[_key])
except Exception:
    pass

from services.gemini_client import GeminiClient
from ui.profile_form import render_profile_sidebar
from ui.tab_educacion import render_tab_educacion
from ui.tab_experiencia import render_tab_experiencia
from ui.tab_habilidades import render_tab_habilidades
from ui.tab_vacante import render_tab_vacante

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


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

    with st.sidebar:
        st.header("Configuración")
        gemini_api_key = st.text_input(
            "Ingresa tu API Key de Gemini",
            type="password",
            help="Puedes obtener tu API Key en https://aistudio.google.com/app/apikey",
            key="api_key_input",
        )
        if gemini_api_key:
            st.success("API Key guardada.")
        else:
            st.warning("Por favor, ingresa tu API Key de Gemini para continuar.")

    profile = render_profile_sidebar()

    client = GeminiClient(api_key=gemini_api_key.strip()) if gemini_api_key else None

    tab1, tab2, tab3, tab4 = st.tabs([
        ":material/inbox: Vacante y Generar CV",
        ":material/description: Registrar Experiencia",
        ":material/build: Gestionar Habilidades",
        ":material/school: Educación y Certificados",
    ])

    with tab1:
        render_tab_vacante(client, profile)

    with tab2:
        render_tab_experiencia(client, profile)

    with tab3:
        render_tab_habilidades(profile)

    with tab4:
        render_tab_educacion(profile)


if __name__ == "__main__":
    main()
