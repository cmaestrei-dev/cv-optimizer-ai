# CV Optimizer AI

Genera CVs ATS-optimizados mediante IA, cruzando tu historial real con cada vacante. Un CV nuevo y distinto por cada postulación, listo en segundos.

- **Bandeja de vacantes**: busca en LinkedIn, Computrabajo, Magneto y elempleo, pega varios enlaces y te las ordena por compatibilidad con tu perfil.
- **CV inteligente**: qué cumples y qué te falta, CV de una página verificado (nunca inventa), respuestas a las preguntas del portal y mensaje para el reclutador.
- **Mis postulaciones**: el CV exacto que enviaste a cada vacante, estados, notas y recordatorios. Tú envías siempre en el portal: la app no postula por ti.

## Requisitos

- Python 3.11+
- API Key de [Google Gemini](https://aistudio.google.com/app/apikey)

## Uso local

```bash
# Instalar dependencias (incluye pytest y ruff)
pip install -r requirements-dev.txt

# Configurar variables de entorno
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Editar .streamlit/secrets.toml con tu API Key de Gemini

# Ejecutar
streamlit run app.py
```

Para desarrollo local no se requiere base de datos: se crea `data/cv_core.db` (SQLite) automáticamente.

## Despliegue en Streamlit Cloud

1. Haz fork de este repositorio
2. Conecta el repo en [share.streamlit.io](https://share.streamlit.io)
3. Configura los siguientes secretos en el dashboard de Streamlit Cloud:
   - `GEMINI_API_KEY` — tu API key de Google Gemini
   - `DATABASE_URL` — cadena de conexión de Postgres ([Neon](https://neon.tech), gratuito): **obligatoria** en despliegue
   - Opcional, motor nuevo: `LLM_EXTRACT` / `LLM_WRITE` (`proveedor` o `proveedor:modelo`, p. ej. `deepseek:deepseek-flash`) y `DEEPSEEK_API_KEY`
   - `APP_ACCESS_PASSWORD` — contraseña de acceso a la app (**obligatoria** con `DATABASE_URL`: sin ella la app queda cerrada)

### Base de datos (Postgres en Neon, gratuito)

1. Crea un proyecto en [Neon](https://neon.tech) y copia la cadena de conexión (botón «Connect»).
2. Configúrala como `DATABASE_URL` en los secretos de Streamlit Cloud (y en tu `.env` local si quieres usarla).
3. Las tablas se crean y actualizan solas al arrancar la app (Alembic). En local, sin `DATABASE_URL`, se usa `data/cv_core.db`.

## Estructura del proyecto

```
app.py              # Entrada de Streamlit: puerta de acceso, barra lateral y pestañas
config.py           # Constantes y categorías
core/               # Núcleo sin UI: IA multi-proveedor, perfil, motor de CV, postulaciones, captura
migrations/         # Migraciones de esquema (Alembic)
services/           # Plantilla y utilidades de PDF/DOCX
ui/                 # Pestañas y componentes de Streamlit
evals/, scripts/    # Evaluación del motor con IA real
```

Plan, estado y decisiones del proyecto: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Tests

```bash
pytest tests/ -v
```
