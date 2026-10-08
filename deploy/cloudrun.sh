#!/usr/bin/env bash
# Despliega la versión SaaS (API + web) en Google Cloud Run. Uso, desde la raíz del repo y en `main`:
#   CLERK_PUBLISHABLE_KEY=pk_test_... ./deploy/cloudrun.sh
# Requisitos (una sola vez, ver deploy/README.md): gcloud con sesión iniciada, proyecto con facturación
# y los secretos database-url y gemini-api-key en Secret Manager.
set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-east1}"           # cerca de Neon (aws us-east-2) y en la franja de precio más baja
SERVICE="${SERVICE:-cv-optimizer}"
RUNNER="${SERVICE}-run"                # cuenta de servicio propia: solo lee los dos secretos
: "${CLERK_PUBLISHABLE_KEY:?Define CLERK_PUBLISHABLE_KEY (pk_test_... o pk_live_...)}"
[ -n "$PROJECT" ] || { echo "Define PROJECT o: gcloud config set project TU_PROYECTO"; exit 1; }

# Solo `main` limpio y al día: al arrancar, el servicio migra la base que comparte con Streamlit.
git fetch -q origin main
if [ -n "$(git status --porcelain)" ] || [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "Despliega desde main sin cambios locales (git checkout main && git pull)."; exit 1
fi

# La llave publicable de Clerk contiene (en base64) el dominio de su Frontend API: de ahí salen el emisor y el JWKS.
ENCODED="${CLERK_PUBLISHABLE_KEY#pk_*_}"
while [ $(( ${#ENCODED} % 4 )) -ne 0 ]; do ENCODED="${ENCODED}="; done   # base64 sin relleno
CLERK_DOMAIN="$(printf '%s' "$ENCODED" | base64 -d 2>/dev/null | tr -d '$')"
case "$CLERK_DOMAIN" in *.*) ;; *) echo "La llave de Clerk no parece válida"; exit 1 ;; esac
ISSUER="https://${CLERK_DOMAIN}"

PN="$(gcloud projects describe "$PROJECT" --format 'value(projectNumber)')"
SA="${RUNNER}@${PROJECT}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$RUNNER" --project "$PROJECT" --display-name "CV Optimizer (Cloud Run)"
fi
for secret in database-url gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$secret" --project "$PROJECT" --quiet \
    --role roles/secretmanager.secretAccessor --member "serviceAccount:${SA}" >/dev/null
done

# Direcciones desde donde se aceptan tokens de Clerk (claim azp). Se calculan ANTES de desplegar para que
# ninguna revisión quede sin ellas: la determinista (servicio-númerodeproyecto.región.run.app) y la que
# ya tenga el servicio si existe.
PARTIES="https://${SERVICE}-${PN}.${REGION}.run.app"
EXISTING="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)' 2>/dev/null || true)"
if [ -n "$EXISTING" ] && [ "$EXISTING" != "$PARTIES" ]; then PARTIES="${PARTIES},${EXISTING}"; fi

echo "Proyecto: $PROJECT · Región: $REGION · Servicio: $SERVICE · Clerk: $ISSUER"

# --no-cpu-throttling: la CPU sigue activa fuera de las peticiones (la cola de trabajos genera CV y
#   analiza la bandeja después de responder). Tiene su propia capa gratuita.
# --max-instances 1: un solo proceso (cola en hilo, límites en memoria) y costo acotado.
# --min-instances 0: se apaga sin uso (Neon también puede dormirse).
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source . \
  --service-account "$SA" \
  --allow-unauthenticated --no-cpu-throttling --min-instances 0 --max-instances 1 \
  --cpu 1 --memory 1Gi --concurrency 20 --timeout 300 \
  --set-secrets "DATABASE_URL=database-url:latest,GEMINI_API_KEY=gemini-api-key:latest" \
  --set-env-vars "^@^CLERK_PUBLISHABLE_KEY=${CLERK_PUBLISHABLE_KEY}@AUTH_JWKS_URL=${ISSUER}/.well-known/jwks.json@AUTH_ISSUER=${ISSUER}@AUTH_AUTHORIZED_PARTIES=${PARTIES}@AI_DAILY_CALLS=200@AI_GLOBAL_DAILY_CALLS=1000"

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')"
case ",${PARTIES}," in
  *",${URL},"*) ;;
  *) gcloud run services update "$SERVICE" --project "$PROJECT" --region "$REGION" \
       --update-env-vars "^@^AUTH_AUTHORIZED_PARTIES=${PARTIES},${URL}" ;;  # primer despliegue con otra forma de URL
esac

echo
echo "Listo: ${URL}"
echo "Comprueba: curl -s ${URL}/api/health"
