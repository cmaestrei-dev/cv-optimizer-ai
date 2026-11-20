"""Respuestas para los formularios: banco de la persona, motor de preguntas de la app y emparejar con opciones.

Sin navegador ni red: todo se puede probar. Lo que no sale del banco ni del perfil (vía la app) no se responde y
la vacante se salta, salvo las preguntas de experiencia, que `sin_evidencia` decide.
"""

import math
import re
import unicodedata

YEARS = re.compile(r"\b(cu[aá]nt[oa]s?|how many)\b.*\b(a[nñ]os|years?|meses|months?)\b"
                   r"|\b(cu[aá]nto tiempo|how long)\b.*\b(experiencia|experience|trabaj|llevas)", re.I)
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


def asks_months(question: str) -> bool:
    """«¿Cuántos meses de experiencia…?»: la respuesta va en meses, no en años."""
    q = normalize(question)
    return bool(re.search(r"\b(meses|months?)\b", q)) and not re.search(r"\b(anos|years?)\b", q)


def to_integer(answer: str) -> str | None:
    """«2,5 años» → «2»: hacia abajo, para nunca declarar más de lo que hay."""
    match = _NUMBER.search(answer or "")
    if not match:
        return None
    return str(math.floor(float(match.group(0).replace(",", "."))))


_LESS = re.compile(r"\b(menos de|menor a|less than|under)\b|^<")
_MORE = re.compile(r"\b(mas de|mayor a|more than|over)\b|\+|^>")


def _span(option: str) -> tuple[float, float] | None:
    """Años que cubre una opción: «1 a 2 años» → (1, 2), «Menos de 1 año» → (0, 1), «Más de 5» → (5, ∞), «6 meses» → (0.5, 0.5)."""
    numbers = [float(n.replace(",", ".")) for n in _NUMBER.findall(option)]
    if not numbers:
        return (0.0, 0.0) if re.search(r"\b(ninguna|ninguno|sin experiencia|none|no tengo)\b", option) else None
    if re.search(r"\b(mes|meses|months?)\b", option) and not re.search(r"\b(ano|anos|years?)\b", option):
        numbers = [n / 12 for n in numbers]
    if _LESS.search(option):
        return 0.0, numbers[0]
    if _MORE.search(option):
        return numbers[0], math.inf
    return min(numbers), max(numbers)


def pick_years(years: int, options: list[str]) -> str | None:
    """La opción de años que contiene `years` («1 a 2 años» para 2); si ninguna, la más cercana."""
    spans = [(original, _span(o)) for original, o in ((x, normalize(x)) for x in options) if o]
    spans = [(original, s) for original, s in spans if s is not None]
    inside = [original for original, (low, high) in spans if low <= years <= high]
    if inside:
        return inside[0]
    return min(spans, key=lambda x: min(abs(years - x[1][0]), abs(years - x[1][1])))[0] if spans else None


def pick_option(answer: str, options: list[str]) -> str | None:
    """La opción que corresponde a la respuesta (exacta, sí/no, rango de años o que la contiene). None si ninguna calza."""
    a = normalize(answer)
    if not a:
        return None
    clean = [(o, normalize(o)) for o in options if normalize(o) and not normalize(o).startswith(("selecciona", "select"))]
    for original, o in clean:
        if o == a:
            return original
    if a.isdigit() and any(_NUMBER.search(o) for _, o in clean):
        return pick_years(int(a), [original for original, _ in clean])
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
    """¿La pregunta es sobre experiencia o conocimiento de algo? (la que `sin_evidencia` responde sin evidencia)."""
    return bool(_EXPERIENCE.search(normalize(question)))
