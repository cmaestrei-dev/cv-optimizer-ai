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
    reverted: dict[int, list[str]] = field(default_factory=dict)  # id -> motivos (datos sin respaldo)
    summary_problems: list[str] = field(default_factory=list)
    # Viñetas que quedaron con el texto del usuario porque la IA insistía en sonar a IA (no inventaban nada).
    restyled: dict[int, list[str]] = field(default_factory=dict)


BULLET_CHARS = 100  # lo que cabe en una línea de viñeta a 10 pt (medido: entre 105 y 110 caracteres)
BULLET_MAX = 105


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
2. PROHIBIDO agregar herramientas, software, empresas, cifras, porcentajes, resultados, propósitos o \
responsabilidades que no estén en el texto original. Conserva las cifras tal cual: son lo que más vale.
3. Cada viñeta en UNA línea: entre 60 y {max_chars} caracteres, nunca más. Escríbela como la contaría la persona, \
con palabras simples y concretas y frases completas (con sus artículos: «una API», «el sitio»; nada de estilo \
telegrama): verbo en pasado (primera persona en español) + qué hizo + para qué o con qué resultado, solo si el \
original lo dice. Si no cabe todo, quita detalles: nunca amontones datos ni cambies el sentido. Si suena más \
natural, puede abrir con un contexto breve del original («Cuando hubo una intrusión en la red, la contuve…») o con \
«Me encargué de…». Sin la etiqueta inicial del original («Pagos:», «Calidad:»). No termines con punto. No empieces \
dos viñetas seguidas con el mismo verbo y evita los verbos vacíos («Realicé», «Utilicé», «Ejecuté») si hay uno preciso.
4. Que no suene a IA: nada de «garantizando», «optimizando», «impulsando», «potenciando», «aportando valor», \
«sinergia», «de manera eficiente», «robusto», «de alta calidad», «exitosamente», ni rayas largas (—). No cierres \
una frase con un gerundio («…, mejorando la calidad»): usa «para» + verbo o deja solo lo que hizo.
5. Devuelve una viñeta por cada id recibido, con el mismo id.
6. Resumen (perfil profesional): 2 o 3 oraciones, entre 40 y 70 palabras, que suenen escritas por \
una persona para ESTA vacante, en primera persona implícita (sin «yo»):
   - Quién es: sus cargos reales, sus años y su formación. NUNCA empieces con el cargo de la vacante \
ni lo presentes como un cargo que tuvo; si lo nombras, solo como objetivo («para aportar como…»).
   - Qué aporta aquí: 3 a 5 habilidades reales que la vacante pide (no listes todas) y un logro \
concreto de los LOGROS que lo respalde, con su cifra tal cual si la tiene.
   - No copies frases de la vacante ni uses relleno: «apasionado», «proactivo», «orientado a \
resultados», «altamente motivado», «sólidos conocimientos», «amplia experiencia», «domino», «experto», ni las \
muletillas de la regla 4 (tampoco gerundios al final de una frase).
   - Solo datos de los DATOS PARA EL RESUMEN y de los logros: nada inventado.
7. Todo en {language}."""

_SUMMARY_REPAIR = """Corrige este perfil profesional de un CV para la vacante «{role}» (idioma: {language}).

Perfil actual: {summary}
Problemas: {problems}

Datos reales que puedes usar (nada más): cargos {roles}; años de experiencia {years}; formación {education}; \
habilidades {skills}; logros: {achievements}

Escribe 2 o 3 oraciones naturales (40 a 70 palabras), en primera persona implícita: quién es (cargos, \
años, formación), 3 a 5 habilidades que la vacante pide y un logro concreto con su cifra tal cual. No empieces \
con el cargo de la vacante, no listes todas las habilidades, no copies frases de la vacante ni uses relleno, \
muletillas de IA («impulsando», «de manera eficiente», «aportando valor»…), rayas largas ni gerundios al final."""

# Relleno y muletillas que delatan un texto hecho con IA (v3, 2026-11-28: el dueño pidió hojas de vida que suenen
# escritas por una persona). Se comparan sin tildes ni mayúsculas, desde el inicio de una palabra; en una viñeta solo
# cuentan si no estaban en el texto del usuario. «experto» exagera para un perfil junior (pasó el 2026-11-22).
_FILLER = (
    "apasionad", "proactiv", "orientado a resultados", "orientada a resultados", "altamente motivad",
    "solidos conocimientos", "amplia experiencia", "experto", "experta", "domino", "sinergia", "impulsando", "impulsar",
    "impulse", "potenciando", "potenciar", "potencie", "aportando valor", "aportar valor", "valor agregado",
    "de manera eficiente", "de forma eficiente", "de manera efectiva", "de forma efectiva", "eficaz y eficiente",
    "robust", "de alta calidad", "exitosamente", "con exito", "innovador", "vanguardia", "excepcional", "meticulos",
    "garantizando", "asegurando", "optimizando", "fomentando", "aprovechando", "maximizando", "contribuyendo",
    "passionate", "results driven", "highly motivated", "expert", "synerg", "leverag", "spearhead", "seamless",
    "cutting edge", "detail oriented", "proven track record", "ensuring", "fostering", "showcasing", "blindar",
    "blindando", "integral",
)
_DASHES = ("—", " – ")
_GERUND_TAIL = re.compile(r",\s+([a-záéíóúñ]+(?:ando|iendo|yendo))\b")
_GERUND_CLAUSE = re.compile(r",\s+([a-záéíóúñ]+(?:ando|iendo|yendo))\b[^.;:]*")
_DOMINO = re.compile(r"\b([Dd])omino\b")
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


def _filler(text: str, original: str = "") -> list[str]:
    plain, source = f" {_plain(text)} ", f" {_plain(original)} "
    return [f for f in _FILLER if f" {f}" in plain and f" {f}" not in source]


def style_problems(text: str, original: str = "", language: str = "es") -> list[str]:
    """Lo que hace sonar a IA un texto del CV y no estaba en el del usuario: relleno o muletillas, rayas largas y frases
    que cierran con un gerundio («…, garantizando la calidad»)."""
    problems = []
    if found := _filler(text, original):
        problems.append(f"usa relleno o muletillas de IA ({', '.join(found)})")
    if any(d in text for d in _DASHES) and not any(d in original for d in _DASHES):
        problems.append("usa rayas largas (—)")
    if language == "es":
        tails = [g for g in _GERUND_TAIL.findall(text.lower()) if g not in original.lower()]
        if tails:
            problems.append(f"cierra con un gerundio («…, {tails[0]}…»): usa «para» + verbo o deja solo lo que hizo")
    return problems


def tidy(text: str, original: str = "", language: str = "es") -> str:
    """Arreglos sin IA que solo quitan o cambian una palabra, para lo que la corrección no arregló: la frase en gerundio
    que agregó la IA (si no trae cifras: esas valen), las rayas largas y «Domino» (exagera: «Manejo»)."""
    if language != "es":
        return text
    low = original.lower()

    def cut(m: re.Match) -> str:
        return m.group(0) if m.group(1) in low or any(c.isdigit() for c in m.group(0)) else ""

    text = _GERUND_CLAUSE.sub(cut, text)
    if not any(d in original for d in _DASHES):
        text = re.sub(r"\s*(—|\s–\s)\s*", ", ", text)
    if "domino" not in _plain(original):
        text = _DOMINO.sub(lambda m: "Manejo" if m.group(1) == "D" else "manejo", text)
    return re.sub(r"\s+([.,;])", r"\1", text).strip(" ,")


def summary_style_problems(summary: str, vacancy_role: str, real_roles: list[str], vacancy_texts: list[str],
                           language: str = "es", source: str = "") -> list[str]:
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
    problems += style_problems(summary, source, language)
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
_NOT_VERBS = {"desde", "durante", "mediante", "entre", "siempre", "sobre", "este", "base", "clave", "cliente", "parte",
              "ante", "donde", "frente", "aunque", "porque", "pese", "mientras"}


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


_REPAIR = """Corrige estas viñetas de un CV (idioma: {language}). Cada una trae su texto original, tu versión y sus \
problemas. Reescríbelas usando SOLO los hechos del texto original: nada de herramientas, cifras, resultados ni \
propósitos que no estén ahí. Una línea por viñeta (máximo {max_chars} caracteres), con el verbo en pasado, como la \
contaría la persona: qué hizo y, si el original lo dice, para qué. Sin etiqueta inicial, sin muletillas de IA, sin \
rayas largas y sin cerrar con un gerundio. No termines con punto. Devuelve cada una con su mismo id.

{items}"""


def _clean(text: str, language: str) -> str:
    return _fix_verbs(_without_label(text.strip().rstrip(".").strip()), language)


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
        max_chars=BULLET_CHARS,
        years=_years_text(match),
        roles=", ".join(roles) or "-",
        education=education,
        skills=", ".join(skills) or "-",
        strengths="; ".join(strengths) or "-",
    )
    draft = generate_structured(llm, prompt, Draft, cache=False)

    strict = language_code == SOURCE_LANGUAGE
    written = {b.id: _clean(b.text, language_code) for b in draft.bullets if b.id in originals}
    failing = {}  # datos sin respaldo: van a `reverted`
    styled = {}  # suena a IA: si no se corrige, queda el texto del usuario (no inventa, así que no cuenta como inventado)
    long = set()  # más de una línea: se pide acortar, pero una versión limpia larga se conserva
    for aid in originals:
        if aid not in written:
            failing[aid] = ["sin respuesta"]
        elif problems := unsupported(written[aid], originals[aid], strict=strict):
            failing[aid] = problems
        else:
            if problems := style_problems(written[aid], originals[aid], language_code):
                styled[aid] = problems
            if len(written[aid]) > BULLET_MAX:
                long.add(aid)

    to_fix = {aid: [*failing.get(aid, []), *styled.get(aid, []),
                    *([f"pasa de {BULLET_MAX} caracteres: déjala en una línea"] if aid in long else [])]
              for aid in originals if aid in failing or aid in styled or aid in long}
    if to_fix:
        items = "\n".join(
            f"{aid} | original: {originals[aid]} | tu versión: {written.get(aid, '-')} | problemas: {'; '.join(p)}"
            for aid, p in to_fix.items()
        )
        try:
            repaired = generate_structured(llm, _REPAIR.format(language=language, items=items, max_chars=BULLET_CHARS),
                                           Draft, cache=False).bullets
        except Exception:  # noqa: BLE001 — sin la corrección se decide con lo que ya hay
            repaired = []
        for b in repaired:
            if b.id not in to_fix:
                continue
            text = _clean(b.text, language_code)
            if unsupported(text, originals[b.id], strict=strict) or style_problems(text, originals[b.id], language_code):
                continue
            if b.id in failing or b.id in styled or len(text) < len(written[b.id]):
                written[b.id] = text
                failing.pop(b.id, None)
                styled.pop(b.id, None)

    for aid in list(styled):  # solo le sobraba un gerundio o una raya: se quitan sin IA
        text = tidy(written[aid], originals[aid], language_code)
        if not style_problems(text, originals[aid], language_code) and not unsupported(text, originals[aid], strict=strict):
            written[aid] = text
            styled.pop(aid)

    for aid in [*failing, *styled]:
        written[aid] = _without_label(originals[aid]).rstrip(".")  # el texto del usuario nunca miente ni suena a IA

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
                summary_style_problems(text, vacancy.role, roles, vacancy_texts, language_code, summary_source))

    summary = tidy(draft.summary.strip(), summary_source, language_code)
    summary_problems, style = check(summary)
    if summary_problems or style:  # una corrección: datos sin respaldo o un perfil robótico, corto o copiado
        try:
            fixed = generate_structured(llm, _SUMMARY_REPAIR.format(
                role=vacancy.role, language=language, summary=summary or "-",
                problems="; ".join(summary_problems + style), roles=", ".join(roles) or "-", years=_years_text(match),
                education=education, skills=", ".join(skills) or "-",
                achievements=" | ".join(list(written.values())[:6]) or "-"), SummaryDraft, cache=False).summary.strip()
            fixed = tidy(fixed, summary_source, language_code)
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
        restyled=styled,
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
