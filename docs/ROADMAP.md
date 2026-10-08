# Roadmap y estado del proyecto

> Documento vivo. Se actualiza al terminar cada cambio relevante: qué existe, qué se hizo, qué sigue.
> Última actualización: 2026-10-08 (fase 5e: alertas de empleo por correo → bandeja)

## Prioridad actual

1. **Ahora:** que la app funcione bien para 2 personas que buscan empleo con urgencia (el dueño y su pareja), de **cualquier profesión**.
2. **Futuro:** convertirla en SaaS. No se migra a React/FastAPI hasta tener un núcleo de dominio independiente de Streamlit (ver decisiones).

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

### Fase 6 — Pruebas reales y retroalimentación
- [ ] Uso diario por los dos usuarios (y amigos) con postulaciones reales
- [ ] Registro de problemas y mejoras; ajustar cargos sugeridos, mensajes, motor y diseño con datos reales
- [ ] Evals con casos reales anonimizados

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

1. 5e (dueño): crear el Gmail de la app y su contraseña de aplicación → desplegar → activar las alertas de los dos y crear alertas en los portales. Con los primeros correos reales, ajustar los lectores por portal.
2. 5f extensión de navegador (Guardar y Llenar, con confirmación humana) → 5g (operación y Ley 1581) → 5h (cobros).
3. Fase 6: pruebas reales y retroalimentación (decisión del dueño: probar a fondo cuando la versión SaaS esté lista; la app de Streamlit sigue disponible mientras tanto).
