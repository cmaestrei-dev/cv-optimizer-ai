# CV Optimizer AI

App Streamlit que genera CVs ATS a medida por vacante (IA multi-proveedor + WeasyPrint, SQLite local / Postgres en Neon en producción). Desplegada públicamente en Streamlit Cloud; repo público.

**Antes de empezar cualquier tarea, lee `docs/ROADMAP.md`** (prioridades, fases, decisiones, próximo paso). Al terminar un cambio relevante, actualízalo: marca checkboxes, añade decisiones con su porqué y ajusta "Próximo paso".

## Comandos

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
ruff check .
streamlit run app.py
```

## Mapa

- `core/` — núcleo sin dependencias de UI (destino de toda la lógica nueva). `core/llm/`: cliente único compatible con OpenAI (Gemini, DeepSeek), `get_llm(task)` con `LLM_EXTRACT`/`LLM_WRITE`, `generate_structured()` (JSON validado con Pydantic + 1 corrección). `core/vacancy.py`: análisis estructurado de vacantes. `core/db.py`: motor SQLAlchemy (`DATABASE_URL` → Postgres; si no, `data/cv_core.db`), `session_scope()`, `upgrade_schema()` (Alembic). `core/engine/`: motor de CV — `matching.py` (mapa de evidencias IA + puntaje determinista), `selection.py` (mochila + MMR), `writing.py` (IA reescribe viñetas/resumen), `verification.py` (anti-invención determinista), `document.py` (CVDocument → HTML/PDF con ajuste medido a 1 página, DOCX), `pipeline.py` (`analyze`, `generate`). `core/profile/snapshot.py`: foto inmutable del perfil para el motor. `core/profile/importer.py`: importar CV/LinkedIn (extracción IA + verificación contra el PDF + plan sin duplicados); la UI está en `ui/importer.py`. `core/profile/interview.py` (entrevista: preguntas → respuestas → mejoras verificadas) y `core/profile/completion.py` (texto libre → logros, tareas típicas, detalle); UI unificada en `ui/profile_coach.py`. Las brechas de "CV inteligente" usan `split_into_achievements`. `core/profile/`: modelos, `repository.py` (consultas con verificación de dueño), `service.py` (lo que usa la UI), `periods.py`.
- `core/tracking/` — fase 2: `models.py` (Application, ApplicationEvent de solo-agregar, CVDocumentRecord con PDF/DOCX + SHA-256) y `service.py` (crear, adjuntar CV, `mark_sent` solo con un CV de esa postulación, estados, notas, recordatorios, resumen). UI: `ui/tab_postulaciones.py` y la sección de seguimiento de `ui/tab_cv_inteligente.py`.
- Fase 3: `core/capture.py` (traer vacante por enlace: JobPosting o texto de la página, con protección SSRF), `core/tracking/insights.py` ("Mi mercado", determinista), `core/engine/screening.py` (preguntas de filtro verificadas); UI en `ui/tab_mercado.py` y `ui/tab_cv_inteligente.py`.
- Fase 4: `core/discovery.py` (cargos sugeridos, enlaces de búsqueda por portal, `triage` de la bandeja con detección de repetidas), `core/engine/cover.py` (mensaje al reclutador verificado), `core/capture.canonical_url` (una URL por vacante). Estados `por_revisar` / `descartada` en `core/tracking/models.py`. UI en `ui/tab_bandeja.py`; "Preparar" llena `ci_analysis` y `ci_pending_inputs` de "CV inteligente".
- `app.py` — entrada, inyecta `st.secrets` en `os.environ` antes de importar el resto. Puerta de acceso: con `DATABASE_URL` de Postgres exige `APP_ACCESS_PASSWORD`; con contraseña pero sin `DATABASE_URL` se cierra (evita datos efímeros).
- `services/` — `pdf_generator.py` (plantilla CSS, `deny_all_url_fetcher`, nombres de archivo) y `docx_generator.py`.
- `migrations/` — Alembic. Cambio de modelo = nueva revisión (`DATABASE_URL=sqlite:///tmp.db alembic revision --autogenerate -m ...`); el test `test_alembic_schema_matches_models` falla si falta.
- `evals/` + `scripts/run_evals.py` — evaluación del motor con IA real y casos ficticios (`--providers gemini deepseek`); correrla tras cambiar prompts o el motor. No va en la CI.
- `ui/` — una función `render_*` por pestaña; `profile_form.py` maneja perfiles y login. Los resultados que deben sobrevivir reruns (CV generado, skills extraídas) van en `st.session_state`. Las etiquetas de `st.tabs` son fijas (si cambian, Streamlit vuelve a la primera pestaña). Para escribir en un widget ya dibujado, guardar un valor pendiente y `st.rerun()`. Tema en `.streamlit/config.toml` (oscuro fijo, coherente con el CSS de `app.py`).
- `models/profile.py` — `UserProfile` y hashing de contraseñas.

## Reglas de seguridad (no romper)

- PDF: `HTML(..., url_fetcher=deny_all_url_fetcher)` siempre; nunca permitir HTML crudo del LLM ni de campos del perfil.
- Cualquier `unsafe_allow_html=True` con datos del usuario debe pasar por `html.escape`.
- Texto de terceros (vacantes traídas de internet, salidas de la IA) en `st.markdown`/`st.caption` pasa por `ui/text.md()` (sin enlaces, imágenes remotas ni directivas inyectadas).
- Acciones destructivas o de cuenta solo si `_is_authenticated(perfil)`.
- Comparaciones de contraseñas con `hmac.compare_digest`.
- Toda llamada HTTP con `timeout`.
- Cualquier descarga de una URL que venga del usuario pasa por `core/capture._download` (valida esquema, IP pública en cada redirección, tamaño). Riesgo residual conocido: DNS rebinding entre la validación y la conexión; mitigado por la puerta de acceso.
- La UI nunca abre sesiones de BD: usa `core/profile/service.py` (st.rerun() es una BaseException y descartaría cambios).
- Toda consulta por id filtra también por el usuario dueño.
- Los eventos de una postulación nunca se editan ni se borran (solo con la postulación completa).
- Los tests nunca tocan bases reales: `tests/conftest.py` fuerza un SQLite temporal.
- Nunca versionar datos personales ni secretos (`.streamlit/secrets.toml`, `.env`, `data/`).

## Reglas de producto

- Los prompts nunca inventan: ni cargos, ni empresas, ni fechas, ni habilidades, ni métricas.
- La app debe servir para cualquier profesión, no solo TI.
- Todo texto que escribe la IA para el CV pasa por `core/engine/verification.py`; si no se respalda, se usa el texto del usuario. Nunca relajar esto para "mejorar" la redacción.
