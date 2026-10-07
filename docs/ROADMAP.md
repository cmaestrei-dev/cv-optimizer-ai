# Roadmap y estado del proyecto

> Documento vivo. Se actualiza al terminar cada cambio relevante: qué existe, qué se hizo, qué sigue.
> Última actualización: 2026-10-07 (paso 1 de la Fase 1)

## Prioridad actual

1. **Ahora:** que la app funcione bien para 2 personas que buscan empleo con urgencia (el dueño y su pareja), de **cualquier profesión**.
2. **Futuro:** convertirla en SaaS. No se migra a React/FastAPI hasta tener un núcleo de dominio independiente de Streamlit (ver decisiones).

## Qué existe hoy

- App Streamlit pública en Streamlit Cloud, persistencia en Turso (SQLite local en desarrollo).
- Perfiles con contraseña (PBKDF2), base maestra de experiencias / habilidades / educación (guardadas como Markdown).
- Análisis de vacante (texto o imagen) y generación de CV ATS con Gemini → PDF con WeasyPrint.
- Importación de CV en PDF.
- Solo Gemini como proveedor de IA; la API key la escribe el usuario en la barra lateral.

## Fases

### Fase 0 — Seguridad e higiene (en curso)
- [x] Bloquear inclusión de archivos locales / SSRF en el PDF (`url_fetcher` que niega todo + escapado de HTML)
- [x] Impedir secuestro de perfil al "crear" un usuario existente
- [x] Botón de eliminar perfil solo con sesión iniciada en ese perfil
- [x] Escapar contenido del usuario en tarjetas HTML (educación, habilidades)
- [x] Contraseña de acceso a toda la app (`APP_ACCESS_PASSWORD`; desplegada sin ella → cerrada)
- [x] Timeouts en llamadas a Gemini; reintentos 5 → 3
- [x] Prompts honestos: se conservan los cargos reales (antes se reemplazaban por el de la vacante)
- [x] Sacar datos personales del árbol del repo; `requirements-dev.txt` separado
- [ ] **(usuario)** Configurar `APP_ACCESS_PASSWORD` en Streamlit Cloud **antes** de desplegar
- [ ] **(usuario)** Rotar token de Turso y API key de Gemini (estuvieron expuestos a la vulnerabilidad del PDF)
- [x] ~~Purgar datos personales del historial git~~ → descartado (ver decisiones)
- [x] Commit + PR
- [ ] Merge a `main` (despliegue) — **después** de configurar `APP_ACCESS_PASSWORD`
- [ ] CI en GitHub Actions (ruff + pytest)

### Fase 1 — Motor de CV (dirección aprobada el 2026-10-07)

**Paso 1 — Mejoras rápidas sobre el código actual** (rama `claude/cv-multiprofesion`)
- [x] Prompts universales (cualquier profesión): el análisis detecta `AREA` e `LANGUAGE` de la vacante y se inyectan en el prompt del CV
- [x] CV en el idioma de la vacante, con títulos de sección en ese idioma ("Habilidades" en vez de "Technical Skills")
- [x] Prompts sin invención: 8–12 viñetas según material real (antes "exactamente 12"), cifras solo si existen, sin repetir keywords artificialmente
- [x] Categorías de habilidades universales, conservando las categorías que cada perfil ya usa
- [x] API key de Gemini del servidor (`GEMINI_API_KEY`); la de la barra lateral es opcional
- [x] Descarga en DOCX además de PDF (una columna, sin tablas: legible por ATS)
- [x] Arreglos: "Extraer skills" no funcionaba tras generar; caché de skills no se invalidaba entre vacantes; la imagen de la vacante se leía vacía en el segundo intento
- [ ] Validar con vacantes reales de un perfil administrativo/operativo

**Paso 2 — Núcleo nuevo (motor por etapas)**
- [ ] Perfil maestro estructurado: logros atómicos (texto, habilidades, métricas), no Markdown
- [ ] Postgres (Neon o Supabase) + pgvector + SQLAlchemy/Alembic, migrando datos desde Turso
- [ ] Cliente de IA único compatible con OpenAI (Gemini, DeepSeek, otros) + salidas validadas con Pydantic + modelo por tarea + caché por contenido
- [ ] Etapas: entender vacante (JSON) → medir match requisito↔evidencia (ESCO + embeddings) → seleccionar logros (mochila + MMR) → redactar (solo viñetas y resumen) → verificar respaldo → render con ajuste medido a 1 página
- [ ] Puntaje de match y brechas visibles antes de generar; edición de viñetas antes de exportar
- [ ] Entrevista guiada para extraer logros con cifras reales
- [ ] Set de vacantes de prueba con métricas automáticas (evals) para comparar prompts y proveedores
- [ ] Separar núcleo de Streamlit; `pydantic-settings`; `uv` + lockfile; tipado

### Fase 2 — Seguimiento de postulaciones (tracker)
- [ ] Entidad Postulación: vacante, plataforma, estado, fechas, contacto, notas
- [ ] Estados: guardada → CV generado → postulada → en revisión → entrevista → oferta / rechazada / retirada
- [ ] Historial de eventos inmutable (trazabilidad de punta a punta)
- [ ] Copia exacta del CV enviado + hash (garantía de "CV correcto por vacante")
- [ ] Recordatorios de seguimiento

### Fase 3 — Inteligencia por plataforma (LinkedIn, Computrabajo, Magneto, elempleo)
- [ ] Captura de vacantes sin scraping masivo: extensión de navegador, JSON-LD `JobPosting`, correos de alertas
- [ ] Análisis de palabras clave / requisitos por plataforma y por rol
- [ ] Mapeo de campos y preguntas de filtro de cada plataforma
- [ ] Analítica de resultados propios (qué CV / plataforma consigue respuesta)

### Fase 4 — Descubrimiento y aplicación asistida
- [ ] Búsqueda de vacantes objetivo + puntaje de afinidad
- [ ] Cola de aprobación: el usuario aprueba cada envío
- [ ] Extensión que llena formularios en la sesión del usuario; el usuario confirma el envío

### Fase 5 — SaaS
- [ ] FastAPI + React, Postgres, cola de trabajos, almacenamiento de archivos
- [ ] Autenticación gestionada, multi-tenant, pagos
- [ ] Política de tratamiento de datos (Ley 1581 de 2012), términos, observabilidad

## Registro de decisiones

| Fecha | Decisión | Por qué |
|---|---|---|
| 2026-10-07 | Uso personal primero, SaaS después | Necesidad urgente de empleo; validar el producto con usuarios reales |
| 2026-10-07 | React + FastAPI sí, pero después de extraer el núcleo | Migrar la UI con la lógica acoplada a Streamlit solo traslada el desorden |
| 2026-10-07 | No scraping masivo de LinkedIn; captura vía extensión / JSON-LD / alertas | Los términos de LinkedIn prohíben bots y scraping; riesgo de baneo de cuentas |
| 2026-10-07 | Aplicación asistida (humano aprueba y envía), no 100% automática | Envíos irreversibles, preguntas de filtro exigen veracidad, no guardar contraseñas de terceros |
| 2026-10-07 | Conservar cargos reales en el CV; el cargo de la vacante va en el Perfil Profesional | Falsificar cargos se descubre en verificación de referencias |
| 2026-10-07 | Para el SaaS no usar el plan gratuito de Gemini ni DeepSeek sin revisar | Google puede usar datos del plan gratuito; DeepSeek almacena en China (transferencia internacional, Ley 1581) |
| 2026-10-07 | Puerta de acceso con contraseña compartida (no OAuth) | 2 usuarios; mínimo esfuerzo; se reemplaza por auth real en Fase 5 |
| 2026-10-07 | Sin prompts por profesión: un motor parametrizado por contexto ocupacional (área, idioma), taxonomía ESCO y ejemplos por familia | Infinitas profesiones; los prompts por perfil se duplican y divergen |
| 2026-10-07 | Motor por etapas: algoritmos para lo medible (match, selección, verificación, 1 página), IA solo para entender y redactar | Un prompt que hace todo no se puede controlar, medir ni verificar |
| 2026-10-07 | Postgres + pgvector en lugar de Turso (en el paso 2) | Texto completo en español, embeddings y JSON en un solo lugar; es la base que necesitará el SaaS |
| 2026-10-07 | Un cliente compatible con OpenAI para todos los proveedores | Gemini y DeepSeek exponen esa API; cambiar de IA = cambiar URL y modelo |
| 2026-10-07 | 8–12 viñetas según material real (no "exactamente 12") | Forzar un número obliga a la IA a inventar cuando hay poco material |
| 2026-10-07 | No purgar el historial git de los `.md` personales | Solo contenido de CV (sin contacto ni IDs); purgar exige force push a `main` público y GitHub mantiene accesibles los commits huérfanos por SHA |

## Próximo paso

1. Usuario: configurar `APP_ACCESS_PASSWORD` y `GEMINI_API_KEY` en Streamlit Cloud (y no fijar `PROMPT_VERSION`, o dejarlo en `v3`); rotar token de Turso + API key de Gemini.
2. Merge del PR de la Fase 0 y luego del PR del paso 1.
3. Validar el paso 1 con vacantes reales (perfil administrativo/operativo).
4. CI en GitHub Actions (ruff + pytest).
5. Paso 2 del motor: empezar por el perfil maestro estructurado + Postgres.
