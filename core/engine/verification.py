"""Etapa 5 — verificación determinista de respaldo (anti-invención).

Una viñeta reescrita solo puede contener cifras y nombres propios / siglas / herramientas que ya
estén en su fuente. Es deliberadamente estricta: ante la duda, se usa el texto original del usuario.
Las herramientas y metodologías conocidas cuentan aunque vayan en minúscula («agile», «docker»).
"""

import re
from functools import cache

from core.engine.skill_groups import vocabulary
from core.profile.repository import skill_key

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_TOKEN = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9#+&./-]*")
_SENTENCE_START = re.compile(r"(^|[.!?:;]\s+|\n)\s*$")
# Palabras que suelen ir en mayúscula sin ser datos (inicio tras viñeta, conectores en títulos).
_IGNORED = {"i", "y", "e", "o", "a", "de", "del", "la", "el", "los", "las", "en", "con", "para", "the", "and", "of", "in", "to"}


# Prácticas y metodologías que suelen escribirse en minúscula y afirman una experiencia (no son un adorno).
_PRACTICES = {"agile", "agil", "agiles", "scrum", "kanban", "lean", "six sigma", "itil", "devops", "devsecops", "tdd",
              "bdd", "microservicios", "microservices", "machine learning", "deep learning", "inteligencia artificial",
              "big data", "cloud computing", "pentesting", "ci/cd", "design thinking", "okr", "okrs"}


@cache
def _claims() -> frozenset[str]:
    """Términos que, si aparecen en el texto reescrito, tienen que estar en la fuente (sin letras sueltas: «c», «r»)."""
    terms = {_normalize(t) for t in vocabulary() | _PRACTICES}
    return frozenset(t for t in terms if len(t.replace(" ", "")) > 2)


def _normalize(text: str) -> str:
    return skill_key(re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ#+&]+", " ", text))


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[.,]", "", n) for n in _NUMBER.findall(text)}


def _is_term(token: str, at_sentence_start: bool, strict: bool) -> bool:
    letters = [c for c in token if c.isalpha()]
    if any(c.isdigit() for c in token) or any(c in "#+&" for c in token):
        return True
    if len(letters) >= 2 and all(c.isupper() for c in letters):
        return True  # sigla: SAP, CRM, ERP, NIIF
    if not strict:
        return False
    # En el mismo idioma: una palabra con mayúscula a mitad de frase es nombre propio o herramienta.
    return token[0].isupper() and not at_sentence_start and token.lower() not in _IGNORED


def unsupported(rewritten: str, source: str, *, strict: bool = True, extra_numbers: set[str] | None = None) -> list[str]:
    """Problemas de respaldo de `rewritten` frente a `source`; lista vacía = verificada."""
    problems = []
    allowed_numbers = _numbers(source) | (extra_numbers or set())
    for number in sorted(_numbers(rewritten) - allowed_numbers):
        problems.append(f"cifra sin respaldo: {number}")

    source_key = f" {_normalize(source)} "
    seen = set()
    rewritten_key = f" {_normalize(rewritten)} "
    for term in sorted(_claims()):  # herramientas y metodologías aunque vayan en minúscula
        if f" {term} " in rewritten_key and f" {term} " not in source_key:
            seen.add(term)
            problems.append(f"término sin respaldo: {term}")
    for match in _TOKEN.finditer(rewritten):
        token = match.group(0).rstrip(".-/")
        if not token or _NUMBER.fullmatch(token):
            continue
        at_start = bool(_SENTENCE_START.search(rewritten[: match.start()]))
        if not _is_term(token, at_start, strict):
            continue
        key = _normalize(token)
        if key and f" {key} " not in source_key and key not in seen:
            seen.add(key)
            problems.append(f"término sin respaldo: {token}")
    return problems
