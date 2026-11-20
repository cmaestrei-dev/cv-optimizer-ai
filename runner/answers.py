"""Respuestas para los formularios: banco de la persona, motor de preguntas de la app y emparejar con opciones.

Sin navegador ni red: todo se puede probar. La regla de oro se mantiene: lo que no sale del banco ni del
perfil (vía la app) no se responde, y la vacante se salta.
"""

import math
import re
import unicodedata

YEARS = re.compile(r"\b(cu[aá]nt[oa]s?|how many)\b.*\b(a[nñ]os|years?|meses|months?)\b", re.I)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_YES = {"si", "sí", "yes", "true", "1"}
_NO = {"no", "false", "0"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[*¿?¡!:]", " ", text)).strip()


def bank_answer(question: str, bank: dict[str, str]) -> str | None:
    """Respuesta del banco: cada clave es una lista de patrones separados por «|» (sin tildes)."""
    q = normalize(question)
    for patterns, value in bank.items():
        if any(p.strip() and normalize(p) in q for p in patterns.split("|")):
            return value
    return None


def is_years(question: str) -> bool:
    return bool(YEARS.search(normalize(question)))


def to_integer(answer: str) -> str | None:
    """«2,5 años» → «2»: hacia abajo, para nunca declarar más de lo que hay."""
    match = _NUMBER.search(answer or "")
    if not match:
        return None
    return str(math.floor(float(match.group(0).replace(",", "."))))


def pick_option(answer: str, options: list[str]) -> str | None:
    """La opción que corresponde a la respuesta (exacta, sí/no, o que la contiene). None si ninguna calza."""
    a = normalize(answer)
    if not a:
        return None
    clean = [(o, normalize(o)) for o in options if normalize(o) and not normalize(o).startswith(("selecciona", "select"))]
    for original, o in clean:
        if o == a:
            return original
    if a in _YES or a in _NO:
        wanted = _YES if a in _YES else _NO
        for original, o in clean:
            if o in wanted or o.split(" ")[0] in wanted:
                return original
        return None
    for original, o in clean:
        if a in o or o in a:
            return original
    return None


_EXPERIENCE = re.compile(r"\b(experiencia|conocimientos?|manejas?|manejo|has (trabajado|usado)|ha (trabajado|usado)|dominas?|"
                         r"sabes|experience|knowledge)\b")


def asks_experience(question: str) -> bool:
    """¿La pregunta es sobre experiencia o conocimiento de algo? (entonces «no la tengo» es una respuesta honesta)."""
    return bool(_EXPERIENCE.search(normalize(question)))
