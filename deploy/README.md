# Publicar la versión SaaS (Google Cloud Run + Clerk)

Un solo servicio sirve la API (`/api`) y la web. Se apaga solo cuando nadie lo usa y, con dos personas
usándolo, cabe en la capa gratuita de Cloud Run. La base de datos es la misma Neon de Streamlit: las dos
versiones conviven mientras dure la transición.

> Hazlo desde `main` actualizado: al arrancar, el servicio aplica las migraciones pendientes a Neon.

## 1. Clerk (inicio de sesión)
1. Crea una cuenta en [clerk.com](https://clerk.com) y una aplicación **CV Optimizer** con **Google** y **Email** activados.
2. Copia la **Publishable key** (`pk_test_…`). Es pública. La *Secret key* no se necesita.
3. Mientras no haya dominio propio se usa la instancia de *desarrollo* de Clerk (muestra un aviso de
   «Development mode» y admite un número limitado de usuarios: suficiente para la fase de pruebas).
4. **Cierra los registros** mientras sea solo para ustedes: lista de correos permitidos (*Configure →
   Restrictions → Allowlist*), sin enviar invitaciones. Así nadie más gasta el cupo de IA (además hay un
   tope global de 1000 llamadas al día para todo el servicio). Con la CLI de Clerk (`npm i -g clerk`,
   `clerk auth login`):
   ```bash
   clerk api /allowlist_identifiers --app APP_ID --instance dev -X POST -d '{"identifier":"correo@gmail.com","notify":false}' --yes
   clerk config patch --app APP_ID --instance dev --json '{"auth_access_control":{"allowlist_enabled":true}}'
   ```
   No hace falta `clerk init` ni `clerk env pull`: la web ya trae Clerk y la llave secreta no se usa.
   La llave publicable sale de `clerk apps list`.

## 2. Google Cloud (una sola vez)
1. Crea una cuenta en [cloud.google.com](https://cloud.google.com), un proyecto (p. ej. `cv-optimizer`) y
   actívale la facturación (pide tarjeta aunque no cobre dentro de la capa gratuita).
2. **Alerta de presupuesto** de ~US$1 con avisos al 50 % y 100 %. Si la cuenta de facturación está en
   pesos (Colombia), el monto va en COP:
   ```bash
   gcloud billing budgets create --billing-account CUENTA --display-name "CV Optimizer ~US\$1" \
     --budget-amount 4000COP --filter-projects projects/TU_PROYECTO \
     --threshold-rule percent=0.5 --threshold-rule percent=1.0
   ```
   **No actives la facturación en el proyecto de la llave de Gemini** («Default Gemini Project»): la
   llave pasaría al plan de pago. Cloud Run va en un proyecto aparte.
3. Instala la CLI: [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install), y luego:
   ```bash
   gcloud auth login
   gcloud config set project TU_PROYECTO
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com billingbudgets.googleapis.com iam.googleapis.com
   ```

## 3. Secretos (los escribes tú; nunca se guardan en el repo ni en el historial de la terminal)
```bash
read -rs DB  && printf '%s' "$DB"  | gcloud secrets create database-url  --data-file=- && unset DB
read -rs KEY && printf '%s' "$KEY" | gcloud secrets create gemini-api-key --data-file=- && unset KEY
```
(`read -rs` espera que pegues el valor sin mostrarlo; luego Enter.) El script de despliegue crea una cuenta
de servicio propia (`cv-optimizer-run`) que solo puede leer estos dos secretos.

## 4. Desplegar
```bash
git checkout main && git pull
PROJECT=TU_PROYECTO CLERK_PUBLISHABLE_KEY=pk_test_... ./deploy/cloudrun.sh
```
Solo despliega `main` limpio y al día (se niega si hay cambios locales). Al final imprime la dirección
(`https://cv-optimizer-….run.app`). Para actualizar, el mismo comando. Si Streamlit migra la base a una
revisión más nueva antes que este servicio, el servicio no se cae (avisa en el registro); redespliégalo
para ponerlo al día.

## 5. Alertas por correo (opcional)
Las alertas de empleo que la persona reenvía desde su Gmail llegan solas a la bandeja.
1. Crea una cuenta de Gmail **solo para la app** (no uses la personal: la app lee todo ese buzón).
2. En esa cuenta activa la verificación en dos pasos (myaccount.google.com/signinoptions/twosv) y crea una
   **contraseña de aplicación** (myaccount.google.com/apppasswords): 16 letras.
3. Guárdalas como secretos:
   ```bash
   printf '%s' 'buzon.de.la.app@gmail.com' | gcloud secrets create alerts-mailbox --data-file=-
   read -rs P && printf '%s' "$P" | tr -cd 'a-zA-Z' | gcloud secrets create alerts-mailbox-password --data-file=- && unset P
   ```
4. Vuelve a desplegar. El script detecta los secretos, genera el token de la revisión programada
   (`alerts-cron-token`) y crea una tarea de Cloud Scheduler que revisa el buzón cada día a las 7:00
   (hora de Bogotá). También se revisa al abrir la bandeja.

Cada persona activa sus alertas en la Bandeja: la app le da su dirección (`buzon+código@gmail.com`) y los
pasos para el reenvío y el filtro de Gmail. Solo se aceptan correos firmados (DKIM) por LinkedIn,
Computrabajo, elempleo y Magneto; los correos se mandan a la papelera apenas se leen.

## 6. Primer uso
1. Entra con Google o correo.
2. En **Perfil**, «¿Ya usabas CV Optimizer?» → tu nombre de perfil de la versión anterior y su contraseña:
   tus experiencias, CV y postulaciones pasan a tu cuenta nueva (Streamlit los sigue mostrando).

La dirección del servicio no se publica en este repositorio (es público): sácala con
`gcloud run services describe cv-optimizer --region us-east1 --format 'value(status.url)'`.

## Qué queda configurado
| Variable | Valor |
|---|---|
| `DATABASE_URL`, `GEMINI_API_KEY` | Secret Manager |
| `AUTH_JWKS_URL`, `AUTH_ISSUER` | derivados de la llave de Clerk |
| `AUTH_AUTHORIZED_PARTIES` | las direcciones `run.app` del servicio (solo tokens pedidos desde esta web) |
| `CLERK_PUBLISHABLE_KEY` | la entrega `/api/config` a la web |
| `ALERTS_MAILBOX`, `ALERTS_MAILBOX_PASSWORD`, `ALERTS_CRON_TOKEN` | Secret Manager, solo si existen los secretos del buzón |
| `AI_DAILY_CALLS` / `AI_GLOBAL_DAILY_CALLS` | 200 llamadas a la IA por cuenta al día / 1000 en total |

Cloud Run: CPU siempre asignada (la cola de trabajos genera el CV después de responder), 0 a 1
instancias, 1 vCPU y 1 GiB, cuenta de servicio `cv-optimizer-run`. Sin `DATABASE_URL` de Postgres el
servicio se niega a arrancar.
