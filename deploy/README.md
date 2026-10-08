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
4. **Cierra los registros** mientras sea solo para ustedes: *Configure → Restrictions* → modo de registro
   **Restricted** e invita sus correos. Así nadie más gasta el cupo de IA (además hay un tope global de
   1000 llamadas al día para todo el servicio).

## 2. Google Cloud (una sola vez)
1. Crea una cuenta en [cloud.google.com](https://cloud.google.com), un proyecto (p. ej. `cv-optimizer`) y
   actívale la facturación (pide tarjeta aunque no cobre dentro de la capa gratuita).
2. **Alerta de presupuesto**: Facturación → Presupuestos y alertas → crear presupuesto de **US$1** con
   avisos al 50 % y 100 %. Así te enteras antes de cualquier cobro.
3. Instala la CLI: [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install), y luego:
   ```bash
   gcloud auth login
   gcloud config set project TU_PROYECTO
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
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
CLERK_PUBLISHABLE_KEY=pk_test_... ./deploy/cloudrun.sh
```
Solo despliega `main` limpio y al día (se niega si hay cambios locales). Al final imprime la dirección
(`https://cv-optimizer-….run.app`). Para actualizar, el mismo comando. Si Streamlit migra la base a una
revisión más nueva antes que este servicio, el servicio no se cae (avisa en el registro); redespliégalo
para ponerlo al día.

## 5. Primer uso
1. Entra con Google o correo.
2. En **Perfil**, «¿Ya usabas CV Optimizer?» → tu nombre de perfil de la versión anterior y su contraseña:
   tus experiencias, CV y postulaciones pasan a tu cuenta nueva (Streamlit los sigue mostrando).

## Qué queda configurado
| Variable | Valor |
|---|---|
| `DATABASE_URL`, `GEMINI_API_KEY` | Secret Manager |
| `AUTH_JWKS_URL`, `AUTH_ISSUER` | derivados de la llave de Clerk |
| `AUTH_AUTHORIZED_PARTIES` | las direcciones `run.app` del servicio (solo tokens pedidos desde esta web) |
| `CLERK_PUBLISHABLE_KEY` | la entrega `/api/config` a la web |
| `AI_DAILY_CALLS` / `AI_GLOBAL_DAILY_CALLS` | 200 llamadas a la IA por cuenta al día / 1000 en total |

Cloud Run: CPU siempre asignada (la cola de trabajos genera el CV después de responder), 0 a 1
instancias, 1 vCPU y 1 GiB, cuenta de servicio `cv-optimizer-run`. Sin `DATABASE_URL` de Postgres el
servicio se niega a arrancar.
