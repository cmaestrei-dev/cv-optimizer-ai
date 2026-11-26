# Roadmap y estado del proyecto

> Documento vivo. Se actualiza al terminar cada cambio relevante: qué existe, qué se hizo, qué sigue.
> Última actualización: 2026-11-16 (cambio de rumbo: búsqueda automática para el dueño; rediseño de la web)

## Prioridad actual

**Cambio de rumbo (2026-11-16).** La pareja del dueño ya consiguió empleo (por contactos, no por la app). El SaaS deja de ser la meta principal. Lo que sigue: que la herramienta le consiga empleo al dueño **de forma automática**, plataforma por plataforma, empezando por LinkedIn.

1. **Ahora:** rediseño de la web (hecho en la rama `rediseno-web`); después, investigar y planear la automatización de LinkedIn con el dueño.
2. **Siempre:** el CV nunca inventa nada; cada envío queda registrado con el CV exacto.
3. **Pausado:** SaaS (5g operación, 5h cobros).

## Qué existe hoy

- App Streamlit pública en Streamlit Cloud (puerta con contraseña), Postgres en Neon (SQLite en desarrollo y tests).
- Perfil maestro estructurado (experiencias con logros, habilidades, educación) con importación de CV/LinkedIn y ayudas para completarlo.
- Motor de CV por etapas (match con evidencias, selección, redacción verificada, 1 página, PDF + DOCX); Gemini o DeepSeek.
- Bandeja de vacantes (buscar en portales, traer varias por enlace, ordenar por compatibilidad), seguimiento de postulaciones con el CV exacto enviado, "Mi mercado".
- Versión SaaS (FastAPI + React) publicada en Cloud Run con Clerk; las alertas de empleo que la persona reenvía desde su Gmail llegan solas a la bandeja.

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

### Fase 4 — Descubrimiento y aplicación asistida (rama `claude/fase4-bandeja`)
- [x] Buscar: cargos sugeridos por la IA a partir de la experiencia real (los cargos propios primero) y botones que abren la búsqueda de cada portal en el navegador de la persona, con ciudad (enlaces verificados el 2026-10-07; Magneto usa su buscador porque sus páginas por cargo solo existen para cargos populares)
- [x] Bandeja de vacantes: pegar hasta 10 enlaces de golpe → se traen, analizan y ordenan por compatibilidad, con los requisitos obligatorios que faltan y los años pedidos vs. los propios. Detecta repetidas aunque cambie el formato del enlace (LinkedIn `?currentJobId=`, enlaces con nombre, parámetros de seguimiento) y tras redirecciones, sin confundir vacantes que se distinguen por un parámetro (`?jk=`); un error en un enlace no detiene el lote, una clave de IA inválida sí
- [x] Cola de aprobación: "Preparar postulación" (recalcula el match con el perfil de hoy y la abre en "CV inteligente") o "Descartar" (recuperable). La bandeja no cuenta como postulaciones en las métricas
- [x] Aplicación asistida en "CV inteligente": mensaje para el reclutador verificado contra el perfil (si inventa, se usa uno armado con datos reales), lista "Antes de enviar en el portal" con el nombre exacto del archivo a subir y enlace a la vacante; la persona envía y marca "Ya la envié"
- [x] Arreglos de la app: tema oscuro fijo (en equipos con modo claro los botones secundarios eran ilegibles), barras de progreso con el color de acento, pestañas con etiqueta fija (cambiar el contador de la etiqueta devolvía a la primera pestaña), `use_container_width` obsoleto reemplazado, texto de vacantes escapado al mostrarlo
- [x] Probado de punta a punta con Gemini y vacantes reales de LinkedIn, Computrabajo y elempleo; migración 0003 probada en Postgres
- [ ] Extensión que llena formularios en la sesión del usuario; el usuario confirma el envío → fase 5 (requiere API)

### Fase 5 — SaaS (FastAPI + React), en entregas con su PR
La app de Streamlit sigue funcionando sobre la misma base durante toda la fase; se retira cuando la versión nueva tenga paridad.

*5a — API sobre el núcleo* (rama `claude/fase5a-api`)
- [x] FastAPI que usa los mismos servicios del núcleo (sin lógica duplicada); errores de dominio → respuestas claras; cabeceras `nosniff` y `no-store`; CORS solo para los orígenes configurados
- [x] Cuentas por token: JWT de un proveedor de identidad verificado con su JWKS (independiente del proveedor); modo de desarrollo con secreto local, prohibido con la base de producción. Cada cuenta se crea sola la primera vez (migración 0004, probada en Postgres con altas simultáneas) y queda aislada de las demás
- [x] Perfil (contacto, experiencias con logros, habilidades, educación), postulaciones (vistas, detalle, estados, notas, recordatorios, envío solo con un CV de esa postulación, resumen), descarga del CV exacto (si no coincide con su huella, no se entrega), "Mi mercado"
- [x] Las cuentas del SaaS no aparecen en Streamlit (allí un perfil sin contraseña se abre sin pedirla)
- [x] 16 pruebas de la API (tokens falsos, vencidos, de otro emisor o audiencia, `alg: none`, cabecera manipulada, JWKS con RSA, aislamiento entre cuentas en cada ruta) y prueba con servidor real
- [x] Revisión independiente aplicada: la migración 0004 en SQLite habría borrado en cascada los datos de todos los perfiles locales (ahora índice único sin recrear la tabla + `env.py` apaga las llaves foráneas mientras migra, con prueba que lo demuestra); audiencia del token obligatoria (con Google, otra app podría reutilizar el token de una persona); tokens manipulados ya no dan error 500; cuentas `saas:` con contraseña local inutilizable; las listas ya no traen los PDF de cada CV

*5b.1 — Motor por API* (rama `claude/fase5b-motor`)
- [x] Casos de uso sin interfaz (`core/applying.py`): agregar vacante por texto o enlace (con repetidas → 409 y el id existente), análisis, preparar desde la bandeja, CV, edición, preguntas de filtro, mensaje al reclutador y brechas ("Sí lo he hecho" → logros verificados)
- [x] El análisis guarda el mapa de evidencias de la IA: consultar la compatibilidad no llama a la IA (se recalcula con el perfil de hoy, descartando logros borrados) y se marca "desactualizado" cuando el perfil cambia
- [x] Cola de trabajos en la base (`core/jobs/`): bandeja por lotes y generación de CV en segundo plano, con progreso; se reanuda tras reinicios, reintenta lo que quedó colgado (máx. 3) y en Postgres reparte sin duplicar (`SKIP LOCKED`, probado con 5 trabajadores). Corre dentro de la API o aparte
- [x] CV con documento estructurado guardado: editar viñetas/resumen crea una versión nueva; el CV enviado nunca cambia
- [x] Límite diario de llamadas a la IA por cuenta (`AI_DAILY_CALLS`, 200 por defecto): se cuentan solo las exitosas; errores del proveedor no se cobran
- [x] Errores con una sola tabla (`core/errors.py`): mensajes para la persona sin detalles internos, en la API y en los trabajos
- [x] Streamlit también guarda evidencias y documentos, así lo que se postule allí queda editable en la versión nueva
- [x] Probado de punta a punta con servidor real, Gemini y vacantes reales (bandeja 3 enlaces en 14 s, CV en 5 s, edición, preguntas, mensaje, envío); migración 0005 probada en Postgres
- [x] Revisión independiente aplicada: el trabajador ya no consulta la base cada segundo (mantenía Neon despierto y gastaba su cómputo gratuito, afectando también a Streamlit): se despierta al encolar y en reposo revisa cada hora; la API no arranca con Postgres sin proveedor de identidad (un `uvicorn` local con el `.env` real habría aplicado migraciones sin fusionar a producción); Streamlit guarda la vacante releída junto con sus evidencias (antes podían quedar cruzadas); máx. 3 trabajos activos por cuenta; latido de los trabajos largos y escrituras solo del intento vigente (sin ejecuciones dobles); las ediciones de CV cuentan en el cupo; enlaces mal formados y caídas del proveedor dan 422/503 en vez de 500

*5b.1 fusionada (PR #15)*

*5b.2 — Perfil asistido por API* (rama `claude/fase5b2-perfil`)
- [x] Importar CV o PDF de LinkedIn: lectura en segundo plano (la IA copia, el código descarta lo que no está en el PDF y marca lo repetido); la persona elige qué guardar y se aplica UNA vez desde lo que leyó el servidor (nunca datos enviados por el cliente). El texto del CV se borra de la cola al terminar
- [x] Completar experiencia: texto libre → logros verificados, tareas típicas del cargo, tareas + detalle (sin detalle no se usa la IA). Nada se guarda hasta que la persona acepta
- [x] Entrevista guiada: preguntas, propuestas verificadas contra las respuestas y aceptar → reemplaza en su lugar o agrega
- [x] Enlaces sin `https://` (como los trae el PDF de LinkedIn) se normalizan; las respuestas ya no validan datos guardados (un enlace raro guardado daba error 500 al leer el perfil: encontrado con el PDF ficticio de LinkedIn y Gemini real)
- [x] Probado con servidor real y Gemini: importación de un PDF de LinkedIn (3 experiencias, 5 logros, 5 habilidades, 2 estudios), entrevista, tareas típicas y texto libre
- [x] Revisión independiente aplicada: subir el PDF ya no congela la API (se procesa en el pool de hilos); los PDF que fallaban quedaban en disco con datos personales (ahora se borran siempre, con prueba que lo demuestra); importar nunca duplica (índices repetidos o dos lecturas del mismo CV) y se guarda en la misma transacción que marca la lectura como usada; al aceptar en la entrevista el servidor vuelve a verificar contra las respuestas (antes dependía del cliente); límite global de 6 MB por petición (FastAPI lee los archivos antes de verificar el token); enlaces guardados que no son http(s) no salen hacia el frontend; los trabajos viejos se borran (lecturas de CV a los 2 días, el resto a los 30)

*5b.2 fusionada (PR #16)*

*5c — Frontend React* (rama `claude/fase5c-web`, carpeta `web/`)
- [x] Vite + React 19 + TypeScript estricto + React Router + TanStack Query; pocas dependencias, sin librería de componentes (estilos propios con los tokens de `DESIGN.md`)
- [x] Tipos generados desde la API (`web/openapi.json` → `src/api/schema.d.ts`); una prueba en Python y la CI fallan si la API cambia sin regenerarlos
- [x] Entrada de desarrollo (`POST /dev/token`, solo con secreto de desarrollo, sin JWKS y sin Postgres) mientras se elige el proveedor de identidad (5d); al salir o cambiar de cuenta se borra la caché de datos
- [x] Pantallas: Perfil (importar CV/LinkedIn con revisión, experiencias, «Completar con IA»: cuéntame, tareas típicas y entrevista; habilidades, educación, contacto), Bandeja (buscar en portales, pegar enlaces con avance en vivo, preparar/descartar), Postulación (compatibilidad con evidencias y «Sí lo he hecho», CV en segundo plano con versiones, descarga y edición, preguntas, mensaje, «Antes de enviar», «Ya la envié», seguimiento), Mis postulaciones, Mi mercado
- [x] Primero el celular (barra inferior; pestañas arriba en escritorio), enlaces de terceros solo http(s), contador de IA en el encabezado
- [x] Probado en el navegador con la API real, Gemini y vacantes reales (importar el PDF de LinkedIn ficticio, bandeja con 3 enlaces, preparar, CV, descarga, editor) en escritorio y celular; arreglos de lo visto (texto pegado, mensaje que desaparecía, contador de IA, símbolo «a medias», decimales con coma, pestañas cortadas en el celular)
- [x] CI: trabajo `web` (tipos al día, `tsc`, Vitest, build); `PRODUCT.md` y `DESIGN.md` actualizados (cualquier profesión, React)
- [x] Revisión independiente aplicada: «Ya la envié» podía registrar una versión del CV distinta de la más reciente (ahora usa la elegida o la más reciente de ese momento, con versiones distinguibles); la entrada de desarrollo exige `AUTH_DEV_LOGIN=1` explícito (un despliegue sin `DATABASE_URL` cae en SQLite y la habría dejado abierta); nombres sin letras latinas ya no comparten cuenta; contrato OpenAPI reproducible; LinkedIn sin `https://` ya no bloquea el formulario; doble toque no agrega logros dos veces; fechas sin zona tratadas como UTC; el portal de envío ya no queda en «LinkedIn» por defecto; una caché de datos por sesión

*5c fusionada (PR #17)*

*5d — Cuentas reales y despliegue*. Decisiones del dueño (2026-10-07): **Clerk** (Google y correo), **US$0** al inicio, **sin dominio** por ahora.

*5d.1* (rama `claude/fase5d-cuentas`)
- [x] La API acepta tokens de Clerk: emisor + JWKS + `azp` (origen de la web) en `AUTH_AUTHORIZED_PARTIES`; sin `azp` o de otro origen → 401
- [x] Web con Clerk (`@clerk/react` v6, textos `esMX`, colores de `DESIGN.md`) cuando la API entrega la llave pública (`/api/config`); sin ella, entrada de desarrollo. Token asíncrono por petición; caché por sesión
- [x] Vincular el perfil de Streamlit (nombre + contraseña de siempre): la cuenta nueva vacía se reemplaza por el perfil anterior con todos sus datos, en una transacción; máx. 5 intentos cada 15 min por cuenta y 10 por hora por perfil; Streamlit lo sigue mostrando (con su contraseña) durante la transición. Probado en el navegador
- [x] Un solo servicio: la API en `/api` sirve también la web (sin CORS); rutas de API inexistentes dan 404 JSON, no la web; sin acceso fuera de `web/dist`
- [x] `Dockerfile` (web compilada + API sin Streamlit, WeasyPrint con fuentes Liberation, usuario sin privilegios) y trabajo `docker` en la CI (construye, arranca y genera un PDF dentro del contenedor)
- [x] Cloud Run (`deploy/cloudrun.sh`, `deploy/README.md`): us-east1 (cerca de Neon us-east-2), CPU siempre asignada (la cola trabaja después de responder; con cobro por petición la CPU se frena), 0–1 instancias, secretos en Secret Manager, alerta de presupuesto de US$1. En Cloud Run sin Postgres el servicio no arranca
- [x] Revisión independiente aplicada: vincular responde siempre el mismo mensaje (no revela qué perfiles existen ni cuáles tienen contraseña, con tiempo igualado) y se puede re-vincular con la contraseña; el límite de intentos se cuenta antes de verificar (las peticiones simultáneas no lo saltan); los nombres se normalizan como en Streamlit; tope global de IA (`AI_GLOBAL_DAILY_CALLS`, 1000/día) porque registrarse es gratis; una base migrada por la otra app a una revisión más nueva ya no tumba el arranque; cabeceras anti-iframe y `Referrer-Policy`, recursos de la web con caché inmutable; si `/api/config` falla la web ofrece reintentar (antes mostraba la entrada de desarrollo); el script solo despliega `main` limpio y al día, fija `AUTH_AUTHORIZED_PARTIES` antes de la primera revisión y usa una cuenta de servicio que solo lee los dos secretos; `.gcloudignore`; guía: registros de Clerk restringidos a invitación durante las pruebas

*5d.1 fusionada (PR #18)*

*5d.2 — Publicar* (2026-10-08)
- [x] Clerk (app `gen_cv`, instancia de desarrollo): Google + correo; registro cerrado a los dos correos del dueño y su pareja (lista de permitidos, sin enviar invitaciones)
- [x] Google Cloud: proyecto propio, aparte del de Gemini, facturación solo ahí, alerta de presupuesto de 4000 COP (~US$1), secretos en Secret Manager pegados por el dueño sin mostrarse
- [x] Desplegado en Cloud Run (la dirección no va en el repo público; ver `deploy/README.md`) (salud, configuración, web, 401 sin sesión, cabeceras de seguridad comprobados; pantalla de Clerk en español)
- [x] `HEAD` en las rutas de la web (antes 405: un monitor de disponibilidad lo vería caído)
- [ ] (dueño) entrar con Google y vincular su perfil y el de dianita
- [ ] Retirar Streamlit cuando la versión nueva lo reemplace

*5e — Vacantes que llegan solas* (rama `claude/alertas-correo`; pedido tras la primera prueba real de la pareja, 2026-10-08)
- [x] Buzón propio de Gmail leído por IMAP (contraseña de aplicación en Secret Manager); cada cuenta tiene su dirección `buzón+código@gmail.com` y la activa en la Bandeja
- [x] La persona reenvía con un filtro de Gmail solo las alertas (LinkedIn `jobalerts-noreply`, Computrabajo, elempleo, Magneto); el código de confirmación del reenvío de Gmail aparece en la app (nunca se abre el enlace)
- [x] Solo correos con DKIM/DMARC válido del portal según el primer `Authentication-Results` (los de más abajo se pueden falsificar); de LinkedIn solo los de empleos (sus otros correos son mensajes privados)
- [x] Enlaces reconocidos por patrón y guardados en forma canónica sin parámetros (los correos traen `otpToken`, que inicia sesión, y enlaces de «darse de baja»); nunca se abre un enlace del correo
- [x] Cada vacante nueva entra al mismo trabajo "bandeja" (captura con protección SSRF + análisis medido por el cupo de IA); repetidas se ignoran; tope de 40 al día por cuenta; los correos van a la papelera apenas se leen
- [x] Revisión al abrir la bandeja (máx. una por minuto) y cada mañana a las 7:00 (Cloud Scheduler con token propio); el script de despliegue lo configura solo si existen los secretos del buzón
- [x] Comprobado desde Google Cloud: LinkedIn y Computrabajo entregan la vacante completa (JSON-LD) sin sesión
- [x] Revisión independiente aplicada:
  - `Authentication-Results` se lee resultado por resultado, sin comentarios ni comillas: antes un MAIL FROM o un `header.i` inventados podían pasar por DKIM válido.
  - La confirmación de reenvío solo se acepta de `forwarding-noreply@google.com`.
  - Las alertas son un tipo de trabajo propio: no cuentan para el límite de la persona y van después de lo que alguien espera.
  - Lo que pasa del tope, lo que llega sin experiencia registrada y lo que queda sin analizar porque se acabó el cupo de IA ahora espera, no se pierde.
  - El cupo, la espera y los trabajos se guardan en una sola transacción, y las URL que ya están en análisis no se repiten.
  - Un correo que falla se queda sin frenar a los demás y se descarta tras 3 intentos.
  - Se vacía la papelera: antes los correos quedaban 30 días con sus enlaces de inicio de sesión.
  - Vincular el perfil anterior conserva la dirección de alertas.
  - Computrabajo de otros países conserva su host.
  - Pedir una dirección nueva pide confirmación.
- [x] Desplegado (2026-10-08) con el buzón propio y la revisión de las 7:00; la revisión programada entra al buzón sin errores
- [x] Aviso en la Bandeja si llegan correos que no son alertas (señal de que Gmail reenvía todo el correo: hay que marcar «Inhabilitar el reenvío»); los avisos INFO de `core.*` ya salen al registro de Cloud Run (antes solo las advertencias), sin datos personales: de los correos ajenos a los portales no se registra ni el remitente
- [ ] (dueño y pareja) activar las alertas, confirmar el reenvío, crear el filtro y las alertas en los portales (la pareja ya lo hizo)
- [ ] Con correos reales: ajustar los lectores de Computrabajo, elempleo y Magneto (aún sin muestras reales) y acotar el filtro de Gmail y los remitentes aceptados a la dirección exacta de alertas de cada portal (el registro guarda el remitente de cada alerta; hoy se acepta cualquier dirección de esos dominios)

*5e.1 — Vigencia de las vacantes* (2026-10-08, pedido del dueño al ver vacantes de hace 40-60 días)
- [x] La captura guarda la fecha de publicación y de cierre del JobPosting (`datePosted`, `validThrough`; acepta fechas sin ceros como las de elempleo y descarta las imposibles); migración 0008
- [x] La Bandeja muestra «Publicada hace N días · cierra …», marca las de más de 30 días o por cerrar, y pone al final las que ya cerraron

*5f — Extensión de navegador*: en la página de una vacante, «Guardar» (a la bandeja) y «Llenar» (datos, CV a medida y respuestas de filtro); la persona revisa y pulsa Enviar. Primero el portal que más usen; también las páginas «Trabaja con nosotros» de las empresas. Nunca contraseñas de los portales ni envíos automáticos

*5g — Operar como SaaS*: observabilidad (errores, latencia, costo de IA por cuenta), copias de seguridad, Ley 1581 (política de tratamiento, autorización, exportar y borrar mis datos), términos, proveedor de IA de pago (sin plan gratuito)

*5h — Cobros*: planes y pasarela de pago (según si el dueño factura como persona natural o empresa); recordatorios por correo

*Rediseño de la web* (2026-11-16, rama `rediseno-web`; pedido del dueño: «se ve horrible, hazlo como quieras»)
- [x] Nuevo mundo visual «tabla de posiciones» (gráfica deportiva de día).
  - Fondo claro con verde cancha. Fuentes Barlow y Barlow Condensed, servidas desde la app y no desde Google.
  - Reemplaza el oscuro estilo GitHub de una sola columna de tarjetas.
  - La dirección queda en `.impeccable/surfaces/web-src.md`.
- [x] Bandeja:
  - Tabla de posiciones ordenada por compatibilidad, con zonas siempre acompañadas de texto: postulación (75 o más), repechaje (50 a 74), descenso (menos de 50 o cerrada).
  - Banda «Tu próxima jugada» con una sola decisión.
  - Riel lateral para traer vacantes: enlaces, alertas y portales.
- [x] Postulaciones: estadísticas como fila de la tabla de la liga, racha de los últimos 5 envíos y lista tipo calendario.
- [x] Postulación: marcador grande con su zona; requisitos y CV a la izquierda, envío y seguimiento a la derecha.
- [x] Perfil: ficha con estadísticas y la trayectoria como historial de clubes.
- [x] Mercado: tablas en el mismo estilo.
- [x] Fusionado (PR #23) y desplegado (revisión 00006, 2026-11-16).
- [x] Íconos dibujados en lugar de símbolos (✓ ✗ ↗ ×). En celular, las tablas se vuelven filas de dos líneas; sin desplazamiento horizontal en ninguna pantalla.

### Fase 7: Postulación automática (dueño), plataforma por plataforma

**LinkedIn (rama `fase7-linkedin`).** Decisiones del dueño (2026-11-16):
- Automático total: postula a todo lo que pase los filtros, sin umbral de compatibilidad.
- De 15 a 25 postulaciones al día.
- Corre en su computador, con su IP de casa y su propio perfil de navegador.

Lo que encontró la investigación (2026-11-16):
- En septiembre de 2026 LinkedIn reemplazó la búsqueda clásica por una búsqueda con IA. Eso rompió los bots abiertos (GodsScion) y, con sesión iniciada, se ignoran los filtros `f_AL`, `f_WT` y `sortBy`.
- La búsqueda pública (sin sesión) sí filtra por fecha (`f_TPR`) y por «Solicitud sencilla» (`f_AL`).
- geoId verificados: Colombia `100876405`, Bogotá `102361989`, Cartagena `106336022`.
- ~~Los botones de la «Solicitud sencilla» (`#jobs-apply-button-id`, el modal, `data-test-form-element`) sobrevivieron a los rediseños.~~ Ya no (2026-11-18): las clases y los ids de la página de la vacante son aleatorios. Se ubica todo por roles y nombres accesibles.
- LinkedIn tiene un tope diario de «Solicitud sencilla» que no publica (se reporta de unas 25 a 50).
- Las condiciones de uso (§8.2) prohíben los bots: el riesgo es la cuenta, y el dueño lo asume.

Entregas:
- [x] **E1, token del bot:**
  - Se crea y revoca desde Perfil y usa la cuenta sin contraseña.
  - Se muestra una vez y solo se guarda su SHA-256; máximo 5 activos.
  - El bot no puede crear tokens ni vincular perfiles. Migración 0009.
- [x] **E1 fusionado** (PR #24).
- [x] **E2, buscar y analizar en modo prueba** (`runner/`, `python -m runner`):
  - Configuración TOML en `~/.config/cv-optimizer-bot/` y token en un archivo 0600.
  - Las vacantes salen de la búsqueda **pública** de LinkedIn (sin sesión, con pausas de 2,5 a 5 s y como mucho 2 páginas por búsqueda). La oferta también se lee de la vista pública, así que la sesión del dueño solo se usará para postular.
  - Cada vacante va a la API con su texto y su enlace: la API usa ese texto y no la descarga (Cloud Run está en una IP de centro de datos). Luego se hace su CV y se baja el PDF.
  - Recuerda las vacantes ya vistas, excluye palabras y empresas, y cuenta el tope diario.
  - Si LinkedIn devuelve 429/999, pausa 24 h. Explica un token revocado o un perfil vacío.
  - `python -m runner entrar` abre el navegador propio (Playwright, perfil persistente en una carpeta 0700) para que el dueño inicie sesión una vez.
  - 14 pruebas, una de ellas de punta a punta contra la API de pruebas, con IA falsa y sin red.
- [x] **E2 fusionado y desplegado** (PR #25, revisión 00007).
- [x] El bot importa el perfil: `python -m runner importar Profile.pdf` sube el CV o el PDF de LinkedIn por la API y guarda solo lo nuevo. Con él se cargó el perfil del dueño.
- [x] El importador ya no duplica estudios escritos distinto: el PDF de LinkedIn añade el campo («Ingeniería de Sistemas, Ingeniería informática») o el país a la institución («Universidad de Cartagena-Colombia»).
- [x] Búsquedas con cualquier lugar por nombre («Medellín, Antioquia, Colombia»). Las exclusiones comparan palabras completas: «sr» no descarta «SRE». Las prácticas ya no se excluyen por defecto: el dueño puede hacer prácticas empresariales.
- [x] **E3, postular con «Solicitud sencilla»** (`python -m runner postular`, `runner/linkedin.py`, `runner/answers.py`):
  - Ubica todo por nombres accesibles («Solicitud sencilla», el diálogo, «Siguiente», «Revisar», «Enviar solicitud»).
  - Sube el CV de esa vacante con «Cargar currículum» (el campo de archivo no existe hasta pulsarlo), lo deja elegido y, antes de enviar, comprueba que el CV elegido sea ese. Si no, salta la vacante: LinkedIn deja elegido el último CV subido.
  - Solo llena lo obligatorio vacío: primero el banco `[respuestas]` del dueño (salario, inglés, disponibilidad, prácticas…), luego el motor de preguntas con su perfil. Años con una tecnología: redondeo hacia abajo; sin evidencia, `sin_evidencia` decide si salta o responde 0.
  - Si una pregunta obligatoria no tiene respuesta, salta la vacante: nunca responde al azar.
  - Desmarca «seguir empresa», envía y lo registra en la postulación con el CV exacto (`/sent`).
  - Tope diario y pausas al azar de 2 a 4 minutos entre envíos.
  - Se detiene ante verificaciones (`/checkpoint`, captcha, tope de LinkedIn): 24 h sin postular. El 429 de la búsqueda pública solo frena la búsqueda (6 h). Nunca resuelve captchas ni usa herramientas para ocultarse.
  - Modo prueba (`--prueba` o `modo = "prueba"`): llega a la revisión, guarda una captura y descarta sin enviar.
  - Confirmación del envío: el aviso de LinkedIn o que la vacante pase a «Postulado»; si no aparece ninguno, recarga la vacante para comprobarlo antes de dar error (el texto real del aviso aún no se ha visto).
  - Probado en modo prueba contra una vacante real (Comfama, 4 pasos): la revisión muestra el CV de la vacante y las respuestas. 5 pruebas con Playwright contra una copia local del formulario (se saltan sin Chromium).
- [x] **(dueño)** Revisó la captura de prueba y activó `modo = "auto"` (2026-11-18). También excluyó los cargos «bilingüe/bilingual» (inglés A2).
- [ ] Los primeros envíos reales, mirándolos (cuando la búsqueda pública vuelva a responder y haya preparadas).
- [ ] **E4, que corra solo:**
  - [x] `python -m runner diario`: una vuelta (buscar y luego postular) con candado para que nunca corran dos a la vez. Si la búsqueda falla, igual postula lo preparado. Al terminar avisa en el escritorio (enviadas, verificación pendiente, sesión perdida).
  - [x] `python -m runner programar [--horas …] [--quitar]`: temporizador de systemd del usuario, sin root. Por defecto a las 9:17 y 15:47; si el computador estaba apagado, corre al encender. El registro va a `registro.log`. Rechaza rutas temporales o que systemd leería mal.
  - [x] Instalado (2026-11-19) desde la copia estable `~/.local/share/cv-optimizer-bot/codigo`, a las 9:17 y 15:47, tras el primer envío real verificado (Computrabajo). La copia solo se actualiza a mano (`git pull`).
  - [ ] El primer envío real de LinkedIn aún no ocurre: la búsqueda pública devuelve 429 a la primera petición desde la IP de casa (tres días seguidos).
  - [x] **Vacantes desde la bandeja de la app** (2026-11-20): `buscar` toma primero las vacantes de LinkedIn y Computrabajo que esperan en la bandeja, que llegan ya analizadas por las alertas por correo de la fase 5e. Les aplica las mismas exclusiones, mínimo y topes; lo excluido o descartado queda «descartado» en la app con el motivo. Decisión del dueño: LinkedIn se alimenta de sus alertas, no de la búsqueda pública ni de buscar con su sesión.
  - [x] Alertas diarias en LinkedIn (2026-11-20, con el navegador del bot): 8 búsquedas solo con «Solicitud sencilla»: desarrollador (Colombia, Cartagena, Medellín, remoto), desarrollador python, desarrollador full stack, practicante desarrollo de software y ciberseguridad. «Alertas por correo» activadas en la app.
  - [x] **(dueño, 2026-11-20)** Reenvío desde Gmail: la dirección de la app quedó verificada y el filtro `from:(jobalerts-noreply@linkedin.com)` → «Reenviar a» está creado. El reenvío de todo el correo sigue inhabilitado. Google pide verificar la identidad para la dirección y para el filtro, y su ventana no se abre en el navegador del agente: el dueño lo hizo en su Chrome.
  - [x] `buscar` pide a la app revisar el buzón (`POST /alerts/check`) y espera hasta 5 min a que analice lo nuevo. Antes solo lo revisaba Cloud Scheduler a las 7:00, y una alerta de la tarde esperaba al otro día.
  - [ ] Ver la primera alerta de LinkedIn en la bandeja y su envío real.
  - [ ] Mostrar en la web lo que hizo el bot cada día.
- [ ] Después: postulaciones externas (Greenhouse, Lever…) y los otros portales.

**Computrabajo (Fase 8, rama `fase8-computrabajo`).** Decisiones del dueño (2026-11-18):
- Tope de 15 a 25 al día (se usa 20), aparte de LinkedIn.
- Compatibilidad mínima de 60: la búsqueda por «desarrollador» trae ventas («desarrollador comercial motorizado»).
- Su cuenta existe, pero la hoja de vida de Computrabajo está desactualizada.

Lo que encontró la investigación (2026-11-18):
- La búsqueda y la oferta son públicas, en HTML sin Cloudflare: `/trabajo-de-<cargo>[-en-<ciudad>|-en-remoto]?pubdate=<días>&by=publicationtime&p=<n>`, con 20 por página.
- Ciudades como `cartagena-de-indias` y `bogota-dc`. Si hay pocas en la ciudad, rellena con otras.
- La oferta trae condiciones, descripción, requisitos y aptitudes en `div-link="oferta"`, y al final unas «Palabras clave» de SEO que confunden el análisis: a un planeador de producción le ponen «developer».
- Postular exige sesión en `candidato.co.computrabajo.com` (`/match/?oi=<código>`) y usa la hoja de vida del perfil de Computrabajo.

Entregas:
- [x] **C1, buscar y preparar** (`runner/computrabajo.py`):
  - Se activa con `portal = "computrabajo"` en `[[busqueda]]`. Tope y compatibilidad mínima van en la tabla `[computrabajo]`.
  - Debajo del mínimo, la vacante queda «descartada» en la app con el motivo y sin CV (no gasta cupo de IA en CV).
  - Pausas y conteos por portal (`busqueda_computrabajo`, `preparadas_computrabajo`); el postulador de LinkedIn ignora las de Computrabajo.
  - Se detiene ante 403/429/503 o la página de verificación de Cloudflare; nunca la resuelve.
- [x] Probado con la búsqueda real (2026-11-18): 3 preparadas (79, 75 y 64) y 3 descartadas por debajo de 60 (aprendices SENA).
- [x] `python -m runner entrar computrabajo` abre su inicio de sesión en el navegador del bot. La cookie de sesión aún no se conoce: la persona cierra la ventana al terminar. No abre si el navegador del bot ya está abierto.
- [ ] **(dueño)** Actualizar la hoja de vida en Computrabajo e iniciar sesión en el navegador del bot (`entrar computrabajo`).
- [x] **C2, estudio con la sesión del dueño, sin postular (2026-11-18):**
  - «Aplicar» lleva a `/match/?oi=` y postula de inmediato; las preguntas de filtro van en `/candidate/apply-kq`, y `/candidate/apply-exists` es «ya aplicaste». No hay revisión, así que tampoco hay un modo prueba completo.
  - La ayuda oficial dice que la empresa siempre ve la **última versión** de la hoja de vida en línea, también en postulaciones viejas.
  - Del PDF adjunto la ayuda oficial no dice nada. Una guía independiente dice que «se guarda con tu postulación». Hay un máximo de 10 y uno «por defecto» que va «a mis candidaturas».
  - El dueño tenía 10 PDF de vacantes viejas y marcado «No adjuntar ninguna»: sus postulaciones salían sin PDF.
- [x] **C2, postular** (`runner/computrabajo_apply.py`):
  - Sube el CV de la vacante, lo marca por defecto y aplica. Responde las preguntas de filtro con el banco y el perfil; si alguna queda sin respuesta, no envía.
  - Confirma con el aviso o con la oferta marcada «Postulado». Luego vuelve a dejar por defecto el CV general (`cv_general`).
  - Para hacer espacio borra el PDF más viejo que subió el bot; nunca el general ni uno ajeno (`sin_espacio`).
  - 7 pruebas contra un Computrabajo falso con Playwright. Las redirecciones van con JavaScript, porque las HTTP de una respuesta simulada no pasan por la intercepción y saldrían a la red.
- [x] **(dueño)** Decidió: CV por vacante más uno general fijo; borrar sus 10 PDF viejos; el primer envío, mirándolo.
- [x] Borrar los 10 PDF viejos, subir el CV general y dejarlo por defecto (con el bot, 2026-11-19). Corrección: el PDF por defecto anterior era «Tecnólogo en Sistemas», no «No adjuntar» (se leyó mal el HTML).
- [x] **Primera vuelta automática (2026-11-20): 9 enviadas** (una ya «HdV Vista» a los 44 minutos). Dos fallas, corregidas:
  - 13 ofertas tenían preguntas de selección en `/candidate/kq`, no en `apply-kq` como decía la analítica del sitio. El texto de cada pregunta va en un campo oculto `KillerQuestions[i].Title`. Ahora el bot las lee y responde (banco y perfil verificado), o salta la vacante si una queda sin respuesta.
  - La vuelta al encender el computador arrancó antes que la sesión gráfica (`Missing X server`): ahora espera hasta 10 min a que systemd conozca la pantalla.
  - 2026-11-26: esa espera no bastaba. Playwright arranca su controlador antes de `ensure_display` y Chrome heredaba su entorno, sin pantalla (la vuelta del 25-11 a las 20:25 no envió nada). Ahora `open_context` le pasa el entorno a Chrome. Si postular falla, la vuelta igual hace el seguimiento y manda el resumen con el aviso.
  - Las pruebas de la vuelta diaria leían la configuración real en el computador del dueño: revisaron los portales, crearon una postulación en la app (la 1075, con CV), anotaron estados del seguimiento real y mandaron un Telegram. Ahora `tests/conftest.py` apunta `CVO_BOT_CONFIG_DIR` y `CVO_BOT_DATA_DIR` a carpetas temporales antes de importar `runner`, y una prueba verifica que ninguna ruta del bot cae en las reales.
  - El banco ya no responde «Inmediata» a «¿disponibilidad para trabajar presencial…?»: «disponibilidad» sola era demasiado amplia.
- [x] **Menos vacantes saltadas (#42, 2026-11-20):**
  - Preguntas de experiencia sin respaldo en el perfil («¿Tienes experiencia con Azure?», «¿Cuántos años con X?»): con `sin_evidencia = "cero"` responde «No», «0» o «Aún no tengo experiencia con eso.». Nunca inventa un «Sí».
  - Si la verificación rechaza una respuesta de la IA, la pide una vez más antes de saltar la vacante.
  - La verificación acepta palabras juntas o separadas («Full Stack» = «Fullstack»).
  - Las vacantes con error siguen «preparadas» y se reintentan en la vuelta siguiente. Las saltadas no: quedan «saltada» con sus preguntas en el estado del bot.
  - Corrección de #43: decía que las saltadas también se reintentan. Las 2 saltadas del 2026-11-20 (preguntas de nacimiento, dirección y experiencia) se devolvieron a la cola a mano tras el banco nuevo y el modo «si».
- [x] **Responder «Sí» en las preguntas de experiencia (decisión del dueño, 2026-11-20):** `sin_evidencia = "si"`. A «¿Tienes experiencia con X?» responde «Sí», aunque el perfil no lo muestre. A «¿Cuántos años con X?» responde lo que muestre el perfil, o al menos `experiencia_por_defecto` (2; en meses, ×12).
  - Con opciones de años («1 a 2 años», «3 a 5»…), elige la que contiene ese número.
  - Solo cambia las preguntas de experiencia. Patrocinio de visa, dirección y demás siguen saliendo del banco o del perfil, o la vacante se salta.
  - El CV no cambia: todo lo que escribe la IA sigue pasando por la verificación anti-invención.
- [x] **Primer envío real (2026-11-19):** Soporte Tester QA, ikatech Solutions. En la app quedó «postulada» en Computrabajo; allá aparece «Postulado» y el CV general volvió por defecto. El primer intento falló sin enviar: elegir el PDF por defecto recarga la página y `check()` de Playwright esperaba en vano. Corregido en #38.
- [x] Hoja de vida en línea igual a LinkedIn (regla del dueño: «solo lo que está en LinkedIn tal cual»):
  - titular, resumen, áreas, departamentos y situación «buscando activamente»;
  - «Información adicional» con el CV de LinkedIn; tenía un «[INSERTAR PORCENTAJE]%» olvidado;
  - las 3 experiencias de LinkedIn; se borraron dos que no estaban;
  - estudios corregidos, inglés básico, 17 conocimientos nuevos y 27 de infraestructura quitados.
- [ ] **(dueño)** Cargar su perfil (CV o PDF de LinkedIn), crear el token en la web e iniciar sesión en el navegador del bot.

**Magneto (Fase 8, 2026-11-21).** El dueño quiere todas las plataformas posibles. Magneto va primero porque una sola cuenta cubre Davivienda, Claro, Banco de Bogotá, ARUS e Indra.
- [x] Estudio con la sesión del dueño, sin postular:
  - La búsqueda pública (`/jobs/v1/public/jobs/search`, orden `_score`) entrega la oferta completa y no pide sesión.
  - La sesión (`access_token`) vence en más o menos una hora y se renueva sola al abrir `login.magneto365.com/candidates`, porque el dueño entró con Google. Él aprobó que el bot la renueve.
  - «Aplicar» es un `POST /jobs/v1/jobs/apply` sin revisión. Antes, la página consulta `verify-applications-by-dni` y, si hay cuestionario, `questionnaire/already-answered` y `questionnaire/{id}`.
  - Tipos de pregunta: 0 = una opción, 1 = varias, 2 = abierta corta (140 caracteres), 3 = abierta larga.
- [x] Perfil del dueño igual a LinkedIn. Estaba «incompleto» y Magneto no lo mostraba a las empresas.
  - Experiencias con fechas y textos de LinkedIn; se borró una freelance que no estaba y se agregó Karta.
  - Descripción de LinkedIn, 15 habilidades, idiomas, estudios, 9 certificaciones y CV adjunto.
  - Teléfono corregido: tenía el 57 repetido.
  - Su formulario no guarda las fechas ni deja borrar una experiencia incompleta, así que esas partes se hicieron con la misma petición que envía su página.
- [x] `runner/magneto.py` (búsqueda) y `runner/magneto_apply.py` (postular con la petición de la página, después de sus mismas consultas). Probados con una sesión falsa, sin red.
- [x] **Primer envío real (2026-11-21):** Desarrollador/a Cells Junior, Indra (compatibilidad 75). Quedó en «Mis procesos» de Magneto y sus postulaciones pasaron de 8 a 9.
  - La oferta no pasa a `isApplied` después de postular, así que el bot lo marcó como error.
  - Ahora confirma con «Mis procesos» (`/jobs/v2/my-processes`), que también revisa antes de enviar para nunca postular dos veces.
  - Una respuesta 2xx sin confirmación cuenta como enviada, para no repetir.

**Telegram (pedido del dueño, 2026-11-21).** Un bot propio para que le lleguen al celular las cosas que solo él puede hacer y para manejar el sistema desde ahí.
- [x] `runner/telegram.py`: long polling desde su computador, sin puertos ni webhooks.
  - Se empareja con un código de un solo uso y solo atiende ese chat.
  - El token se pide oculto y queda en un archivo 0600.
  - Comandos `/estado`, `/hoy`, `/vuelta`, `/pausar`, `/reanudar`, `/preguntas` y `/responder`.
  - Al final de cada vuelta envía el resumen y las preguntas pendientes.
  - No escribe `estado.json`: la pausa va en `control.json` y las respuestas en `respuestas_extra.json`, que `config.load` une al banco.
- [x] Las vacantes saltadas guardan su CV. Si después sus preguntas tienen respuesta, `postular` las devuelve a la cola (`_retry_answered`).
- [x] **(dueño)** Creó @SoyEmpleo_bot y lo emparejó (2026-11-21). Como no alcanzó en 10 minutos, el servicio instalado ahora espera el código sin límite de tiempo (#53).
- [x] Postulaciones manuales por Telegram (pedido del dueño): `python -m runner manual …` las agrega y las envía con su CV en PDF. `/manuales` las lista y `/hecha N` marca una como enviada (en `manuales_hechas.json`, aparte, como la pausa).

**Empresas objetivo (2026-11-21).** Revisión en vivo de la lista de empresas:
- Bancolombia: no tiene prácticas de tecnología publicadas, y sus vacantes junior de software piden título profesional.
- Ecopetrol: 0 prácticas publicadas.
- Pragma (práctica 2027-1) y Bold (IT Support, Frontend): sus formularios tienen captcha o piden la cédula, así que postula el dueño; la app le preparó el CV de cada una.
- [x] `runner/watch.py` y `[[vigilar]]`: en cada vuelta el bot revisa la búsqueda pública de portales SuccessFactors y avisa de las ofertas nuevas cuyo cargo encaja (registro y Telegram). No postula: piden una cuenta por empresa.
- [x] Bancolombia, como los demás portales (pedido del dueño, 2026-11-21):
  - Cada oferta vigilada que encaja pasa por la app: análisis, compatibilidad y, si llega a 60, su CV.
  - Le llega al dueño por Telegram con el PDF, lista para postular (máximo 5 por vuelta).
  - Postular solo no es posible: el inicio de sesión de Bancolombia pide correo, contraseña y captcha, y el portal muestra un aviso de mantenimiento («Por el momento no podrás adjuntar tu hoja de vida»).
  - `python -m runner entrar bancolombia` deja la cuenta en el navegador del bot. Si la sesión resulta durar días, se puede postular solo; eso se mide después de que el dueño entre.
- [x] Bancolombia «en lote» (2026-11-22, ver la decisión): `python -m runner lote bancolombia [--prueba]` abre el acceso, espera a que el dueño entre y postula a todo lo preparado con su CV; al final deja en el perfil el CV general.
  - El primer intento real no envió nada: el portal pidió «¿Cómo supo de este puesto?», «Detalles» y la declaración. Ahora va primero el CV (subirlo redibuja el formulario y borra lo respondido), luego una pregunta a la vez (las listas en cascada dependen de la anterior), cada valor confirmado con «change» y Tab, y solo se envía si no queda nada obligatorio vacío.
  - En el modo prueba, campos del perfil ya llenos («País de nacimiento», «Nacionalidad») se veían vacíos un momento tras cada redibujo: el bot espera a que el formulario se quede quieto y los vuelve a mirar antes de responderlos. «Mis documentos» del perfil carga cerrada: se abre antes de devolver el CV general.
  - **Primer lote real, 2026-11-22: 2 de 2 enviadas** (Backend Junior y Backend de EVC Gestión del Fraude); «Puestos solicitados» pasó de 1 a 3.
  - El bot no las pudo confirmar ni devolver el CV general porque el perfil solo abre con el código de la sesión en la dirección (`_s.crb`): el enlace directo responde «not authorized». Con sesión, el acceso lleva al perfil con ese código, así que el bot entra siempre por ahí (sobra `perfil` en la configuración). Si la devolución falla, dice en qué paso y deja una captura.

**Portales de empresas en Workday y Eightfold (2026-11-22).** Pedido del dueño («arranca con Workday y Mercado Libre»).
- [x] Estudio de portales (sin cuentas ni envíos): Get on Board tiene API pública pero unas 4 vacantes que le sirven; ticjob y Hireline casi nada; Indeed bloquea con un reto de JavaScript (no se salta). Lo que más rinde son los portales de grandes empresas.
- [x] `runner/workday.py`: búsqueda pública de Workday (`/wday/cxs/<tenant>/<sitio>/jobs`), filtrada por el país que se busca por nombre en las facetas (el id de Colombia es el mismo en todas), y la oferta con su fecha de cierre. Frena rápido (429 por host): pausas de 6 a 10 s y, si frena, ese portal espera a la próxima vuelta.
- [x] `runner/eightfold.py`: búsqueda pública de Eightfold (Mercado Libre, `/api/pcsx/search` y `position_details`), solo las del país.
- [x] `[[vigilar]] portal = "workday" | "eightfold"` con `pais` (y `dominio` en Eightfold); `buscar` es opcional. Más palabras de tecnología en inglés (backend, developer, support, security…) y exclusiones (lead, manager, expert). Hasta 10 ofertas vigiladas por vuelta.
- [x] Verificado en vivo: Mercado Libre 59 en Colombia (17 encajan), Accenture 40 (9), DXC y Kyndryl responden. Configurados Accenture, DXC, Kyndryl, Unisys y Mercado Libre. El bot no postula ahí (cada empresa pide su cuenta): llegan por Telegram con su CV.
- [x] Primera vuelta real: 41 ofertas nuevas que encajan; 1 enviada a Telegram (IT Customer Service, Accenture, 64), 2 descartadas, y 7 se gastaron en detalles de Accenture que frenaron (429). Ahora un portal que frena espera a la próxima vuelta sin gastar cupos, y el detalle de Workday lleva pausa.
- [x] `runner/boards.py`: un solo módulo para los sistemas con lista pública de ofertas, con la `cuenta` de la empresa: Recruitee (Bold, 61 en Colombia), Greenhouse (Clara, 33), Lever (Yuno, 1), Ashby (Addi, 34) y SmartRecruiters (Experian, 10); verificados en vivo con lista y detalle. Solo las del país (por nombre o código ISO). Ventas y comerciales quedan fuera por defecto.
- [x] Estudio de empresas que encajan con el dueño y tienen portal propio (2 investigaciones, ~90 empresas, sin cuentas ni envíos). Las mejores: Nequi (prácticas de TI, Buk), Softtek (Eightfold), Stefanini (≈25 de soporte y QA junior, Gupy), Periferia IT, Alegra, Siigo y Bluetab (Teamtailor), Grupo Falabella (Muévete, 197 en Colombia), Grupo Aval (Talento Aval, 88), Sonda y Promigas/Surtigas (SuccessFactors), BBVA, Rappi, Tigo e Ikusi (Workday), Sutherland y SGS (SmartRecruiters). Muchas otras solo publican en LinkedIn, Computrabajo, Magneto o elempleo (ya cubiertas).
- [x] `runner/boards.py` suma Teamtailor (`/jobs.rss`), Buk (lista + JSON-LD de la oferta), Gupy (`__NEXT_DATA__`) y Muévete (una lista de 6 MB que se baja una vez por vuelta). Verificados en vivo: Periferia IT 31 en Colombia (12 encajan), Alegra 22, Stefanini 46 (33), Nequi 9 (5 con sus prácticas de TI), Falabella 197 (11), Softtek 60 (13), Sonda 14 (4), LINQ, Ceiba, Bluetab, Siigo, Cobre.
- [x] Workday frena por conexión (429 tras unas 6 consultas entre empresas distintas): cada vuelta revisa solo 3 portales de Workday, los menos recientes, con 20 a 30 s entre uno y otro.
- [x] Postular sin la persona en Teamtailor (`runner/teamtailor_apply.py`, `postular = true`, 2026-11-22). Estudio de los formularios de postulación de cada sistema (sin enviar): Teamtailor sin cuenta ni captcha; Gupy y Workday piden cuenta (una de Gupy sirve para todas sus empresas); Greenhouse y Ashby tienen captcha invisible; Recruitee (Bold) y Lever, hCaptcha; Buk pide entrar con el correo y tiene captcha. En Teamtailor el bot llena las preguntas (texto, radios y desplegables), los datos de contacto del perfil de la app, el CV de la vacante y el consentimiento obligatorio, revisa `checkValidity` y envía; ensayado en una oferta real de Periferia IT sin enviar. Hasta 10 por vuelta; las preguntas sin respuesta van a Telegram.
- [x] Teamtailor en vivo (2026-11-22/23): 9 enviadas (Siigo 1, Bluetab 3, Periferia IT 4, Alegra 1); 6 pidieron confirmar desde el correo (aviso por Telegram). Arreglos con los formularios reales (#92–#101): campos numéricos, desplegables que se quedan abiertos, ubicación con sugerencias, etiquetas «Obligatorio», consentimiento implícito, «nivel de experiencia» en número (años), carta de motivación con el mensaje de la app (`/cover`) y sedes («Ubicaciones»). Respuestas del dueño: libreta militar «No», «Camilo (él)», condiciones actuales (prestación de servicios, remoto, 2 millones). La aspiración salarial sigue la vacante (punto medio del rango publicado; si no, 3 millones; sin cifra en prácticas). Las preguntas de IA de Alegra hablan solo de la parte de adaptar CVs de CV Optimizer y de Karta (pedido del dueño).
- [x] Gupy (Stefanini, `runner/gupy_apply.py`, 2026-11-23): `entrar gupy` en un Chrome normal (Cloudflare rechaza la ventana del bot); hoja de vida de Gupy completada con el CV general (estudios, experiencias, idiomas, datos personales, 26 habilidades); primera postulación terminada (Help Desk Analyst L1). Pasos: «Continuar» → información adicional → preguntas de la empresa → «Finalizar candidatura». Las respuestas no se pueden editar luego: con alguna sin respuesta no se guarda nada.
- [x] Gupy en vivo: 18 postulaciones confirmadas en Stefanini (2026-11-23).
- [x] AIRA / Grupo Falabella (`runner/aira_apply.py`, 2026-11-23): el dueño creó su cuenta y entró en la ventana del bot; primera postulación real (Practicante Área de Sistemas, compatibilidad 78). El formulario es Vue: el CV se sube llamando al `changedFile` de su componente (AIRA lo guarda como `resume.pdf` de esa postulación), los años son deslizadores (`handleChangeRadiosSlider`), la expectativa salarial es obligatoria (en prácticas, el apoyo usual: 1.750.000, decisión delegada) y se desmarcan «Guardar hoja de vida en mi perfil» y «Recibir alertas». Falabella pide pruebas de personalidad e inteligencia que hace la persona (valen 12 meses).
- [x] AIRA, arreglos tras la primera vuelta (2026-11-23): los deslizadores de «Nivel de conocimiento» (Ninguno…Experto, valores none…expert) se responden por su etiqueta; y AIRA guarda en la sesión del servidor la última postulación elegida y a veces abre esa (de otra vacante) con el enlace de una oferta: el bot comprueba que el cargo de «Estado postulación» sea el de la vacante (un reintento) y si no, no llena nada. Se excluyen los cargos para personas con discapacidad («inclusión», «discapacidad», «pcd»): una así se envió en la primera vuelta.
- [x] Meses que salían como años (2026-11-24): la app respondía «4 meses (Equimat)» y el bot tomaba el número como años («4 años», «7 años», «11 años» en `registro.log`; no se enviaron porque no calzaban con las opciones, pero en un campo numérico sí habrían salido). `answers.to_period` lee la unidad: en años, hacia abajo (4 meses → 0, y luego la política `sin_evidencia`); en las preguntas por meses, 1 año → 12.
- [x] LinkedIn con su diseño nuevo (2026-11-24): estaba frenado desde el 22 por un «tope» falso (siempre en la misma oferta; LinkedIn no mostraba ningún límite) y el formulario nuevo no avanzaba. Arreglos: el tope debe ser un aviso corto (y queda su texto en el registro), botón visible sin esperar navegación, diálogos apilados al descartar, radios con la pregunta en el aria-label y la opción al lado. Ensayado sin enviar en Softtek y Hitss (llegan a la revisión y se descartan). Además, una respuesta del banco que no es un número no responde una pregunta de años (la clave «practica» respondía «Sí» a «¿Cuántos años… prácticas de IaC?»).
- [x] LinkedIn: compatibilidad mínima de 50 (en la configuración local; 8 de la cola, bajo 50, descartadas en la app) y los años de experiencia que LinkedIn trae guardados se vuelven a responder (`linkedin._saved_years`); si el bot no tiene respuesta, se deja la guardada.
- [x] Seguimiento de postulaciones (`runner/seguimiento.py`, 2026-11-24, pedido del dueño: «automatiza el monitoreo»): al final de cada vuelta y con `python -m runner seguimiento` lee, sin cambiar nada, Computrabajo (`/candidate/match?p=N`, todas las páginas), elempleo («Mi proceso», hasta 25 por vuelta, primero los que no han avanzado), Gupy (su API: la página solo dibuja 12 de 31), Magneto («Mis procesos») y AIRA (`/list_applications`). Lo nuevo va a Telegram y a la app («En revisión»/«Rechazada» con nota; nunca hacia atrás; si hay dos iguales, solo avisa). Primera foto: 7 hojas de vida vistas en Computrabajo, lo demás enviado sin avance. También se excluyen «docente», «tesorería» y «coordinador».
- [x] Eightfold (Mercado Libre, Softtek; `runner/eightfold_apply.py`, 2026-11-24): eran los portales vigilados con más vacantes que encajan sin postulación automática (14 con 60 o más). Formulario sin cuenta en `/careers/apply?pid=<id>`: CV, contacto (se corrige lo que Eightfold lee del CV), país y código del teléfono (listas que se filtran escribiendo), preguntas de texto, radios «Si»/«No», listas (`role=combobox`) y autorizaciones obligatorias. reCAPTCHA invisible de Google: el bot no lo toca ni se oculta; si aparece un reto, la vacante pasa a la persona. Talento Aval se estudió y queda para después: 7 vacantes de TI y su API exige un formato que arma la página.
- [x] Eightfold en pausa (2026-11-24): el primer envío real (Softtek, Desarrollador Front-End Angular) pulsó «Enviar solicitud» pero no apareció ninguna confirmación reconocible; `postular` queda apagado en Mercado Libre y Softtek hasta ver, en un envío supervisado, qué responde el servidor (ahora queda en el registro, con una captura). Además, en los portales de empresas una oferta saltada sin preguntas pendientes (cerrada, sin formulario) ya no se reintenta en cada vuelta.
- [x] Filtro de estafas (2026-11-25): una falsa convocatoria «de RTVC» en elempleo (a la que el bot se postuló el 21-11, antes de los filtros de cargos) terminó en WhatsApp pidiendo cédula, correo y 150.000 pesos por cursos «con devolución»; el dueño no pagó. `scam_reason` descarta antes del CV las ofertas que piden pagar (cursos, certificados, inscripción) y las «convocatorias» masivas de decenas de cargos a la vez (la plantilla de las falsas RTVC y Comfamiliar de Nariño). Revisadas las 268 postulaciones: solo esas dos (retiradas en la app).
- [x] Teamtailor Connect de Periferia IT con la sesión del dueño en el navegador del bot (no hace falta para postular).
- [x] Publicaciones de LinkedIn donde etiquetan al dueño (`runner/linkedin_posts.py`, 2026-11-26, pedido del dueño: su hermana lo etiqueta en vacantes publicadas como posts normales, con texto o afiche). Cada vuelta, antes de buscar, lee `/notifications/?filter=mentions_all` y cada publicación nueva una vez (máx. 8). Si enlaza una oferta de un portal que el bot postula, la oferta va a la bandeja. Si no, `POST /vacancies` con el texto y hasta 3 imágenes: la app transcribe el afiche (`core/vacancy.transcribe_images`) y lo guarda como texto. Luego las mismas reglas (estafa, excluir, incluir, idioma, compatibilidad), CV y Telegram con cómo postular (correo o enlace). Nunca abre los enlaces del post (destino tomado de `/safety/go/?url=`) ni envía correos.
- [ ] Desplegar la API con imágenes en `/vacancies` ANTES de actualizar el clon del bot: la API vieja ignora `images`, y una publicación que solo trae el afiche quedaría como «no es vacante» para siempre.
- [ ] Talento Aval (Grupo Aval): búsqueda con un token anónimo que hay que leer de la página; postular pide cuenta Microsoft.
- [x] `runner/getonbrd.py` (`portal = "getonbrd"`): API pública de búsqueda de Get on Board por país; solo categorías de tecnología, nivel sin experiencia/junior/semi senior, del último mes, sin inglés salvo sede en el país. El detalle por API pide clave: se lee de la página pública (microdatos JobPosting), con la empresa de cada oferta, que es la que va a la app y a Telegram. Volumen bajo, como se esperaba: 3 recientes para Colombia el 2026-11-22, ninguna para el dueño.

**elempleo (Fase 8, 2026-11-21).** Pedido del dueño («ya entré a elempleo, continúa y probablemente también debas modificar el perfil»).
- [x] Hoja de vida del dueño igual a LinkedIn: descripción, experiencias (El Arte de Nicolás, Equimat, Karta; se quitó una freelance que no estaba), estudios formales (UdeC y UNAB), 12 cursos complementarios, 18 habilidades técnicas, el CV general como adjunto (en lugar de uno viejo de «Auxiliar de recursos educativos») y GitHub.
- [x] Estudio sin postular:
  - La búsqueda pública `/co/ofertas-empleo/trabajo-<cargo>?fecha=hoy|hace-1-semana|hace-2-semanas|hace-1-mes` (y `-modalidad-remoto`) trae 20 por página con los datos de cada oferta; sin `fecha` mezcla meses.
  - La oferta publica `JobPosting` y las condiciones (experiencia, estudios, contrato).
  - «Postularme a oferta» es un `POST /co/JobOffers/JobOfferDetail/Save?jobOfferId=…` con el token de la página, sin preguntas. Responde un código: 2 = sigue en el sitio de la empresa, 3 = hoja de vida incompleta, 4 = ya postulada.
  - La sesión (`.ELEMPLEO`) es una cookie de sesión: Chrome la borraba al cerrarse. El perfil del bot ahora reabre la sesión anterior (`session.restore_on_startup = 1`) y así se conserva.
- [x] `runner/elempleo.py` (búsqueda) y `runner/elempleo_apply.py` (postular con la petición de la página). Probados con páginas de ejemplo y un elempleo falso, sin red. Lo que solo puede hacer el dueño (sitio de la empresa, videocuestionario, postulación rápida) le llega por Telegram como postulación manual.
- [x] El navegador del bot ocupado ya no tumba la vuelta: la de las 15:47 del 2026-11-21 falló porque se estaba editando elempleo con ese navegador (24 de Computrabajo y 4 de Magneto quedaron sin enviar; una vuelta a mano envió 7 y 2). Ahora espera hasta 30 minutos.
- [x] «Postulación rápida». Sin sesión, todas las ofertas se ven normales; con sesión, una práctica la tenía. La empresa recibe el PDF que se elige entre los adjuntos de la hoja de vida, así que el bot elige el primero (el CV general) y envía ese formulario como la página. No sube archivos, porque quedarían también en la hoja de vida. Probado en modo prueba contra la oferta real.
- [ ] Primer envío real a elempleo (lo hará la vuelta de las 9:17 del 2026-11-22: el 21 ya no quedaba cupo de IA para analizar vacantes nuevas).
- [x] Sin cupo diario de IA, una vacante con preguntas de filtro sigue «preparada» para la vuelta siguiente, en vez de quedar saltada para siempre. En la vuelta manual del 2026-11-21 se saltaron así 19 (17 de Computrabajo y 2 de Magneto), que se devolvieron a la cola. Tras el primer «cupo agotado», el bot no vuelve a preguntarle a la app en esa vuelta.

### CV v2: legible para personas y ATS (2026-11-18, pedido del dueño)

La auditoría del PDF anterior encontró:
- La capa de texto estaba bien: completa, con tildes y fuentes incrustadas.
- Media página vacía mientras se descartaba un proyecto relevante.
- Letra de 8 pt justificada.
- Títulos de sección en versalitas, que el ATS lee en minúsculas.
- Sin ciudad ni titular.
- Educación sin fechas.
- Todas las habilidades técnicas en una sola categoría.

Cambios:
- [x] **Diseño** al estilo de los CV técnicos más usados:
  - Una columna, Liberation Sans (métricas de Arial) a 10 pt, alineada a la izquierda.
  - Títulos de sección con texto real en mayúsculas.
  - Cargo a la izquierda y fechas a la derecha; empresa y lugar debajo, en cursiva. La educación va con el mismo formato.
- [x] **Encabezado:** titular y ciudad (migración 0010, columnas nuevas en `users`), editables en Perfil → Datos de contacto; también van en el Word.
- [x] **Habilidades técnicas agrupadas** (lenguajes, frameworks, bases de datos, nube y DevOps, ciberseguridad, datos) con un diccionario determinista. Solo reordena lo que la persona tiene y solo si la guardó en una categoría genérica.
- [x] **La selección ya no descarta experiencias** mientras haya espacio (hasta 4; de 10 a 14 viñetas). El ajuste medido a 1 página recorta primero lo menos relevante.
- [x] **Prueba de «lectura ATS»** (`tests/test_cv_ats.py`): extrae el texto del PDF y exige todos los campos, los títulos en mayúsculas en orden, el cargo antes de la fecha y de las viñetas, y que no haya ligaduras ni caracteres perdidos.
- [ ] Correr `scripts/run_evals.py` con IA real: aquí no hay llave; hacerlo en el próximo despliegue.

### Fase 6 — Pruebas reales y retroalimentación
- [ ] Uso diario por los dos usuarios (y amigos) con postulaciones reales
- [ ] Registro de problemas y mejoras; ajustar cargos sugeridos, mensajes, motor y diseño con datos reales
- [ ] Evals con casos reales anonimizados

## Registro de decisiones

| Fecha | Decisión | Por qué |
|---|---|---|
| 2026-11-24 | LinkedIn con compatibilidad mínima de 50 (antes sin mínimo) y los años que LinkedIn trae guardados se responden de nuevo | Decisión del dueño. Sin mínimo, la cola tenía vacantes de 22 a 45 % (firmware ESP32, videojuegos) que gastaban el cupo de 20 diarias; con 60, como en los demás portales, quedaban 3 de 19. LinkedIn llenaba «3 años de Java» con una respuesta vieja que el perfil no respalda: ahora vale la respuesta del bot (perfil y la regla de 2 años para junior). |
| 2026-11-18 | En Computrabajo, CV por vacante marcado «por defecto» al postular, más un CV general fijo | La empresa recibe el PDF por defecto; un CV general en uno de los 10 espacios garantiza que nunca quede sin PDF si Computrabajo solo guardara una referencia y el bot rotara el de la vacante (decisión del dueño) |
| 2026-11-22 | Bancolombia se postula «en lote»: la persona entra en la ventana del bot y él postula enseguida a todo lo preparado | Su acceso (SuccessFactors) pide captcha y no tiene «mantener la sesión»; la de la página de ofertas venció en menos de 20 minutos. El bot no resuelve captchas: la persona entra (un minuto) y el bot hace el resto con esa sesión (CV de la vacante, preguntas del puesto, declaración de conformidad que el dueño autorizó firmar con su nombre, «Aplicar» y confirmación en «Puestos solicitados»). Las preguntas de experiencia siguen la regla del dueño («Sí») |
| 2026-11-22 | El bot omite las vacantes que no están en español, salvo las de Colombia (`solo_idiomas`, `salvo_pais`) | Decisión del dueño: su inglés es básico. Las alertas de LinkedIn traían ofertas en inglés de EE. UU. y en alemán de Alemania; se omiten antes de hacer el CV. Las de Colombia que piden inglés siguen |
| 2026-11-22 | `find_by_url` compara solo id y enlace; las listas de la API no traen texto de vacante ni evidencias | Neon pausó la base el 22-11 por pasar los 5 GB de transferencia del plan gratuito (5,33 GB; cómputo 3,24 de 100 h, base de 45 MB). `find_by_url` se llama 2–3 veces por vacante nueva y una por enlace de alerta, y traía las ~310 postulaciones con sus textos: unos 7 MB por llamada, ~870 llamadas el 21-11. Ahora trae unos 30 KB y completa solo la que coincide |
| 2026-11-22 | `[incluir]`: el bot solo analiza los cargos con alguna palabra de la lista | Pedido del dueño. El cupo de IA de la noche del 21 se fue en analizar vacantes que luego quedaron bajo 60: en el registro del bot, 196 de 258. Con su lista de tecnología, el filtro se habría ahorrado 113 de esos 196 análisis (57 %). Las «buenas» que habría omitido eran casi todas falsos positivos del puntaje («Editor audiovisual» con 100); para las reales se agregaron «hardware», «bi», «plataforma» y «monitoreo». Es opcional: sin la tabla se analiza todo (la app sirve para cualquier profesión) |
| 2026-11-22 | Resumen del CV: quién es la persona y qué aporta a esa vacante, sin plantilla | Auditoría de 73 CV del dueño, pedida por él. 43 decían «‹cargo de la vacante› con 1 año de experiencia como… Competente en ‹15 a 18 habilidades›», incluso con cargos ajenos («Editor audiovisual», «Realizador de medios»), y 13 cayeron al respaldo de una línea («Desarrollador full stack: 1 años de experiencia como…»). El prompt obligaba a empezar con el cargo exacto de la vacante y a listar habilidades. Ahora: 2–3 oraciones (40–70 palabras) con cargos reales, años, formación, 3–5 habilidades que pide la vacante y un logro con su cifra. Una revisión determinista de estilo (cargo de la vacante como propio, muy corto, lista larga, relleno, frase copiada de la vacante) y la de datos piden una corrección; si los datos siguen sin respaldo, un respaldo con cargos, años, formación y habilidades relevantes. Con DeepSeek, en los 5 casos de evaluación quedaron de 57 a 69 palabras, sin respaldo |
| 2026-11-22 | Viñetas del CV de una línea (≈100 caracteres, máx. 130), empezando por lo que respalda los requisitos de la vacante; el perfil del dueño se completó con lo que implican sus logros, confirmado por él | Auditoría de 116 CV pedida por el dueño: 8,9 viñetas por CV de 20 logros en total (las mismas 5 o 6 siempre), un tercio casi copiadas del original, y el ajuste a 1 página recortaba viñetas de 2 líneas. Se le propusieron 23 tareas que implican sus logros (p. ej., verificar la firma de los webhooks de Wompi) y 20 habilidades que ya nombraban; las confirmó todas (44 logros, 59 habilidades). Con su perfil real y DeepSeek: 12–13 viñetas en vez de 9–12, de 88–92 caracteres en promedio, sin revertidas; evaluación: 0/37 inventadas, 5/5 en 1 página. «Herramientas / DevOps» pasa a categoría genérica (dejaba dos grupos de DevOps) |
| 2026-11-21 | Tras un 429 del proveedor principal, 15 minutos directo al respaldo | El plan gratuito de Gemini se agotó la primera noche con el cupo de 600; cada llamada lo reintentaba 3 veces con espera antes de pasar a DeepSeek, y las alertas acumuladas tardaban minutos por correo |
| 2026-11-21 | Un buzón de alertas que no abre se avisa (Bandeja, API y Telegram del bot) | Desde el 11–14 de noviembre Gmail rechazaba la contraseña de aplicación del buzón de la app («AUTHENTICATIONFAILED»), la revisión respondía «ok» y ninguna alerta de LinkedIn llegó a la bandeja en una semana: el bot no tuvo vacantes de LinkedIn. La contraseña nueva la crea el dueño (credencial de su cuenta de Google) |
| 2026-11-21 | Cupo de IA 600 por cuenta al día (antes 200) y DeepSeek como respaldo de Gemini | Pedido del dueño: con cuatro portales, el bot agotaba las 200 llamadas a media tarde y las vacantes con preguntas de filtro esperaban al otro día. En los registros, Gemini (clave gratuita) solo falló por saturación (503), no por su propio cupo. DeepSeek, con el saldo del dueño (USD 2), responde solo cuando Gemini no puede, así que el gasto queda acotado |
| 2026-11-21 | elempleo se postula con la petición de su botón, desde la página (no haciendo clic) | Después de responder, la página cambia de dirección o abre el sitio de la empresa, y con eso se perdía la respuesta: no se sabía si quedó postulada. El bot no abre sitios de empresas; se los pasa al dueño por Telegram. elempleo envía su hoja de vida, no un PDF por vacante |
| 2026-11-21 | El perfil de Chrome del bot reabre la sesión anterior al arrancar | elempleo guarda su sesión en una cookie de sesión, que Chrome borra al cerrarse: habría que entrar en cada vuelta, con captcha. Reabrir la sesión anterior es una opción normal de Chrome, no una forma de esconder el bot |
| 2026-11-21 | Magneto se postula con la misma petición que envía su página (no haciendo clic) | Su cuestionario es un chat de una pregunta a la vez y sus formularios tienen fallas (fechas, borrar). El bot hace antes las mismas consultas que la página y se detiene donde ella le preguntaría algo a la persona (otra cuenta con la misma cédula, cuestionario ya respondido). La empresa recibe el perfil de Magneto, no un PDF, así que el perfil tiene que estar igual a LinkedIn |
| 2026-11-20 | Preguntas de experiencia del bot: «Sí» y años de junior (2), aunque el perfil no lo muestre; reemplaza al «No» de la fila siguiente | Decisión del dueño: son preguntas de filtro, dice que ya ha hecho lo que preguntan y que en la entrevista responde por ello. Un «No» lo descarta antes de que una persona lea el CV. Se limita a las preguntas de experiencia (un «Sí» a «¿requieres patrocinio?» lo perjudicaría) y no toca el CV, que sigue verificado |
| 2026-11-20 | Ante una pregunta de experiencia sin respaldo, el bot responde que no la tiene en vez de saltar la vacante | Saltarla perdía vacantes buenas por una sola herramienta; decir «No» o «0» es verdad y deja que la empresa decida. La regla de no inventar sigue: un «Sí» siempre necesita evidencia del perfil |
| 2026-11-20 | Gmail reenvía a la app solo las alertas de LinkedIn, con un filtro | El reenvío de todo el correo mandaría a la app correos personales; el servidor igual los rechazaría, pero no deben salir del buzón |
| 2026-11-20 | Las vacantes de LinkedIn llegan por sus alertas por correo a la bandeja, no por su búsqueda pública | La búsqueda pública devolvió 429 a la primera petición tres días seguidos desde la IP de casa. Buscar con la sesión es lo que LinkedIn vigila en las cuentas, y una restricción tumbaría también la «Solicitud sencilla». Las alertas son un uso normal y ya se analizan en el servidor |
| 2026-11-19 | La verificación anti-invención también cuenta herramientas y metodologías en minúscula | Un CV para una vacante de QA decía «metodologías agile» (de la vacante, no del perfil): solo se revisaban cifras, siglas y palabras con mayúscula. Ahora el vocabulario técnico del motor y las metodologías («agile», «scrum», «itil», «devops»…) deben estar en la fuente |
| 2026-11-19 | Al ajustar a una página, se recortan cursos y certificados antes de dejar una experiencia con 1 logro | El CV general del dueño mostraba su trabajo actual con 1 viñeta para conservar dos certificados cortos; para quien selecciona pesa más un logro del trabajo |
| 2026-11-18 | En el CV, el título de educación formal siempre entra y va primero | La educación se ordenaba por «citada» y fecha: un título sin fechas quedaba fuera tras cuatro certificados recientes (pasó con el del dueño). Para cualquier profesión, el título pesa más que un curso |
| 2026-11-18 | En Computrabajo, compatibilidad mínima de 60 y descartar en la app lo que no llega | Su búsqueda mezcla oficios con el mismo nombre (ventas, producción); descartarlo con el motivo deja la bandeja limpia y el registro de por qué no se postuló |
| 2026-11-26 | Las vacantes de publicaciones de LinkedIn llegan por las menciones (notificaciones con la sesión del bot), no por los correos de LinkedIn | El correo de «te mencionó» solo trae un extracto del post y enlaces con rastreo (que no se abren); las notificaciones dan el id del post. El afiche se transcribe en el servidor y se guarda como texto, para que reanalizar y generar el CV funcionen igual que con cualquier vacante. Postular por correo queda en manos del dueño (Telegram): enviar correos por él necesita su permiso explícito |
| 2026-11-18 | Programación con un temporizador de systemd del usuario, no con cron ni una tarea en la nube | La ventana del bot necesita la sesión gráfica de la persona (DISPLAY y llavero), que systemd del usuario ya tiene; `Persistent=true` recupera la vuelta si el computador estaba apagado; no requiere root |
| 2026-11-18 | El bot nunca envía una solicitud con un CV distinto al de la vacante | LinkedIn deja elegido el último CV subido (en la primera prueba real quedó uno de octubre); enviar con otro CV rompe el registro exacto de qué se mandó |
| 2026-11-18 | Pausas separadas: la búsqueda pública (429 → 6 h) y la cuenta (verificación o tope → 24 h) | Un 429 de la búsqueda sin sesión no dice nada de la cuenta; con una sola pausa, frenaba también las postulaciones ya preparadas |
| 2026-11-16 | Bot de LinkedIn local con un perfil de navegador propio (Playwright persistente), no extensión ni CDP | LinkedIn busca extensiones instaladas y sus condiciones nombran los plugins; desde Chrome 136 el puerto de depuración exige otro perfil y expone la sesión a cualquier proceso local. En la IP de casa y con una sesión real, el riesgo para la cuenta es menor que desde un servidor |
| 2026-11-16 | El bot se autentica con un token propio (solo su huella en la base), no con la sesión de Clerk | La sesión de Clerk dura minutos; un token largo, revocable y sin permisos de cuenta (no crea tokens ni vincula perfiles) permite correr sin la persona |
| 2026-11-16 | Prioridad: búsqueda y postulación automática para el dueño; SaaS en pausa | La pareja ya consiguió empleo; el dueño necesita trabajo y quiere que la herramienta lo haga sola. Riesgo real a vigilar: los términos de LinkedIn prohíben bots (posible cierre de la cuenta) |
| 2026-11-16 | Web clara con mundo «tabla de posiciones», fuentes servidas por la app | El tema oscuro clonado de GitHub se veía genérico y desperdiciaba la pantalla; una tabla ordenada es la forma natural de una bandeja por compatibilidad. Fuentes propias: sin dependencia de Google Fonts |
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
| 2026-10-07 | Descubrimiento con enlaces de búsqueda que abre la persona, no recorrido de listados desde el servidor | Ver ofertas en el navegador propio no viola términos ni arriesga bloqueos; el servidor solo lee las vacantes que la persona elige (máx. 10 por carga) |
| 2026-10-07 | La bandeja usa la misma tabla de postulaciones con estados `por_revisar` y `descartada` (no una tabla aparte) | Al prepararla, la vacante ya es la postulación: mismo id, mismo análisis, mismo historial; el CV enviado queda ligado a ella sin copiar datos |
| 2026-10-07 | La bandeja procesa los enlaces en secuencia, no en paralelo | El plan gratuito de Gemini limita peticiones por minuto; en secuencia hay progreso claro y ~6 s por vacante |
| 2026-10-07 | Sin cambio automático de pestaña al preparar una vacante | `st.tabs` con estado obliga a recargar en cada cambio de pestaña (más lento con Neon); un aviso claro basta |
| 2026-10-07 | Etiquetas de pestaña fijas; los contadores van en una línea encima | Streamlit vuelve a la primera pestaña si cambia la etiqueta (descartar una vacante sacaba a la persona de la bandeja) |
| 2026-10-07 | Repetidas por enlace: host + ruta + parámetros que identifican la vacante (`?jk=`), sin los de seguimiento; ante la duda se conserva el parámetro | Mezclar dos vacantes ataría el CV de una a la otra (rompe la garantía de "CV correcto"); un duplicado solo cuesta un clic en "Descartar" |
| 2026-10-07 | "Mi mercado" cuenta también las vacantes de la bandeja y las descartadas | Son datos de qué pide el mercado aunque no se postule; las métricas de envío y avance solo cuentan las enviadas |
| 2026-10-07 | La API verifica tokens de un proveedor de identidad (JWKS) en vez de manejar contraseñas | Verificación de correo, recuperación de contraseña, login con Google y protección contra fuerza bruta ya resueltos; cambiar de proveedor = cambiar 3 variables |
| 2026-10-07 | La API reutiliza los servicios del núcleo; Streamlit y API conviven sobre la misma base | Sin lógica duplicada ni migración de datos; los usuarios no pierden nada mientras se construye la versión nueva |
| 2026-10-07 | Guardar el mapa de evidencias de la IA y recalcular el match sin IA | Ver la compatibilidad es lo más frecuente; así es instantáneo y gratis, y las referencias a logros borrados se descartan solas. La IA solo se vuelve a llamar cuando la persona actualiza tras cambiar su perfil |
| 2026-10-07 | Cola de trabajos en Postgres (no Redis/Celery) | Una pieza menos que desplegar y pagar; `SKIP LOCKED` reparte sin duplicar; el volumen (decenas de trabajos al día) está muy lejos de sus límites |
| 2026-10-07 | Cupo de IA por llamadas reales (envoltorio del cliente), no por "unidades" estimadas | Exacto para cualquier operación presente o futura y no cobra los errores del proveedor |
| 2026-10-07 | Clerk + Cloud Run (CPU siempre asignada, máx. 1 instancia) + sin dominio | Elección del dueño (Clerk, US$0). Cloud Run con cobro por petición frena la CPU al responder y la cola de trabajos quedaría a medias; con CPU asignada tiene su propia capa gratuita. Render gratis: 0,1 CPU (el PDF sería lentísimo) y ~1 min para despertar |
| 2026-10-07 | La llave pública de Clerk la entrega la API (`/api/config`), no se compila en la web | La misma imagen sirve en cualquier entorno y Cloud Run la construye con `--source` sin argumentos |
| 2026-10-07 | Los perfiles de Streamlit se vinculan con su contraseña, no por correo | Los perfiles viejos no tienen correo verificado; la contraseña prueba que es la misma persona |
| 2026-10-08 | Nada de bots que entren a los portales con la contraseña de la persona; automatizar con alertas por correo y (después) una extensión donde ella da el último clic | LinkedIn prohíbe bots y extensiones que automaticen y restringe o cierra esas cuentas; guardar contraseñas de terceros sería el mayor riesgo de la app; postular en masa baja la respuesta; un navegador por usuario en la nube no cabe en US$0 |
| 2026-10-08 | Correo entrante con un buzón de Gmail propio leído por IMAP, al abrir la bandeja y cada mañana | Sin dominio no hay correo entrante propio; un webhook por correo despertaría la instancia (CPU siempre asignada, ~15 min por despertar) muchas veces al día; leer bajo demanda cabe en la capa gratuita y no despierta Neon si no hay correo |
| 2026-10-08 | Las alertas usan el mismo trabajo "bandeja" que los enlaces pegados | Una sola ruta de captura y análisis (SSRF, cupo de IA, repetidas); el correo solo aporta los enlaces |
| 2026-10-08 | Registro cerrado con lista de correos permitidos (no modo «Restricted» con invitaciones) | No envía correos y basta con dos personas; al abrir el SaaS se cambia la configuración, no el código |
| 2026-10-08 | Cloud Run en un proyecto de Google Cloud separado del de la llave de Gemini | Activar facturación en el proyecto de Gemini pasa la llave al plan de pago |
| 2026-10-07 | Tope diario global de IA además del cupo por cuenta | Con registro abierto, muchas cuentas nuevas multiplicarían el cupo individual; el global acota el costo total |
| 2026-10-07 | El código tolera una base en una revisión de Alembic más nueva | Streamlit y la API comparten Neon y se despliegan por separado: la que migra primero no debe tumbar a la otra |
| 2026-10-07 | Frontend sin librería de componentes ni Tailwind | Pocas pantallas y un sistema de diseño ya definido: CSS con tokens es más liviano, sin dependencias extra que mantener o auditar |
| 2026-10-07 | Tipos del frontend generados desde OpenAPI y comprobados en la CI | El backend es la fuente de verdad; un cambio en la API que rompa el frontend lo detecta `tsc`, no la persona usuaria |
| 2026-10-07 | TypeScript 5.9 (no 7) en `web/` | `openapi-typescript` usa la API JS del compilador, que TypeScript 7 (nativo) ya no ofrece |
| 2026-10-07 | Entrada de desarrollo por nombre hasta elegir proveedor de identidad | Permite construir y probar todo el frontend sin decidir aún el proveedor (decisión del dueño en la 5d); nunca existe con Postgres ni con JWKS |
| 2026-10-07 | Migraciones sin recrear tablas en SQLite (índices únicos en vez de restricciones) y llaves foráneas apagadas solo durante la migración | Recrear `users` con cascadas activas borraba todos los datos locales; producción (Postgres) no se afectaba, pero el desarrollo y las pruebas sí |
| 2026-10-07 | Fase 6 (pruebas reales) al final, por decisión del dueño | Quiere probar a fondo la versión completa; la app actual sigue disponible para postular mientras tanto |
| 2026-10-07 | No purgar el historial git de los `.md` personales | Solo contenido de CV (sin contacto ni IDs); purgar exige force push a `main` público y GitHub mantiene accesibles los commits huérfanos por SHA |

## Próximo paso

1. ~~(dueño) Renovar la contraseña de aplicación del buzón de alertas~~: hecho el 2026-11-21 (versión 2 del secreto, revisión 00015). La app recibió 13 alertas de LinkedIn acumuladas; analiza 40 vacantes por día y las demás esperan. Ver el primer envío de LinkedIn en la vuelta de las 9:17 del 22-11. Pendiente: el lector de alertas de Computrabajo no saca vacantes de sus correos reales (34 alertas con 0 vacantes).
2. ~~(dueño) Primer lote de Bancolombia~~: hecho el 2026-11-22 (2 enviadas). Cada oferta nueva que encaja avisa por Telegram con `python -m runner lote bancolombia`; el dueño entra en la ventana del bot y el bot hace el resto.
3. Revisar `registro.log` tras las vueltas: el primer envío real a elempleo (20 preparadas el 2026-11-21) y las opciones de las preguntas que quedan sin respuesta (ahora se anotan), para ajustar el banco.
4. ~~Resumen del CV honesto y natural~~: hecho el 2026-11-22 (ver la decisión). Revisar en los CV de las próximas vueltas que suene bien con el perfil real del dueño.
5. Ver qué traen Workday, Mercado Libre y Get on Board en las vueltas. Si el dueño crea su cuenta en Accenture (Workday), estudiar postular ahí en lote como en Bancolombia.
6. Después: LinkedIn sin «Solicitud sencilla» (medir adónde llevan), Get on Board y la vista web de lo que hizo el bot.
