"""Mensaje corto para el reclutador (correo, mensaje de LinkedIn o "carta de presentación" del portal).

Mismas garantías que el CV: solo datos del perfil y de la vacante, verificado; si no pasa, se usa un
mensaje armado únicamente con datos reales.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel

from core.engine.matching import MatchResult, profile_catalog
from core.engine.verification import unsupported
from core.engine.writing import LANGUAGE_NAMES, SOURCE_LANGUAGE
from core.llm.client import LLMClient
from core.llm.structured import generate_structured
from core.profile.snapshot import ProfileSnapshot
from core.vacancy import VacancyAnalysis

_ALLOWED_TERMS = "CV HV"  # "adjunto mi CV" es parte del mensaje, no un dato del perfil


class _Note(BaseModel):
    text: str


@dataclass
class CoverNote:
    text: str
    problems: list[str] = field(default_factory=list)
    fallback: bool = False


_PROMPT = """Escribe un mensaje breve (70 a 110 palabras) de {name} para el reclutador de la vacante \
"{role}"{company}. Idioma: {language}. Tono cordial y directo, sin exageraciones ni frases vacías.

Estructura: 1) a qué cargo se postula; 2) dos o tres fortalezas concretas que la vacante pide y que el \
perfil SÍ respalda (usa logros reales, con sus cifras si las tienen); 3) cierre invitando a conversar y \
mencionando que adjunta su CV.

Requisitos que el perfil cubre: {covered}
Años de experiencia (calculados): {years}

PERFIL (solo puedes usar esto):
{catalog}

PROHIBIDO inventar cifras, herramientas, empresas, logros o cualidades que no estén en el perfil."""


def write_cover_note(
    llm: LLMClient, vacancy: VacancyAnalysis, match: MatchResult, profile: ProfileSnapshot
) -> CoverNote:
    language_code = (vacancy.language or SOURCE_LANGUAGE).lower()[:2]
    catalog, _ = profile_catalog(profile)
    covered = "; ".join(m.requirement.text for m in match.requirements if m.level == "cubre") or "-"
    years = int(match.experience_years)
    prompt = _PROMPT.format(
        name=profile.full_name or "la persona candidata", role=vacancy.role,
        company=f" en {vacancy.company}" if vacancy.company else "",
        language=LANGUAGE_NAMES.get(language_code, "español"), covered=covered, years=years, catalog=catalog,
    )
    text = generate_structured(llm, prompt, _Note, cache=False).text.strip()
    source = f"{catalog} {vacancy.role} {vacancy.company} {profile.full_name} {covered} {_ALLOWED_TERMS}"
    problems = unsupported(text, source, strict=language_code == SOURCE_LANGUAGE,
                           extra_numbers={str(years), str(round(match.experience_years))})
    if not problems and text:
        return CoverNote(text)
    return CoverNote(fallback_note(vacancy, match, profile, language_code), problems, fallback=True)


def fallback_note(vacancy: VacancyAnalysis, match: MatchResult, profile: ProfileSnapshot, language_code: str) -> str:
    roles = ", ".join(list(dict.fromkeys(e.role for e in profile.experiences))[:2]) or "-"
    years = int(match.experience_years)
    company = f" en {vacancy.company}" if vacancy.company else ""
    if language_code == "en":
        return (f"Hello, I am applying for the {vacancy.role} position{company.replace(' en ', ' at ')}. "
                f"I have {years} years of experience as {roles}. I have attached my CV and would be glad to talk.")
    return (f"Hola, me postulo a la vacante de {vacancy.role}{company}. Tengo {years} años de experiencia como "
            f"{roles}. Adjunto mi hoja de vida y quedo atento(a) para conversar.")
