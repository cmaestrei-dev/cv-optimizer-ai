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

- `core/` — núcleo sin dependencias de UI (destino de toda la lógica nueva). `core/llm/`: cliente único compatible con OpenAI (Gemini, DeepSeek), `get_llm(task)` con `LLM_EXTRACT`/`LLM_WRITE`, `generate_structured()` (JSON validado con Pydantic + 1 corrección). `core/vacancy.py`: análisis estructurado de vacantes. `core/db.py`: motor SQLAlchemy (`DATABASE_URL` → Postgres; si no, `data/cv_core.db`), `session_scope()`, `upgrade_schema()` (Alembic). `core/engine/`: motor de CV — `matching.py` (mapa de evidencias IA + puntaje determinista), `selection.py` (mochila + MMR), `writing.py` (IA reescribe viñetas/resumen), `verification.py` (anti-invención determinista), `document.py` (CVDocument → HTML/PDF con ajuste medido a 1 página, DOCX), `pipeline.py` (`analyze`, `generate`). `core/profile/snapshot.py`: foto inmutable del perfil para el motor. `core/profile/importer.py`: importar CV/LinkedIn (extracción IA + verificación contra el PDF + plan sin duplicados); la UI está en `ui/importer.py`. `core/profile/interview.py` (entrevista: preguntas → respuestas → mejoras verificadas) y `core/profile/completion.py` (texto libre → logros, tareas típicas, detalle); UI unificada en `ui/profile_coach.py`. Las brechas de "CV inteligente" usan `split_into_achievements`. `core/profile/`: modelos, `repository.py` (consultas con verificación de dueño), `service.py` (lo que usa la UI), `legacy.py` (puente con el Markdown anterior), `migration.py`, `periods.py`.
- `app.py` — entrada, inyecta `st.secrets` en `os.environ` antes de importar el resto, puerta de acceso.
- `services/` — legado en transición hacia `core/`: `gemini_client.py` (prompts por versión, `PROMPT_VERSION`; v3 es la vigente y universal), `pdf_generator.py`, `docx_generator.py`.
- `storage/_db.py` — **legado (solo lectura para migrar)**: SQLite o Turso (cliente HTTP propio). Retirar tras confirmar la migración.
- `migrations/` — Alembic. Cambio de modelo = nueva revisión (`DATABASE_URL=sqlite:///tmp.db alembic revision --autogenerate -m ...`); el test `test_alembic_schema_matches_models` falla si falta.
- `scripts/migrate_legacy.py` — simula/aplica la migración del modelo anterior.
- `evals/` + `scripts/run_evals.py` — evaluación del motor con IA real y casos ficticios (`--providers gemini deepseek`); correrla tras cambiar prompts o el motor. No va en la CI.
- `ui/` — una función `render_*` por pestaña; `profile_form.py` maneja perfiles y login. Los resultados que deben sobrevivir reruns (CV generado, skills extraídas) van en `st.session_state`.
- `models/profile.py` — `UserProfile` y hashing de contraseñas.

## Reglas de seguridad (no romper)

- PDF: `HTML(..., url_fetcher=_deny_all_url_fetcher)` siempre; nunca permitir HTML crudo del LLM ni de campos del perfil.
- Cualquier `unsafe_allow_html=True` con datos del usuario debe pasar por `html.escape`.
- Acciones destructivas o de cuenta solo si `_is_authenticated(perfil)`.
- Comparaciones de contraseñas con `hmac.compare_digest`.
- Toda llamada HTTP con `timeout`.
- La UI nunca abre sesiones de BD: usa `core/profile/service.py` (st.rerun() es una BaseException y descartaría cambios).
- Toda consulta por id filtra también por el usuario dueño.
- Los tests nunca tocan bases reales: `tests/conftest.py` fuerza un SQLite temporal y anula Turso.
- Nunca versionar datos personales ni secretos (`.streamlit/secrets.toml`, `.env`, `data/`).

## Reglas de producto

- Los prompts nunca inventan: ni cargos, ni empresas, ni fechas, ni habilidades, ni métricas.
- La app debe servir para cualquier profesión, no solo TI.
- Todo texto que escribe la IA para el CV pasa por `core/engine/verification.py`; si no se respalda, se usa el texto del usuario. Nunca relajar esto para "mejorar" la redacción.
