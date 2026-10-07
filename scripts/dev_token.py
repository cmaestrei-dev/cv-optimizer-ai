"""Token de desarrollo para probar la API en local (nunca sirve con la base de producción).

    AUTH_DEV_SECRET=algo-largo python scripts/dev_token.py ana --email ana@example.com
    curl -H "Authorization: Bearer <token>" http://localhost:8000/me
"""

import argparse
import os
import sys
import time

import jwt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.auth import DEV_ISSUER  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("subject", help="Identificador de la cuenta de prueba")
    parser.add_argument("--email", default="")
    parser.add_argument("--hours", type=float, default=8)
    args = parser.parse_args()
    secret = os.environ.get("AUTH_DEV_SECRET", "")
    if len(secret) < 32:
        sys.exit("Define AUTH_DEV_SECRET (32 caracteres o más) igual que en la API.")
    now = int(time.time())
    claims = {"iss": DEV_ISSUER, "sub": args.subject, "email": args.email, "iat": now, "exp": now + int(args.hours * 3600)}
    print(jwt.encode(claims, secret, algorithm="HS256"))


if __name__ == "__main__":
    main()
