# Versión SaaS: un solo contenedor con la API (FastAPI) y la web (React) — Google Cloud Run.
# La web se compila aquí; la llave pública de Clerk la entrega la API en /api/config (variable CLERK_PUBLISHABLE_KEY).

FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# WeasyPrint (PDF del CV) + fuentes compatibles con Arial/Helvetica y Times (las del CSS del CV)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1 fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-api.txt ./
# Sin Streamlit: la imagen solo corre la API (requirements.txt sigue siendo el de Streamlit Cloud)
RUN grep -v '^streamlit' requirements.txt > /tmp/requirements.txt \
 && grep -v '^-r ' requirements-api.txt >> /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt
COPY . .
COPY --from=web /web/dist ./web/dist
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
ENV API_PREFIX=/api WEB_DIST=/app/web/dist PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
