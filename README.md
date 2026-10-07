# CV Optimizer AI

Genera CVs ATS-optimizados mediante IA, cruzando tu historial real con cada vacante. Un CV nuevo y distinto por cada postulación, listo en segundos.

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

Para persistencia local (SQLite), no se requiere configuración adicional. La base de datos se crea automáticamente en `data/cv_optimizer.db`.

## Despliegue en Streamlit Cloud

1. Haz fork de este repositorio
2. Conecta el repo en [share.streamlit.io](https://share.streamlit.io)
3. Configura los siguientes secretos en el dashboard de Streamlit Cloud:
   - `GEMINI_API_KEY` — tu API key de Google Gemini
   - `TURSO_DB_URL` — URL de tu base de datos Turso
   - `TURSO_AUTH_TOKEN` — token de autenticación de Turso
   - Opcional, motor nuevo: `LLM_EXTRACT` / `LLM_WRITE` (`proveedor` o `proveedor:modelo`, p. ej. `deepseek:deepseek-flash`) y `DEEPSEEK_API_KEY`
   - `APP_ACCESS_PASSWORD` — contraseña de acceso a la app (**obligatoria** si usas Turso: sin ella la app queda cerrada)

### Base de datos en Turso (gratuito)

Para que los datos persistan entre deploys:

1. Crea una cuenta en [Turso](https://turso.tech)
2. Crea una base de datos: `turso db create cv-optimizer`
3. Obtén la URL: `turso db show cv-optimizer --url`
4. Genera un token: `turso db tokens create cv-optimizer`
5. Configura `TURSO_DB_URL` y `TURSO_AUTH_TOKEN` como secretos en Streamlit Cloud

## Estructura del proyecto

```
app.py              # Entry point de Streamlit
config.py           # Configuración y constantes
core/               # Núcleo sin UI: cliente de IA multi-proveedor, análisis de vacantes
services/           # Cliente de Gemini (legado), generadores de PDF y DOCX
storage/            # Capa de persistencia (SQLite local / Turso remoto)
ui/                 # Componentes de la interfaz (tabs, formularios)
models/             # Dataclasses (UserProfile)
utils/              # Utilidades (extracción de PDF, retry)
```

Plan, estado y decisiones del proyecto: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Tests

```bash
pytest tests/ -v
```
