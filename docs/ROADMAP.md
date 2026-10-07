# Roadmap y estado del proyecto

> Documento vivo. Se actualiza al terminar cada cambio relevante: qué existe, qué se hizo, qué sigue.
> Última actualización: 2026-10-07 (fase 3: inteligencia por plataforma)

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
- [x] **(usuario)** Configurar `APP_ACCESS_PASSWORD` en Streamlit Cloud **antes** de desplegar
- [ ] **(usuario, sin confirmar)** Rotar token de Turso y API key de Gemini (estuvieron expuestos a la vulnerabilidad del PDF)
- [x] ~~Purgar datos personales del historial git~~ → descartado (ver decisiones)
- [x] Commit + PR
- [x] Merge a `main` y despliegue (PR #1)
- [x] CI en GitHub Actions (ruff + pytest) — entrega 2a

### Fase 1 — Motor de CV (dirección aprobada el 2026-10-07)

**Paso 1 — Mejoras rápidas sobre el código actual** (PR #2, fusionado y desplegado)
- [x] Prompts universales (cualquier profesión): el análisis detecta `AREA` e `LANGUAGE` de la vacante y se inyectan en el prompt del CV
- [x] CV en el idioma de la vacante, con títulos de sección en ese idioma ("Habilidades" en vez de "Technical Skills")
- [x] Prompts sin invención: 8–12 viñetas según material real (antes "exactamente 12"), cifras solo si existen, sin repetir keywords artificialmente
- [x] Categorías de habilidades universales, conservando las categorías que cada perfil ya usa
- [x] API key de Gemini del servidor (`GEMINI_API_KEY`); la de la barra lateral es opcional
- [x] Descarga en DOCX además de PDF (una columna, sin tablas: legible por ATS)
- [x] Arreglos: "Extraer skills" no funcionaba tras generar; caché de skills no se invalidaba entre vacantes; la imagen de la vacante se leía vacía en el segundo intento
- [ ] Validar con vacantes reales de un perfil administrativo/operativo (en curso, lo hace el usuario en la app)

**Paso 2 — Núcleo nuevo (motor por etapas)**, en entregas pequeñas, cada una en su PR

*2a — Cimientos* (PR #3, fusionado)
- [x] CI en GitHub Actions
- [x] `core/llm/`: cliente único compatible con OpenAI (Gemini, DeepSeek), modelo por tarea (`LLM_EXTRACT` / `LLM_WRITE`), reintentos, timeouts, caché por contenido
- [x] `generate_structured()`: JSON validado con Pydantic + 1 intento de corrección
- [x] `core/vacancy.py`: análisis estructurado (requisitos obligatorios vs deseables, categoría, años, modalidad, keywords) con puente al formato actual
- [x] Prueba real contra Gemini (2,3 s) y DeepSeek (8,4 s): ambos extraen bien cargo, área, años y separan obligatorios de deseables

*2b — Perfil maestro estructurado* (PR #4, fusionado; migración en producción confirmada: 5 perfiles)
- [x] Modelo de datos: usuarios, experiencias (cargo, empresa, periodo con fechas interpretadas, país, modalidad), logros atómicos, habilidades (sin duplicados ignorando mayúsculas/tildes), educación
- [x] SQLAlchemy + Alembic sobre SQLite (local/tests) y Postgres (producción); probado contra Postgres real
- [x] Capa de servicio (`core/profile/service.py`): cada operación con su propia transacción y verificación de dueño
- [x] Migración determinista y única desde el modelo anterior al arrancar la app (las tablas viejas quedan como respaldo); probada con datos reales: 38/38 logros idénticos, 100% de fechas interpretadas
- [x] Pestañas de perfil, experiencia, habilidades, educación y vacante sobre el modelo nuevo; logros editables uno por uno; "Guardar tal cual" sin IA
- [x] La app se niega a arrancar desplegada sin `DATABASE_URL` (evita guardar en un archivo temporal)
- [x] **(usuario)** Poner `DATABASE_URL` de Neon en los secretos de Streamlit Cloud antes del merge
- [ ] Retirar Turso y `storage/` cuando la migración en producción esté confirmada

*2c — Motor de CV* (PR #5, fusionado)
- [x] Match requisito ↔ evidencia: la IA propone qué logro/habilidad/estudio respalda cada requisito (y cada función del cargo); el código valida las referencias, corrige años con las fechas reales y calcula el puntaje (obligatorio 1.0, deseable 0.4)
- [x] Selección determinista: siempre el cargo más reciente, ≥1 logro por cargo, mochila por líneas + diversidad (MMR) + equilibrio entre cargos; habilidades y estudios citados primero
- [x] Redacción controlada: la IA solo reescribe viñetas y resumen; cargos, empresas, fechas, estudios y habilidades salen de los datos
- [x] Verificación determinista: cifras, siglas y nombres propios deben existir en el logro original; 1 corrección y si no, texto original. Resumen no respaldado → resumen armado con datos reales
- [x] Render desde datos estructurados (todo escapado) con ajuste medido a 1 página (cuenta páginas reales del PDF y quita lo menos relevante); DOCX del mismo documento
- [x] Pestaña "CV inteligente (nuevo)": puntaje, requisitos con su evidencia, brechas, edición de viñetas antes de descargar; el generador clásico queda como respaldo
- [x] Probado de punta a punta con Gemini real (perfil administrativo ficticio): 88/100, 1 página, 0 datos inventados
- [ ] Validación con vacantes y perfiles reales de los usuarios
- [ ] Retirar el generador clásico cuando el nuevo esté validado

*2d — Extras* (PR #6 y rama `claude/motor-2d`)
- [x] Importación de CV / PDF de LinkedIn rediseñada: pasos numerados, visible cuando el perfil está vacío, la IA solo copia (JSON validado), cada logro y habilidad se verifica contra el texto del PDF, sin duplicados, guardado atómico, completa contacto vacío
- [x] Mensajes claros cuando la API key es inválida o fue revocada (incluye el formato nuevo `AQ.` de Google)
- [x] Entrevista guiada: la IA pregunta por cifras, herramientas y resultados de un cargo (empezando por el más débil); con las respuestas propone viñetas que se verifican contra el original + las respuestas; el usuario acepta una por una. Indicador "X de Y logros tienen cifras"
- [x] PDF: la plantilla CSS tenía llaves dobles (`{{ }}`) que WeasyPrint no entendía → se ignoraban los márgenes de página (75 px en vez de 48) y los guiones de las viñetas. Corregido (más espacio útil por página) con test de regresión
- [x] Evaluación del motor (`evals/`, `scripts/run_evals.py`): 3 perfiles y 5 vacantes ficticios (administrativo, desarrollo, ventas; una en inglés) con resultados esperados. Primera corrida: Gemini y DeepSeek 20/20 en match, 0 viñetas inventadas, 5/5 en una página e idioma; Gemini 7,5 s/CV vs DeepSeek 9,9 s y 1 resumen rechazado
- [x] Entrevista más visible (feedback real: la usuaria no la encontró): va primero en la pestaña y se abre sola si menos de la mitad de los logros tienen cifras; avisos tras importar y en "CV inteligente"
- [x] **Completar el perfil** (feedback real: LinkedIn deja descripciones breves → perfil pobre → CV pobre). Una sola sección "Completar y mejorar mi experiencia" con tres modos: "Cuéntame todo lo que hacías" (texto libre → logros separados), "Tareas típicas de tu cargo" (marcar lo que sí hizo + detalle), "Entrevista: agrega cifras". En "CV inteligente", cada requisito faltante tiene "Sí lo he hecho: contarlo" → logro en el empleo elegido → "Actualizar puntaje". Todo verificado contra las palabras del usuario; duplicados desmarcados. Prueba real: compatibilidad 38 → 88 tras contar una brecha
- [ ] Normalización con ESCO → **pospuesta** (ver decisiones)
- [ ] (Idea) Generar el texto de LinkedIn ("Acerca de" y experiencias) desde el perfil completo
- [x] Retirado el generador clásico, `services/gemini_client.py`, `storage/` (Turso), el puente Markdown y la migración del modelo anterior (ya ejecutada en producción). "Pulir con IA" usa el motor nuevo verificado
- [ ] **(usuario)** Borrar los secretos `TURSO_*` de Streamlit y la base de Turso (copia vieja de datos personales) cuando confirme que todo está en Neon

### Fase 2 — Seguimiento de postulaciones (tracker) (rama `claude/fase2-postulaciones`)
- [x] Postulación: cargo, empresa, plataforma, enlace, texto y análisis de la vacante (JSON, para la fase 3), puntaje, estado, fechas, contacto
- [x] Estados: guardada → CV listo → postulada → en revisión → entrevista → oferta / rechazada / retirada
- [x] Historial de eventos de solo-agregar (creada, CV generado, CV enviado, cambio de estado con nota, nota, recordatorio, datos)
- [x] Copia exacta de cada CV (PDF + DOCX) con huella SHA-256; "Ya la envié" solo acepta un CV generado para esa misma vacante; verificación de integridad al mostrarlo
- [x] Recordatorios en la app: seguimiento a 7 días al enviar, "Para hacer hoy", contador en la pestaña
- [x] Integración con "CV inteligente": guardar la vacante, registrar el CV (guardado o enviado), detectar versiones editadas
- [x] Registrar postulaciones hechas por fuera de la app; métricas (enviadas, en proceso, ofertas, tasa de respuesta)
- [ ] Recordatorios fuera de la app (correo / WhatsApp) — requiere un servicio de envío; evaluar en la fase 5

### Fase 3 — Inteligencia por plataforma (LinkedIn, Computrabajo, Magneto, elempleo) (rama `claude/fase3-mercado`)
- [x] Captura de vacantes por enlace (una página que el usuario pide, no scraping masivo): schema.org `JobPosting` en LinkedIn público, elempleo y Magneto; texto de `<main>` en Computrabajo (verificado en los 4 portales el 2026-10-07). Portal y enlace se guardan solos en la postulación
- [x] Protección SSRF: solo http(s), cada salto de redirección se valida, se rechazan IPs privadas/loopback/link-local/reservadas, límite de tamaño y tiempo
- [x] "Mi mercado": palabras clave más pedidas (marcando si están en el perfil), por portal (guardadas, enviadas, tasa de avance, compatibilidad promedio), ¿más compatibilidad = más respuestas?, áreas; aviso honesto con pocos datos
- [x] Preguntas de filtro de los portales: respuestas con datos del perfil (años sumados con las fechas reales), verificadas; lo que solo sabe la persona (salario, disponibilidad, licencia) se marca para que lo complete
- [ ] Extensión de navegador para capturar con un clic y correos de alertas → requieren una API (fase 5)
- [ ] Guías por portal (qué campos del perfil del portal pesan más) → necesita datos reales de resultados; reevaluar con 20+ postulaciones por portal

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
| 2026-10-07 | Salida estructurada con JSON simple (`json_object`) + esquema en el prompt + validación Pydantic, no `json_schema` | DeepSeek solo soporta `json_object`; así el mismo código sirve para todos los proveedores |
| 2026-10-07 | Configuración de IA por variables `LLM_EXTRACT` / `LLM_WRITE` (`proveedor:modelo`), sin `pydantic-settings` | Una dependencia menos; lectura perezosa evita depender del orden de importación |
| 2026-10-07 | Postgres en Neon (recomendado sobre Supabase) | El plan gratuito de Neon escala a cero sin pausar el proyecto; Supabase pausa tras 7 días sin uso |
| 2026-10-07 | Base nueva separada de Turso; migración automática una sola vez (marca en `app_meta`) y tablas viejas como respaldo | Siempre hay vuelta atrás; un perfil borrado no "resucita" en el siguiente arranque |
| 2026-10-07 | A Postgres solo se migra automáticamente desde Turso (producción); el SQLite local solo a un SQLite local | Correr la app en local con la `DATABASE_URL` de producción no debe colar datos viejos ni marcar la migración como hecha |
| 2026-10-07 | La UI nunca mantiene una sesión de BD abierta: capa de servicio con una transacción por operación | `st.rerun()` lanza una `BaseException` que descartaría los cambios en silencio dentro de una sesión |
| 2026-10-07 | Columnas de texto libre sin límite de longitud | Postgres rechaza textos más largos que la columna; SQLite no, y los tests no lo detectarían |
| 2026-10-07 | No usar el CLI/MCP de Neon (`neon deploy`, `neon.ts`) | Solo se necesita la cadena de conexión; el despliegue es Streamlit Cloud |
| 2026-10-07 | Cobertura de requisitos con un "mapa de evidencias" de la IA (validado por código), no con embeddings | Decidir si una evidencia cumple un requisito exige razonamiento; los umbrales de similitud no sirven para eso. Además explica qué logro cubre cada requisito y no requiere otra API ni vectores |
| 2026-10-07 | Las funciones del cargo suman relevancia a los logros pero no puntaje | El puntaje debe reflejar requisitos (lo que filtra un reclutador); las funciones ayudan a elegir qué contar |
| 2026-10-07 | El HTML del CV se arma desde datos estructurados, nunca desde Markdown de la IA | Elimina por diseño la inyección de HTML y permite medir/recortar por elemento |
| 2026-10-07 | Generador nuevo en pestaña aparte; el clásico se mantiene hasta validar | Los usuarios están postulando ya; cero riesgo de romper lo que funciona |
| 2026-10-07 | Importar CV: la IA extrae y el código verifica contra el texto del PDF; lo no encontrado se descarta y se muestra | Un importador que "infiere" habilidades llenaría el perfil de cosas falsas que luego el motor usaría como verdad |
| 2026-10-07 | ESCO pospuesto | El mapa de evidencias ya resuelve sinónimos del oficio (100 % de acierto en los evals); ESCO aporta sobre todo a escala (SaaS: normalizar miles de perfiles, sugerir habilidades por ocupación). Reevaluar si los evals muestran fallos de sinónimos o en la Fase 5 |
| 2026-10-07 | Evals con casos ficticios y expectativas por palabra clave, fuera de la CI | Miden calidad real con IA real (cuesta cuota); la CI solo prueba las métricas. Son la base para elegir proveedor del SaaS con datos |
| 2026-10-07 | Tareas típicas generadas por IA solo como recordatorio: la persona marca lo que hizo | Reconocer es más fácil que recordar; la confirmación explícita mantiene la honestidad (nada entra sin que la persona lo marque) |
| 2026-10-07 | Los CV (PDF/DOCX) se guardan en Postgres junto a su huella | ~60 KB por CV: miles caben en el plan gratuito; una sola fuente de verdad y respaldos simples. Pasar a almacenamiento de objetos (S3/R2) si crece en la fase 5 |
| 2026-10-07 | Una postulación por vacante analizada; cada CV generado se adjunta a ella | Evita duplicados y permite ver todas las versiones; solo un CV de esa misma vacante puede marcarse como enviado |
| 2026-10-07 | Captura por enlace con `JobPosting` (schema.org) + respaldo de texto visible, en vez de scraping | Es lo que los portales publican para Google Empleos; una lectura por petición del usuario. No hay inicio de sesión ni recorrido de listados |
| 2026-10-07 | "Mi mercado" en tablas con barras en la celda, no gráficos de colores | Pocos datos personales y varias medidas por portal: una tabla es legible con 3 o 300 filas, trae la vista de tabla y no depende del color |
| 2026-10-07 | Retirar el código legado (generador clásico, cliente Gemini nativo, Turso) | El motor nuevo cubre todo y es más seguro (verificación); mantener dos caminos duplicaba el trabajo de cada cambio |
| 2026-10-07 | No purgar el historial git de los `.md` personales | Solo contenido de CV (sin contacto ni IDs); purgar exige force push a `main` público y GitHub mantiene accesibles los commits huérfanos por SHA |

## Próximo paso

1. Usuarios: usar "Traer" con enlaces reales, registrar postulaciones y estados; revisar "Mi mercado" tras ~10 envíos.
3. Fase 4 — descubrimiento y aplicación asistida: buscar vacantes objetivo y puntuarlas; cola de aprobación; la persona confirma cada envío.
4. Fase 5 — SaaS (FastAPI + React, extensión de navegador, auth gestionada, pagos, Ley 1581).
