"""Respuestas a las preguntas de filtro de los portales ("¿cuántos años de experiencia tienes en…?").

La IA responde SOLO con datos del perfil; lo que depende de la persona (aspiración salarial,
disponibilidad, documentos) se marca para que lo complete ella. Cada respuesta se verifica.
"""

import math

from pydantic import BaseModel, Field

from core.engine.matching import profile_catalog
from core.engine.verification import unsupported
from core.llm.client import LLMClient
from core.llm.structured import generate_structured
from core.profile.snapshot import ProfileSnapshot
from core.vacancy import VacancyAnalysis

MAX_QUESTIONS = 15


class ScreeningAnswer(BaseModel):
    question: str
    answer: str = Field(default="", description="Respuesta lista para pegar; vacía si depende de la persona")
    needs_you: bool = Field(
        default=False,
        description="true si la respuesta depende de algo que NO está en el perfil "
        "(salario, disponibilidad, licencia, documentos, preferencias)",
    )
    note: str = Field(default="", description="Para la persona: qué falta o en qué se basa la respuesta (máx. 20 palabras)")


class ScreeningAnswers(BaseModel):
    answers: list[ScreeningAnswer] = Field(default_factory=list)


_PROMPT = """Ayuda a esta persona a responder las preguntas del formulario de postulación de un portal \
de empleo, usando SOLO los datos de su perfil.

{vacancy}PERFIL (L# logro, H# habilidad, E# educación):
{catalog}

DURACIÓN DE CADA EMPLEO (calculada con sus fechas):
{durations}
Experiencia total: {total_years} años.

PREGUNTAS:
{questions}

Reglas:
1. Responde en primera persona, breve y lista para pegar en el formulario.
2. Para "¿cuántos años/meses de experiencia en X?": suma solo los empleos donde el perfil muestra X, \
usando las duraciones dadas. Si no hay evidencia de X, needs_you=true.
3. Si la pregunta depende de algo que no está en el perfil (aspiración salarial, disponibilidad, \
licencia, vehículo, documentos, preferencias), deja answer vacío, needs_you=true y explica en note qué responder.
4. PROHIBIDO inventar datos. Nunca afirmes una habilidad o experiencia que el perfil no muestre.
5. Una respuesta por pregunta, en el mismo orden."""


def _durations(profile: ProfileSnapshot) -> tuple[str, set[str]]:
    lines, numbers = [], set()
    for exp in profile.experiences:
        months = exp.period.months()
        if months is None:
            lines.append(f"- {exp.role} @ {exp.company}: sin fechas")
            continue
        years = round(months / 12, 1)
        numbers.update({str(months), f"{years:g}".replace(".", ""), str(int(years))})
        lines.append(f"- {exp.role} @ {exp.company} ({exp.period_text}): {months} meses ≈ {years:g} años")
    return "\n".join(lines) or "(sin empleos)", numbers


def answer_screening(
    llm: LLMClient, questions: list[str], profile: ProfileSnapshot, vacancy: VacancyAnalysis | None = None
) -> list[ScreeningAnswer]:
    questions = [q.strip() for q in questions if q.strip()][:MAX_QUESTIONS]
    if not questions:
        return []
    catalog, _ = profile_catalog(profile)
    durations, duration_numbers = _durations(profile)
    total_years = round(profile.total_experience_months() / 12, 1)
    prompt = _PROMPT.format(
        vacancy=f"VACANTE: {vacancy.role} — {vacancy.company}\n\n" if vacancy else "",
        catalog=catalog or "(vacío)", durations=durations, total_years=f"{total_years:g}",
        questions="\n".join(f"{i}. {q}" for i, q in enumerate(questions, start=1)),
    )
    answers = generate_structured(llm, prompt, ScreeningAnswers, cache=False).answers
    # Sumas de duraciones: se acepta cualquier cantidad de años/meses que no supere la experiencia total.
    max_years = math.ceil(total_years)
    allowed = duration_numbers | {str(n) for n in range(0, max(max_years, 0) + 1)}
    allowed |= {str(n) for n in range(0, profile.total_experience_months() + 1)}
    source = f"{catalog} {durations} {vacancy.role if vacancy else ''} {vacancy.company if vacancy else ''}"

    results = []
    for i, question in enumerate(questions):
        item = answers[i] if i < len(answers) else ScreeningAnswer(question=question, needs_you=True,
                                                                     note="Sin respuesta; complétala tú")
        item = item.model_copy(update={"question": question})
        if item.answer.strip():
            problems = unsupported(item.answer, source, extra_numbers=allowed)
            if problems:
                item = item.model_copy(update={
                    "needs_you": True,
                    "note": f"Revísala: incluye datos que no están en tu perfil ({'; '.join(problems)})",
                })
        results.append(item)
    return results
