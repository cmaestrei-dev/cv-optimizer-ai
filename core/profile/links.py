"""Enlaces escritos por personas o copiados de un CV ("www.linkedin.com/in/ana" sin https://)."""

import re

_BARE_DOMAIN = re.compile(r"^[\w-]+(\.[\w-]+)+(:\d+)?(/\S*)?$")


def with_scheme(value: str) -> str:
    """Agrega https:// a un dominio sin esquema; lo demás queda igual (y lo valida quien lo use)."""
    value = value.strip()
    if value and "://" not in value and _BARE_DOMAIN.match(value):
        return "https://" + value
    return value


def safe_link(value: str) -> str:
    """Para mostrar: solo http(s). Un enlace guardado en otro esquema (p. ej. "javascript:") sale vacío."""
    value = with_scheme(value)
    return value if value.startswith(("https://", "http://")) else ""
