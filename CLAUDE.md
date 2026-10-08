# CV Optimizer AI

App Streamlit que genera CVs ATS a medida por vacante (IA multi-proveedor + WeasyPrint, SQLite local / Postgres en Neon en producción). Desplegada públicamente en Streamlit Cloud; repo público.

**Antes de empezar cualquier tarea, lee `docs/ROADMAP.md`** (prioridades, fases, decisiones, próximo paso). Al terminar un cambio relevante, actualízalo: marca checkboxes, añade decisiones con su porqué y ajusta "Próximo paso".

## Comandos

```bash
pip install -r requirements-dev.txt   # incluye requirements-api.txt (FastAPI)
pytest tests/ -q
ruff check .
streamlit run app.py
uvicorn api.main:app --reload         # API (fase 5); token local: AUTH_DEV_SECRET=... python scripts/dev_token.py ana
cd web && npm run dev                 # frontend (fase 5c), con proxy /api → :8000; npm test, npm run typecheck
python scripts/export_openapi.py web/openapi.json && (cd web && npm run api:types)   # tras cambiar la API
```

## Mapa

- `core/` — núcleo sin dependencias de UI (destino de toda la lógica nueva). `core/llm/`: cliente único compatible con OpenAI (Gemini, DeepSeek), `get_llm(task)` con `LLM_EXTRACT`/`LLM_WRITE`, `generate_structured()` (JSON validado con Pydantic + 1 corrección). `core/vacancy.py`: análisis estructurado de vacantes. `core/db.py`: motor SQLAlchemy (`DATABASE_URL` → Postgres; si no, `data/cv_core.db`), `session_scope()`, `upgrade_schema()` (Alembic). `core/engine/`: motor de CV — `matching.py` (mapa de evidencias IA + puntaje determinista), `selection.py` (mochila + MMR), `writing.py` (IA reescribe viñetas/resumen), `verification.py` (anti-invención determinista), `document.py` (CVDocument → HTML/PDF con ajuste medido a 1 página, DOCX), `pipeline.py` (`analyze`, `generate`). `core/profile/snapshot.py`: foto inmutable del perfil para el motor. `core/profile/importer.py`: importar CV/LinkedIn (extracción IA + verificación contra el PDF + plan sin duplicados); la UI está en `ui/importer.py`. `core/profile/interview.py` (entrevista: preguntas → respuestas → mejoras verificadas) y `core/profile/completion.py` (texto libre → logros, tareas típicas, detalle); UI unificada en `ui/profile_coach.py`. Las brechas de "CV inteligente" usan `split_into_achievements`. `core/profile/`: modelos, `repository.py` (consultas con verificación de dueño), `service.py` (lo que usa la UI), `periods.py`.
- `core/tracking/` — fase 2: `models.py` (Application, ApplicationEvent de solo-agregar, CVDocumentRecord con PDF/DOCX + SHA-256) y `service.py` (crear, adjuntar CV, `mark_sent` solo con un CV de esa postulación, estados, notas, recordatorios, resumen). UI: `ui/tab_postulaciones.py` y la sección de seguimiento de `ui/tab_cv_inteligente.py`.
- Fase 3: `core/capture.py` (traer vacante por enlace: JobPosting o texto de la página, con protección SSRF), `core/tracking/insights.py` ("Mi mercado", determinista), `core/engine/screening.py` (preguntas de filtro verificadas); UI en `ui/tab_mercado.py` y `ui/tab_cv_inteligente.py`.
- Fase 4: `core/discovery.py` (cargos sugeridos, enlaces de búsqueda por portal, `triage` de la bandeja con detección de repetidas), `core/engine/cover.py` (mensaje al reclutador verificado), `core/capture.canonical_url` (una URL por vacante). Estados `por_revisar` / `descartada` en `core/tracking/models.py`. UI en `ui/tab_bandeja.py`; "Preparar" llena `ci_analysis` y `ci_pending_inputs` de "CV inteligente".
- `api/` — fase 5: FastAPI sobre los mismos servicios del núcleo (nunca lógica propia). `auth.py`: JWT del proveedor de identidad verificado con JWKS (`AUTH_JWKS_URL`/`AUTH_ISSUER`/`AUTH_AUDIENCE`, los tres obligatorios) o `AUTH_DEV_SECRET` (solo con SQLite); cada "emisor|sub" se crea como usuario `saas:…` (con contraseña local inutilizable) y `users.auth_subject`. Listas, resumen y mercado usan `list_applications(..., with_files=False)` para no traer los PDF. Dependencia `CurrentAccount` en cada ruta. `schemas.py`: contratos con validación. `routers/`: perfil, postulaciones (+ descarga de CV verificada), mercado. Las dependencias de la API van en `requirements-api.txt` (Streamlit Cloud usa `requirements.txt`).
- Fase 5b: `core/applying.py` (casos de uso de la postulación para la API: vacante, análisis con evidencias guardadas + huella del perfil, CV y versiones editadas, preguntas, mensaje, brechas), `core/jobs/` (cola en la base: `service.claim` con `SKIP LOCKED`, `handlers` "cv" y "bandeja", `worker` en hilo de la API o `python -m core.jobs.worker`), `core/usage.py` (`metered(llm, username)`: cupo diario de llamadas), `core/errors.py` (`describe(exc)` → código y mensaje seguro). Router `api/routers/engine.py`. Toda IA que use la API pasa por `metered`.
- Fase 5b.2: `core/onboarding.py` (importar PDF → trabajo "importar" con texto que se borra al terminar; aplicar una sola vez desde el resultado del servidor; completar experiencia; entrevista) y router `api/routers/assist.py`. `core/profile/links.with_scheme` normaliza enlaces sin esquema. En la API, los modelos de salida no validan (los datos guardados pueden venir de Streamlit o de importaciones).
- `web/` — fase 5c: React 19 + Vite + TypeScript estricto + React Router + TanStack Query. `src/api/client.ts` (fetch con token, errores en español, `download`, `waitForJob`, `safeHref`), `src/api/schema.d.ts` GENERADO (no editar), `src/auth/auth.tsx` (Clerk si `/api/config` entrega la llave pública; si no, `POST /dev/token`, que solo existe con `AUTH_DEV_LOGIN=1` + secreto de desarrollo, sin JWKS ni Postgres); `main.tsx` crea una caché de datos por sesión, `src/pages/*` (Perfil, Bandeja, Postulación, Postulaciones, Mercado), `src/styles.css` con los tokens de `DESIGN.md`. Enlaces de terceros solo con `safeHref`; nada de `dangerouslySetInnerHTML`. TypeScript 5.9 (openapi-typescript no funciona con TS 7).
- Fase 5d: `api/routers/profile.link_legacy` + `core/profile/service.link_legacy_profile` (vincular un perfil de Streamlit con su contraseña; la cuenta nueva vacía se borra); `api/web.py` (con `WEB_DIST` + `API_PREFIX=/api`, la API sirve la web); `GET /api/config` (llave pública de Clerk). `Dockerfile` + `deploy/cloudrun.sh` + `deploy/README.md` (Cloud Run us-east1, CPU siempre asignada, máx. 1 instancia, secretos en Secret Manager, cuenta de servicio propia; el script solo despliega `main` limpio). `core/usage` tiene también un tope global diario. `core/db.upgrade_schema` no falla si la base está en una revisión más nueva (la otra app ya migró). Streamlit oculta solo los usuarios `saas:…` (los vinculados siguen visibles con su contraseña).
- Fase 5e: `core/alerts/` — alertas de empleo por correo → bandeja. `parsing.py` (sin red: dueño por el `+código` de Delivered-To, remitente autenticado por el primer `Authentication-Results` de mx.google.com, enlaces de vacantes por patrón en forma canónica, código de confirmación de reenvío de Gmail), `mailbox.py` (IMAP, a la papelera tras leer), `service.py` (`activate`, `status`, `check` con candado y máx. una revisión por minuto, tope diario por cuenta; encola el trabajo "bandeja" con `limit_active=False`). Router `api/routers/alerts.py` (+ `/internal/alerts/check` con `ALERTS_CRON_TOKEN` para Cloud Scheduler). UI: `web/src/components/inbox/AlertsCard.tsx`.
- `app.py` — entrada, inyecta `st.secrets` en `os.environ` antes de importar el resto. Puerta de acceso: con `DATABASE_URL` de Postgres exige `APP_ACCESS_PASSWORD`; con contraseña pero sin `DATABASE_URL` se cierra (evita datos efímeros).
- `services/` — `pdf_generator.py` (plantilla CSS, `deny_all_url_fetcher`, nombres de archivo) y `docx_generator.py`.
- `migrations/` — Alembic. Cambio de modelo = nueva revisión (`DATABASE_URL=sqlite:///tmp.db alembic revision --autogenerate -m ...`); el test `test_alembic_schema_matches_models` falla si falta. **En SQLite, el modo batch recrea la tabla y borra la vieja**: `env.py` apaga las llaves foráneas solo mientras migra (si no, se borrarían en cascada los datos que cuelgan de ella). Aun así, preferir operaciones que no recrean (`add_column`, `create_index(unique=True)` en vez de restricciones únicas) y nombrar siempre restricciones e índices. `tests/test_migrations.py` sube y baja con datos.
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
- `api/limits.BodySizeLimit` corta peticiones de más de 6 MB antes de leerlas (FastAPI procesa formularios antes del token). Los endpoints que hacen trabajo síncrono pesado (PDF) son `def`, no `async def`. La salida de enlaces pasa por `core/profile/links.safe_link`.
- Con JWKS se exige `AUTH_AUDIENCE` o `AUTH_AUTHORIZED_PARTIES` (Clerk: `azp` = origen de la web). En Cloud Run (`K_SERVICE`) sin Postgres la API no arranca.
- Alertas por correo: nunca abrir un enlace del correo ni guardar sus parámetros (traen tokens de inicio de sesión y de «darse de baja»); aceptar solo remitentes autenticados según el primer `Authentication-Results`; no registrar en los logs direcciones, tokens ni contenido de los correos; los correos se borran tras leerlos.
- Vincular un perfil viejo responde siempre el mismo error (no revelar si existe o tiene contraseña) y cuenta el intento antes de verificar.
- La API no arranca con una `DATABASE_URL` de Postgres sin `AUTH_JWKS_URL` (protege producción de un `uvicorn` local con el `.env` real). El trabajador de la cola no sondea la base en reposo (Neon debe poder dormirse).
- Las cuentas del SaaS (`auth_subject` no vacío) nunca se listan en Streamlit: allí un perfil sin contraseña se abre sin pedirla.
- La API nunca acepta tokens sin verificar firma, emisor y vencimiento; el secreto de desarrollo no funciona con Postgres. En la API, `NotFoundError` responde 404 igual exista o no el recurso en otra cuenta.
- Los eventos de una postulación nunca se editan ni se borran (solo con la postulación completa).
- Los tests nunca tocan bases reales: `tests/conftest.py` fuerza un SQLite temporal.
- Nunca versionar datos personales ni secretos (`.streamlit/secrets.toml`, `.env`, `data/`).

## Reglas de producto

- Los prompts nunca inventan: ni cargos, ni empresas, ni fechas, ni habilidades, ni métricas.
- La app debe servir para cualquier profesión, no solo TI.
- Todo texto que escribe la IA para el CV pasa por `core/engine/verification.py`; si no se respalda, se usa el texto del usuario. Nunca relajar esto para "mejorar" la redacción.
