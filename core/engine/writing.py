"""Etapa 4 — redacción controlada.

La IA solo reescribe viñetas y el resumen. Cargos, empresas, fechas, educación y habilidades salen
de los datos del usuario, así que no los puede inventar. Cada texto pasa por verification.py; lo
que no se respalda se corrige una vez y, si sigue fallando, se usa el texto original.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, Field

from core.engine.matching import MatchResult
from core.engine.selection import Selection
from core.engine.verification import unsupported
from core.llm.client import LLMClient
from core.llm.structured import generate_structured
from core.profile.snapshot import ProfileSnapshot
from core.vacancy import VacancyAnalysis

LANGUAGE_NAMES = {"es": "español", "en": "inglés", "pt": "portugués", "fr": "francés"}
SOURCE_LANGUAGE = "es"  # los perfiles se registran en español


class WrittenBullet(BaseModel):
    id: int
    text: str = Field(description="Viñeta reescrita, una oración")


class Draft(BaseModel):
    summary: str = Field(default="", description="Perfil profesional: 2 o 3 oraciones naturales")
    bullets: list[WrittenBullet] = Field(default_factory=list)


class SummaryDraft(BaseModel):
    summary: str = Field(description="Perfil profesional corregido: 2 o 3 oraciones naturales")


@dataclass
class WrittenCV:
    summary: str
    bullets: dict[int, str]
    reverted: dict[int, list[str]] = field(default_factory=dict)  # id -> motivos
    summary_problems: list[str] = field(default_factory=list)


_PROMPT = """Eres un redactor experto de CVs para cualquier profesión. Reescribe el contenido del \
candidato para esta vacante SIN INVENTAR NADA.

VACANTE: {role}{company} | Área: {area}
Palabras clave de la vacante: {keywords}
IDIOMA DEL CV: {language}
Enfoque pedido por el candidato: {focus}

LOGROS A REESCRIBIR (id | experiencia | requisitos de la vacante que respalda | texto original):
{bullets}

DATOS PARA EL RESUMEN:
- Años totales de experiencia (calculados): {years}
- Cargos reales: {roles}
- Formación: {education}
- Habilidades reales: {skills}
- Lo que la vacante pide y el candidato demuestra: {strengths}

REGLAS:
1. Cada viñeta usa SOLO hechos de su texto original. Puedes reordenar, acortar, traducir y nombrar \
lo mismo con el término que usa la vacante (sinónimo exacto), nada más. Adáptala a ESTA vacante: \
empieza por la parte del logro que respalda sus requisitos (la columna de requisitos) y deja de lado \
los detalles que a esta vacante no le importan.
2. PROHIBIDO agregar herramientas, software, empresas, cifras, porcentajes, resultados o \
responsabilidades que no estén en el texto original. Conserva las cifras tal cual: son lo que más vale.
3. Cada viñeta: una oración corta, idealmente de una línea (unos 100 caracteres y nunca más de 130), \
que empieza con un verbo de acción en pasado (primera persona en español). Sin la etiqueta inicial \
del original («Pagos:», «Calidad:»). No termines con punto.
4. Devuelve una viñeta por cada id recibido, con el mismo id.
5. Resumen (perfil profesional): 2 o 3 oraciones, entre 40 y 70 palabras, que suenen escritas por \
una persona para ESTA vacante, en primera persona implícita (sin «yo»):
   - Quién es: sus cargos reales, sus años y su formación. NUNCA empieces con el cargo de la vacante \
ni lo presentes como un cargo que tuvo; si lo nombras, solo como objetivo («para aportar como…»).
   - Qué aporta aquí: 3 a 5 habilidades reales que la vacante pide (no listes todas) y un logro \
concreto de los LOGROS que lo respalde, con su cifra tal cual si la tiene.
   - No copies frases de la vacante ni uses relleno: «apasionado», «proactivo», «orientado a \
resultados», «altamente motivado», «sólidos conocimientos», «amplia experiencia».
   - Solo datos de los DATOS PARA EL RESUMEN y de los logros: nada inventado.
6. Todo en {language}."""

_SUMMARY_REPAIR = """Corrige este perfil profesional de un CV para la vacante «{role}» (idioma: {language}).

Perfil actual: {summary}
Problemas: {problems}

Datos reales que puedes usar (nada más): cargos {roles}; años de experiencia {years}; formación {education}; \
habilidades {skills}; logros: {achievements}

Escribe 2 o 3 oraciones naturales (40 a 70 palabras), en primera persona implícita: quién es (cargos, \
años, formación), 3 a 5 habilidades que la vacante pide y un logro concreto con su cifra tal cual. No empieces \
con el cargo de la vacante, no listes todas las habilidades, no copies frases de la vacante ni uses relleno."""

_FILLER = ("apasionad", "proactiv", "orientado a resultados", "orientada a resultados", "altamente motivad",
           "solidos conocimientos", "amplia experiencia", "passionate", "results-driven", "highly motivated",
           "experto", "experta", "domino ", "expert ")  # «experto» exagera para un perfil junior (pasó el 2026-11-22)
_MIN_WORDS, _MAX_LISTED = 25, 7


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.]+", " ", text)).strip()


def _ongoing(edu, today: date | None = None) -> bool:
    today = today or date.today()
    return edu.period.is_current or bool(edu.period.end_year and edu.period.end_year > today.year)


def _education_text(profile: ProfileSnapshot, language_code: str) -> str:
    items = []
    for edu in profile.education[:3]:
        where = f", {edu.institution}" if edu.institution else ""
        status = ((" (in progress)" if language_code == "en" else " (en curso)") if _ongoing(edu) else "")
        items.append(f"{edu.title}{where}{status}")
    return "; ".join(items) or "-"


def summary_style_problems(summary: str, vacancy_role: str, real_roles: list[str], vacancy_texts: list[str]) -> list[str]:
    """Lo que hace sonar robótico o inútil un perfil (aparte de la verificación de datos): empezar con el cargo de
    la vacante como si fuera propio, ser muy corto, listar demasiadas habilidades, relleno o frases copiadas."""
    problems, text = [], _plain(summary)
    role = _plain(vacancy_role)
    if role and text.startswith(role) and not any(_plain(r) == role for r in real_roles):
        problems.append("empieza con el cargo de la vacante, que el candidato no ha tenido")
    if len(text.split()) < _MIN_WORDS:
        problems.append("es demasiado corto: no dice qué aporta el candidato")
    if max((len(part.split(",")) for part in re.split(r"[.;:](?:\s|$)", summary)), default=0) > _MAX_LISTED:
        problems.append("es una lista larga de habilidades: elige las 3 a 5 que pide la vacante")
    if filler := [f for f in _FILLER if f in text]:
        problems.append(f"usa relleno ({', '.join(filler)})")
    words = text.split()
    sources = [f" {_plain(t)} " for t in vacancy_texts if t]
    for i in range(len(words) - 5):
        chunk = " " + " ".join(words[i:i + 6]) + " "
        if any(chunk in s for s in sources):
            problems.append(f"copia una frase de la vacante («{chunk.strip()}»)")
            break
    return problems

# Conjugaciones que la IA inventa al volver verbo un sustantivo del original («auditoría» → «Auditorié»).
_VERB_FIXES = {"auditorié": "Audité", "auditoré": "Audité", "auditorie": "Audité"}
# Pretéritos irregulares que terminan en «e» sin tilde (los regulares en -ar la llevan: «Configuré», «Activé»).
_IRREGULAR_E = {
    "hice", "rehice", "deshice", "satisfice", "tuve", "obtuve", "mantuve", "estuve", "anduve", "contuve", "retuve",
    "detuve", "sostuve", "entretuve", "puse", "propuse", "compuse", "dispuse", "expuse", "supuse", "impuse", "repuse",
    "opuse", "pospuse", "produje", "conduje", "reduje", "traduje", "introduje", "deduje", "induje", "reproduje",
    "traje", "atraje", "extraje", "contraje", "distraje", "dije", "predije", "contradije", "pude", "supe", "cupe",
    "quise", "vine", "convine", "intervine", "previne", "provine", "hube",
}
# Palabras con que a veces empieza una viñeta y no son verbos.
_NOT_VERBS = {"desde", "durante", "mediante", "entre", "siempre", "sobre", "este", "base", "clave", "cliente", "parte"}


_LABEL = re.compile(r"^[A-ZÁÉÍÓÚÑ][\wáéíóúñü ()/-]{1,30}:\s+(?=\S)")


def _without_label(text: str) -> str:
    """El texto del usuario sin su etiqueta inicial («Alcance: sitio…» → «Sitio…»), para la viñeta que se deja tal cual.
    Una etiqueta tiene hasta 4 palabras y no empieza con un verbo en pasado («Atendí 30 clientes: …» se deja)."""
    match = _LABEL.match(text)
    label = match.group(0).rstrip(": \t") if match else ""
    if not match or len(label.split()) > 4 or label.split()[0][-1] in "éíó":
        return text
    rest = text[match.end():]
    return rest[:1].upper() + rest[1:]


def _fix_verbs(text: str, language: str = "es") -> str:
    """Corrige el verbo inicial: una forma inventada, o la tilde que falta en español («Configure» → «Configuré»:
    sin tilde es otro tiempo verbal)."""
    first, _, rest = text.partition(" ")
    fixed = _VERB_FIXES.get(first.lower())
    if not fixed and language == "es":
        word = first.lower()
        if len(word) >= 4 and word.isalpha() and word.endswith("e") and word not in _IRREGULAR_E | _NOT_VERBS:
            fixed = first[:-1] + "é"
    return f"{fixed} {rest}".rstrip() if fixed else text


_REPAIR = """Estas viñetas reescritas contienen datos que NO están en su texto original. \
Reescríbelas de nuevo usando SOLO el texto original (idioma: {language}). Mismo formato y reglas.

{items}"""


def _years_text(match: MatchResult) -> str:
    years = int(match.experience_years)
    return f"{years}" if years >= 1 else "menos de 1"


def write_cv(
    llm: LLMClient,
    vacancy: VacancyAnalysis,
    selection: Selection,
    match: MatchResult,
    profile: ProfileSnapshot,
    *,
    extra_focus: str = "",
) -> WrittenCV:
    language_code = (vacancy.language or SOURCE_LANGUAGE).lower()[:2]
    language = LANGUAGE_NAMES.get(language_code, vacancy.language or "español")
    requirement_texts = {i: m.requirement.text for i, m in enumerate(match.requirements, start=1)}

    originals: dict[int, str] = {}
    lines = []
    for sel in selection.experiences:
        header = f"{sel.experience.role} @ {sel.experience.company}" if sel.experience.company else sel.experience.role
        for a in sel.achievements:
            originals[a.id] = a.text
            reqs = "; ".join(
                requirement_texts[i] for i in sorted(match.achievement_requirements.get(a.id, ())) if i in requirement_texts
            ) or "-"
            lines.append(f"{a.id} | {header} | {reqs} | {a.text}")

    skills = [s.name for _, group in selection.skill_groups for s in group]
    roles = list(dict.fromkeys(e.role for e in profile.experiences))
    education = _education_text(profile, language_code)
    strengths = [m.requirement.text for m in match.requirements if m.level in ("cubre", "parcial")][:6]
    prompt = _PROMPT.format(
        role=vacancy.role,
        company=f" en {vacancy.company}" if vacancy.company else "",
        area=vacancy.area or "-",
        keywords=", ".join(vacancy.keywords) or "-",
        language=language,
        focus=extra_focus.strip() or "ninguno",
        bullets="\n".join(lines),
        years=_years_text(match),
        roles=", ".join(roles) or "-",
        education=education,
        skills=", ".join(skills) or "-",
        strengths="; ".join(strengths) or "-",
    )
    draft = generate_structured(llm, prompt, Draft, cache=False)

    strict = language_code == SOURCE_LANGUAGE
    written = {b.id: _fix_verbs(b.text.strip().rstrip("."), language_code) for b in draft.bullets if b.id in originals}
    problems = {
        aid: unsupported(written[aid], originals[aid], strict=strict) if aid in written else ["sin respuesta"]
        for aid in originals
    }
    failing = {aid: p for aid, p in problems.items() if p}

    if failing:
        items = "\n".join(
            f"{aid} | original: {originals[aid]} | tu versión: {written.get(aid, '-')} | problemas: {'; '.join(p)}"
            for aid, p in failing.items()
        )
        repaired = generate_structured(llm, _REPAIR.format(language=language, items=items), Draft, cache=False)
        for b in repaired.bullets:
            if b.id in failing:
                text = _fix_verbs(b.text.strip().rstrip("."), language_code)
                if not unsupported(text, originals[b.id], strict=strict):
                    written[b.id] = text
                    failing.pop(b.id)

    for aid in failing:
        written[aid] = _without_label(originals[aid]).rstrip(".")  # el texto del usuario nunca miente

    summary_source = " ".join(
        [
            *originals.values(), *written.values(), *skills, vacancy.role, vacancy.area,
            *(f"{e.role} {e.company}" for e in profile.experiences),
            *(f"{e.title} {e.institution}" for e in profile.education),
        ]
    )
    extra_numbers = {str(int(match.experience_years)), str(round(match.experience_years))}
    vacancy_texts = [vacancy.role, *(m.requirement.text for m in match.requirements), *vacancy.keywords]

    def check(text: str) -> tuple[list[str], list[str]]:
        if not text.strip():
            return ["sin resumen"], []
        return (unsupported(text, summary_source, strict=strict, extra_numbers=extra_numbers),
                summary_style_problems(text, vacancy.role, roles, vacancy_texts))

    summary = draft.summary.strip()
    summary_problems, style = check(summary)
    if summary_problems or style:  # una corrección: datos sin respaldo o un perfil robótico, corto o copiado
        try:
            fixed = generate_structured(llm, _SUMMARY_REPAIR.format(
                role=vacancy.role, language=language, summary=summary or "-",
                problems="; ".join(summary_problems + style), roles=", ".join(roles) or "-", years=_years_text(match),
                education=education, skills=", ".join(skills) or "-",
                achievements=" | ".join(list(written.values())[:6]) or "-"), SummaryDraft, cache=False).summary.strip()
        except Exception:  # noqa: BLE001 — si la corrección falla, se decide con lo que ya hay
            fixed = ""
        fixed_problems, fixed_style = check(fixed)
        if not fixed_problems and (summary_problems or len(fixed_style) <= len(style)):
            summary, summary_problems = fixed, []
    return WrittenCV(
        summary=summary if not summary_problems
        else fallback_summary(vacancy, match, profile, language_code, skills=_relevant(skills, vacancy_texts)),
        bullets=written,
        reverted=failing,
        summary_problems=summary_problems,
    )


def _relevant(skills: list[str], vacancy_texts: list[str], limit: int = 5) -> list[str]:
    """Las habilidades que nombra la vacante primero (sin repetir), hasta `limit`."""
    wanted = " " + " ".join(_plain(t) for t in vacancy_texts) + " "
    named = [s for s in skills if f" {_plain(s)} " in wanted]
    return list(dict.fromkeys(named + skills))[:limit]


def fallback_summary(vacancy: VacancyAnalysis, match: MatchResult, profile: ProfileSnapshot, language_code: str,
                     *, skills: list[str] | tuple[str, ...] = ()) -> str:
    """Resumen armado solo con datos reales, para cuando el de la IA no pasa la verificación: quién es (cargos,
    años y formación) y con qué trabaja. Nunca se presenta con el cargo de la vacante."""
    roles = list(dict.fromkeys(e.role for e in profile.experiences))[:2]
    years = match.experience_years
    edu = next((e for e in profile.education if _ongoing(e)), profile.education[0] if profile.education else None)
    skills = list(skills)[:5]

    def join(items: list[str], word: str) -> str:
        return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {word} {items[-1]}"

    if language_code == "en":
        span = "less than a year" if years < 1 else ("1 year" if int(years) == 1 else f"{int(years)} years")
        text = f"{join(roles, 'and')} with {span} of experience" if roles else "Professional"
        if edu:
            where = f" ({edu.institution})" if edu.institution else ""
            text += f"; {'currently studying' if _ongoing(edu) else 'education:'} {edu.title}{where}"
        return text + "." + (f" Hands-on work with {join(skills, 'and')}." if skills else "")
    span = "menos de un año" if years < 1 else ("1 año" if int(years) == 1 else f"{int(years)} años")
    text = f"{join(roles, 'y')} con {span} de experiencia" if roles else "Profesional"
    if edu:
        where = f" ({edu.institution})" if edu.institution else ""
        text += f"; {'estudio' if _ongoing(edu) else 'formación:'} {edu.title}{where}"
    return text + "." + (f" Trabajo con {join(skills, 'y')}." if skills else "")
