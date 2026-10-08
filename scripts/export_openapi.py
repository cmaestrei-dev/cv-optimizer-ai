"""Escribe el contrato de la API (OpenAPI) para generar los tipos del frontend.

    python scripts/export_openapi.py web/openapi.json && (cd web && npm run api:types)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")  # no se conecta: solo se arma la app
# El contrato incluye la entrada de desarrollo (la usa el frontend en local), con la misma configuración siempre.
os.environ.update({"AUTH_DEV_LOGIN": "1", "AUTH_DEV_SECRET": "x" * 40})
for name in ("AUTH_JWKS_URL", "API_PREFIX", "WEB_DIST"):
    os.environ.pop(name, None)

from api.main import create_app  # noqa: E402

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "web/openapi.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(create_app().openapi(), f, ensure_ascii=False, indent=1)
    print(f"OpenAPI → {out}")
