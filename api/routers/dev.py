"""Solo para desarrollo local: entrar con un nombre, sin proveedor de identidad (se elige en la fase 5d).

Existe únicamente con AUTH_DEV_LOGIN=1 (permiso explícito), AUTH_DEV_SECRET de 32+ caracteres, sin
AUTH_JWKS_URL y con una base que no es Postgres. El permiso explícito evita que un despliegue mal
configurado (p. ej. sin DATABASE_URL, que cae en SQLite) deje una entrada abierta a cualquiera.
"""

import hashlib
import os
import re
import time
import unicodedata

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import DEV_ISSUER
from core.db import database_url

router = APIRouter(tags=["desarrollo"])


def enabled() -> bool:
    return (
        os.environ.get("AUTH_DEV_LOGIN", "").strip() == "1"
        and len(os.environ.get("AUTH_DEV_SECRET", "").strip()) >= 32
        and not os.environ.get("AUTH_JWKS_URL", "").strip()
        and not database_url().startswith("postgresql")
    )


class DevLoginIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class DevTokenOut(BaseModel):
    token: str
    expires_in: int


@router.post("/dev/token", response_model=DevTokenOut)
def dev_token(body: DevLoginIn) -> DevTokenOut:
    if not enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    plain = unicodedata.normalize("NFKD", body.name.strip().lower()).encode("ascii", "ignore").decode()
    # "Ana" y "ana" son la misma cuenta; un nombre sin letras latinas (李雷, Дмитрий) no cae en una compartida
    subject = re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "n-" + hashlib.sha256(body.name.strip().lower().encode()).hexdigest()[:16]
    now, ttl = int(time.time()), 8 * 3600
    token = jwt.encode({"iss": DEV_ISSUER, "sub": subject, "name": body.name.strip(), "iat": now, "exp": now + ttl},
                       os.environ["AUTH_DEV_SECRET"].strip(), algorithm="HS256")
    return DevTokenOut(token=token, expires_in=ttl)
