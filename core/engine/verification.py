"""Etapa 5 — verificación determinista de respaldo (anti-invención).

Una viñeta reescrita solo puede contener cifras y nombres propios / siglas / herramientas que ya
estén en su fuente. Es deliberadamente estricta: ante la duda, se usa el texto original del usuario.
"""

import re

from core.profile.repository import skill_key

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_TOKEN = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9#+&./-]*")
_SENTENCE_START = re.compile(r"(^|[.!?:;]\s+|\n)\s*$")
# Palabras que suelen ir en mayúscula sin ser datos (inicio tras viñeta, conectores en títulos).
_IGNORED = {"i", "y", "e", "o", "a", "de", "del", "la", "el", "los", "las", "en", "con", "para", "the", "and", "of", "in", "to"}


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

    source_key = f" {skill_key(re.sub(r'[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ#+&]+', ' ', source))} "
    seen = set()
    for match in _TOKEN.finditer(rewritten):
        token = match.group(0).rstrip(".-/")
        if not token or _NUMBER.fullmatch(token):
            continue
        at_start = bool(_SENTENCE_START.search(rewritten[: match.start()]))
        if not _is_term(token, at_start, strict):
            continue
        key = skill_key(re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ#+&]+", " ", token))
        if key and f" {key} " not in source_key and key not in seen:
            seen.add(key)
            problems.append(f"término sin respaldo: {token}")
    return problems
