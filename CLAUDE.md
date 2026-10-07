# CV Optimizer AI

App Streamlit que genera CVs ATS a medida por vacante (Gemini + WeasyPrint, SQLite local / Turso en producción). Desplegada públicamente en Streamlit Cloud; repo público.

**Antes de empezar cualquier tarea, lee `docs/ROADMAP.md`** (prioridades, fases, decisiones, próximo paso). Al terminar un cambio relevante, actualízalo: marca checkboxes, añade decisiones con su porqué y ajusta "Próximo paso".

## Comandos

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
ruff check .
streamlit run app.py
```

## Mapa

- `app.py` — entrada, inyecta `st.secrets` en `os.environ` antes de importar el resto, puerta de acceso.
- `services/` — `gemini_client.py` (prompts por versión, `PROMPT_VERSION`), `pdf_generator.py`.
- `storage/_db.py` — SQLite o Turso (cliente HTTP propio), según `TURSO_DB_URL`/`TURSO_AUTH_TOKEN`.
- `ui/` — una función `render_*` por pestaña; `profile_form.py` maneja perfiles y login.
- `models/profile.py` — `UserProfile` y hashing de contraseñas.

## Reglas de seguridad (no romper)

- PDF: `HTML(..., url_fetcher=_deny_all_url_fetcher)` siempre; nunca permitir HTML crudo del LLM ni de campos del perfil.
- Cualquier `unsafe_allow_html=True` con datos del usuario debe pasar por `html.escape`.
- Acciones destructivas o de cuenta solo si `_is_authenticated(perfil)`.
- Comparaciones de contraseñas con `hmac.compare_digest`.
- Toda llamada HTTP con `timeout`.
- Nunca versionar datos personales ni secretos (`.streamlit/secrets.toml`, `.env`, `data/`).

## Reglas de producto

- Los prompts nunca inventan: ni cargos, ni empresas, ni fechas, ni habilidades, ni métricas.
- La app debe servir para cualquier profesión, no solo TI.
