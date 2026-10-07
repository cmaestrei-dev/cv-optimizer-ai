# Roadmap y estado del proyecto

> Documento vivo. Se actualiza al terminar cada cambio relevante: qué existe, qué se hizo, qué sigue.
> Última actualización: 2026-10-07

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

### Fase 1 — Núcleo y multi-profesión / multi-IA
- [ ] Prompts genéricos para cualquier profesión (hoy asumen perfil TI: "Technical Skills", categorías de programación). Caso real a validar: perfil administrativo/operativo (sector automotriz, antes e-commerce)
- [ ] Modelo de datos estructurado (experiencia con campos y viñetas, no Markdown parseado con regex)
- [ ] Separar lógica de negocio de Streamlit (`core/` sin dependencias de UI)
- [ ] Capa de IA con proveedores intercambiables (Gemini, DeepSeek) y salidas JSON validadas con Pydantic
- [ ] Prompts en archivos versionados; eliminar versiones muertas (v1/v2)
- [ ] Set de vacantes de prueba para comparar proveedores con datos

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
| 2026-10-07 | No purgar el historial git de los `.md` personales | Solo contenido de CV (sin contacto ni IDs); purgar exige force push a `main` público y GitHub mantiene accesibles los commits huérfanos por SHA |

## Próximo paso

1. Usuario: configurar `APP_ACCESS_PASSWORD` en Streamlit Cloud y rotar token de Turso + API key de Gemini.
2. Merge del PR de la Fase 0.
3. CI en GitHub Actions (ruff + pytest).
4. Fase 1: prompts multi-profesión, validando con un perfil administrativo/operativo.
