"""Cuentas de la API: tokens JWT de un proveedor de identidad (OIDC), verificados con su JWKS.

La API no maneja contraseñas. El proveedor (Google, correo...) autentica a la persona y firma el
token; aquí solo se verifican firma, emisor, audiencia y vigencia. Cambiar de proveedor = cambiar
estas variables:

- AUTH_JWKS_URL, AUTH_ISSUER y AUTH_AUDIENCE o AUTH_AUTHORIZED_PARTIES: producción. Uno de los dos
  últimos es obligatorio: con un proveedor compartido (p. ej. Google), sin ellos cualquier otra app que
  reciba el token de una persona podría reutilizarlo aquí. Clerk no pone `aud` sino `azp` (el origen
  de la web que pidió el token): AUTH_AUTHORIZED_PARTIES = orígenes permitidos, separados por comas.
- AUTH_DEV_SECRET: tokens HS256 firmados en local (`scripts/dev_token.py`). Se rechaza si la base
  es Postgres: un secreto de desarrollo nunca debe abrir datos reales.
"""

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.db import database_url
from core.profile import service as profiles

logger = logging.getLogger(__name__)

DEV_ISSUER = "dev"
_ASYMMETRIC = ["RS256", "ES256", "EdDSA"]
_bearer = HTTPBearer(auto_error=False)


class AuthConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Account:
    subject: str  # "emisor|sub": estable aunque cambie el correo
    username: str  # clave interna que usan los servicios del núcleo
    email: str


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=10)


def decode_token(token: str) -> dict:
    """Claims del token verificado. Lanza jwt.InvalidTokenError (token malo) o AuthConfigError."""
    required = {"require": ["exp", "iss", "sub"]}
    if jwks_url := _env("AUTH_JWKS_URL"):
        issuer, audience = _env("AUTH_ISSUER"), _env("AUTH_AUDIENCE")
        parties = {p.strip().rstrip("/") for p in _env("AUTH_AUTHORIZED_PARTIES").split(",") if p.strip()}
        if not issuer or not (audience or parties):
            raise AuthConfigError("Faltan AUTH_ISSUER y AUTH_AUDIENCE o AUTH_AUTHORIZED_PARTIES")
        # Con el PyJWK (no solo su llave), PyJWT exige que el algoritmo del token sea el de esa llave.
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key, algorithms=_ASYMMETRIC, issuer=issuer, audience=audience or None,
            options={"require": ["exp", "iss", "sub", *(["aud"] if audience else [])], "verify_aud": bool(audience)},
            leeway=30,
        )
        if parties and str(claims.get("azp", "")).rstrip("/") not in parties:  # sin azp: se rechaza
            raise jwt.InvalidTokenError("azp no autorizado")
        return claims
    if secret := _env("AUTH_DEV_SECRET"):
        if database_url().startswith("postgresql"):
            raise AuthConfigError("AUTH_DEV_SECRET no se permite con la base de producción")
        if len(secret) < 32:
            raise AuthConfigError("AUTH_DEV_SECRET debe tener al menos 32 caracteres")
        return jwt.decode(token, secret, algorithms=["HS256"], issuer=DEV_ISSUER, options=required)
    raise AuthConfigError("La autenticación no está configurada (AUTH_JWKS_URL o AUTH_DEV_SECRET)")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def current_account(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> Account:
    if credentials is None:
        raise _unauthorized("Falta el token de acceso")
    try:
        claims = decode_token(credentials.credentials)
    except AuthConfigError:
        logger.exception("Autenticación mal configurada")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El inicio de sesión no está disponible") from None
    except jwt.PyJWKClientConnectionError:
        logger.exception("No se pudo leer el JWKS del proveedor de identidad")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El inicio de sesión no está disponible") from None
    except jwt.PyJWTError:  # firma, emisor, audiencia, vencimiento, algoritmo o llave desconocida
        raise _unauthorized("Token inválido o vencido") from None
    subject = f"{claims['iss']}|{claims['sub']}"
    email = claims.get("email", "") if isinstance(claims.get("email"), str) else ""
    name = claims.get("name", "") if isinstance(claims.get("name"), str) else ""
    return Account(subject, profiles.account_username(subject, email=email, full_name=name), email)


CurrentAccount = Annotated[Account, Depends(current_account)]
