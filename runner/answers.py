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
    first = lambda s: re.split(r"[\s,.;:]+", s, maxsplit=1)[0]  # noqa: E731 — «Sí, tengo…» → «si»
    if a in _YES or a in _NO or first(a) in (_YES | _NO) - {"1", "0"}:
        wanted = _YES if (a in _YES or first(a) in _YES) else _NO
        for original, o in clean:
            if o in wanted or first(o) in wanted:
                return original
        if a in _YES or a in _NO:
            return None  # un «sí» o «no» solo no se parece a ninguna otra opción
    for original, o in clean:
        if a in o or o in a:
            return original
    stems = lambda s: {w[:6] for w in re.findall(r"[a-z]{5,}", s)}  # noqa: E731 — «universitario» ~ «universitaria»
    scored = [(len(stems(o) & stems(a)), original) for original, o in clean]
    best = max((s for s, _ in scored), default=0)
    winners = [original for s, original in scored if s == best]
    return winners[0] if best and len(winners) == 1 else None


_NEGATIVE = {"no", "ninguno", "ninguna", "nada", "sin", "nunca", "none", "never"}
_MIDDLE = ("intermedio", "intermedia", "intermediate", "medio", "media")
_LOW = ("basico", "basica", "basic", "bajo", "baja", "poco", "poca", "principiante")


def negative(option: str) -> bool:
    words = normalize(option).split()
    return bool(words) and words[0].strip(",.;:") in _NEGATIVE


def favorable_option(options: list[str]) -> str | None:
    """En una pregunta de experiencia (decisión del dueño: «sí» cuando le favorece): la opción afirmativa; si no hay,
    un nivel intermedio; si no, la primera que no sea negativa ni de nivel bajo. None si todas son negativas."""
    clean = [o for o in options if normalize(o) and not normalize(o).startswith(("selecciona", "select"))]
    first = lambda o: normalize(o).split()[0].strip(",.;:")  # noqa: E731
    for o in clean:
        if first(o) in _YES - {"1"}:
            return o
    for o in clean:
        if first(o) in _MIDDLE:
            return o
    positive = [o for o in clean if not negative(o)]
    return next((o for o in positive if first(o) not in _LOW), positive[0] if positive else None)


_EXPERIENCE = re.compile(r"\b(experienc\w*|conocimientos?|manejas?|manejo|(has|ha|haz) (trabajado|usado|tenido)|dominas?|"
                         r"sabes|knowledge)\b")  # «experienc…» también con errores («¿haz tenido experiencien…?»)


def asks_experience(question: str) -> bool:
    """¿La pregunta es sobre experiencia o conocimiento de algo? (la que `sin_evidencia` responde sin evidencia)."""
    return bool(_EXPERIENCE.search(normalize(question)))


# --- Aspiración salarial según la vacante (decisión del dueño, 2026-11-22) ---
# «Decídela tú según la vacante y mi experiencia; si es solo para el perfil de la plataforma, 3 millones.»
SALARY_DEFAULT = 3_000_000
_EXPECTED = ("aspiracion salarial", "expectativa salarial", "pretension salarial", "salario esperado", "salario deseado",
             "aspiracion economica", "expectativa economica", "cuanto esperas ganar", "cuanto aspiras", "expected salary",
             "salary expectation", "desired salary")
_INTERNSHIP = re.compile(r"\b(practicante|practica|pasante|pasantia|aprendiz|intern|internship|trainee|estudiante en practica)\b")
# Cifras en pesos: «$2.500.000», «2500000 COP», «3 millones», «2,8 a 3,2 millones». Solo cuentan si llevan moneda o si
# van justo después de una palabra de sueldo: las ofertas hablan de «11.000.000 de transacciones» o de teléfonos.
_MONEY = re.compile(r"(?<![\d.,])(\$\s*|cop\s*)?(\d{1,3}(?:[.,]\d{3}){1,2}|\d{7,8})(?![\d.,]*\d)(\s*(?:cop|pesos))?"
                    r"|(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:(?:a|y|-|–)\s*(\d+(?:[.,]\d+)?)\s*)?millones")
_PAY = re.compile(r"(salari|sueldo|remuneraci|asignaci|compensaci|ingreso|pago mensual|salary|rango)")


def asks_expected_salary(question: str) -> bool:
    """«¿Cuál es tu aspiración salarial?» (no el salario actual o el último)."""
    q = normalize(question)
    return any(p in q for p in _EXPECTED) and not re.search(r"\b(actual|ultimo|anterior|current|last)\b", q)


def _amounts(text: str) -> list[int]:
    t, out = normalize(text), []
    for m in _MONEY.finditer(t):
        if m.group(4):  # «N millones» o «N a M millones»
            values = [float(v.replace(",", ".")) * 1_000_000 for v in (m.group(4), m.group(5)) if v]
        else:
            if not (m.group(1) or m.group(3) or _PAY.search(t[max(0, m.start() - 60):m.start()])):
                continue
            values = [float(re.sub(r"[.,]", "", m.group(2)))]
        out.extend(int(v) for v in values if 1_000_000 <= v <= 20_000_000)  # sueldo mensual en pesos
    return out


def expected_salary(vacancy_text: str, title: str = "", *, default: int = SALARY_DEFAULT) -> int | None:
    """La aspiración para esta vacante: dentro del rango que publica (el punto medio) o su cifra; sin cifra, `default`.
    Para prácticas no se da cifra (None): el apoyo de sostenimiento lo fija la empresa."""
    amounts = _amounts(vacancy_text)
    if amounts:
        value = (min(amounts) + max(amounts)) / 2 if len(amounts) > 1 else amounts[0]
        return int(round(value / 100_000) * 100_000)
    if _INTERNSHIP.search(normalize(title)):
        return None
    return default
