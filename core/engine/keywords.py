"""Palabras clave de la vacante en el CV: la línea «Competencias clave» y la cobertura (v3, 2026-11-28).

Sin IA. Una palabra clave entra en la línea solo si el perfil la respalda tal cual, como palabra completa, así que no
puede colar nada que la persona no tenga (nunca texto oculto: lo que lee el ATS es lo que ve el reclutador). La
cobertura se mide sobre el CV ya recortado a una página y dice qué falta: lo que la persona tiene y no salió, y lo
que la vacante pide y no está en su perfil (para agregarlo si es cierto).
"""

import re
from dataclasses import dataclass, field

from core.engine.selection import is_degree_title
from core.profile.repository import skill_key
from core.profile.snapshot import ProfileSnapshot
from core.vacancy import VacancyAnalysis

LINE_CHARS = 200  # unas dos líneas de la hoja: la línea es para leerla de un vistazo, no un volcado
_SEPARATORS = re.compile(r"[^a-z0-9#+]+")


def _key(text: str) -> str:
    """Forma comparable: sin tildes ni signos y en singular («APIs REST» = «API REST», «Node.js» = «node js»)."""
    words = _SEPARATORS.sub(" ", skill_key(text)).split()
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "js")) else w for w in words)


def _variants(keyword: str) -> set[str]:
    """La misma herramienta escrita de otra forma: «ReactJS» / «React.js» / «React», «Node JS» / «NodeJS»."""
    key = _key(keyword)
    if not key:
        return set()
    compact = key.replace(" ", "")
    found = {key, compact}
    for form in (key, compact):
        if len(form) > 4 and form.endswith("js"):
            found.add(form[:-2].rstrip(" "))
    return {v for v in found if v}


def _contains(text_key: str, keyword: str) -> bool:
    padded = f" {text_key} "
    return any(f" {v} " in padded for v in _variants(keyword))


def profile_text(profile: ProfileSnapshot) -> str:
    """Todo lo que respalda una palabra clave: logros, cargos, habilidades y estudios."""
    parts = [f"{e.role} {e.company}" for e in profile.experiences]
    parts += [a.text for e in profile.experiences for a in e.achievements]
    parts += [s.name for s in profile.skills]
    parts += [f"{d.title} {d.institution}" for d in profile.education]
    # Cada habilidad también en sus otras formas: «ReactJS» respalda «React» y «Node.js» respalda «NodeJS».
    forms = [v for s in profile.skills for v in _variants(s.name)]
    return " | ".join([_key(" | ".join(parts)), *forms])


def _unique(keywords: list[str]) -> list[str]:
    seen, out = set(), []
    for k in keywords:
        key = _key(k)
        if key and key not in seen:
            seen.add(key)
            out.append(k.strip())
    return out


def _is_title(keyword: str, profile: ProfileSnapshot) -> bool:
    """Un título o un cargo («Ingeniería de Sistemas», «Desarrollador Fullstack») no es una competencia: ya sale en su
    sección y cuenta para la cobertura. Un tema que aparece en ellos («Ciberseguridad») sí lo es."""
    key = _key(keyword)
    names = {_key(e.role) for e in profile.experiences} | {_key(d.title) for d in profile.education}
    return key in names or is_degree_title(keyword)


def key_skills(vacancy: VacancyAnalysis, profile: ProfileSnapshot, *, limit: int = 12) -> list[str]:
    """La línea «Competencias clave»: lo que el perfil respalda, en el orden de la vacante y hasta unas dos líneas."""
    text = profile_text(profile)
    chosen, used = [], 0
    for k in (k for k in _unique(vacancy.keywords) if _contains(text, k) and not _is_title(k, profile)):
        if len(chosen) >= limit or used + len(k) + 3 > LINE_CHARS:
            break
        chosen.append(k[:1].upper() + k[1:])  # «pruebas unitarias» → «Pruebas unitarias»: la escritura de la vacante
        used += len(k) + 3
    return chosen


@dataclass
class KeywordReport:
    present: list[str] = field(default_factory=list)
    missing_owned: list[str] = field(default_factory=list)  # la persona las tiene y no salieron en esta hoja
    missing: list[str] = field(default_factory=list)  # la vacante las pide y no están en el perfil

    @property
    def total(self) -> int:
        return len(self.present) + len(self.missing_owned) + len(self.missing)

    @property
    def coverage(self) -> int:
        """Porcentaje de las palabras clave de la vacante que muestra el CV (100 si la vacante no trae)."""
        return round(100 * len(self.present) / self.total) if self.total else 100

    def to_dict(self) -> dict:
        return {"coverage": self.coverage, "total": self.total, "present": self.present,
                "missing_owned": self.missing_owned, "missing": self.missing}


def coverage(cv_text: str, vacancy: VacancyAnalysis, profile: ProfileSnapshot) -> KeywordReport:
    owned = profile_text(profile)
    text = _key(cv_text)
    report = KeywordReport()
    for k in _unique(vacancy.keywords):
        if _contains(text, k):
            report.present.append(k)
        elif _contains(owned, k):
            report.missing_owned.append(k)
        else:
            report.missing.append(k)
    return report
