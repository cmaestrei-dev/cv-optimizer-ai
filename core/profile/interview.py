"""Entrevista guiada: preguntas concretas para fortalecer logros con datos que solo el usuario sabe.

1. La IA lee los logros de un cargo y pregunta por lo que falta (cifras, herramientas, resultados).
2. Con las respuestas propone mejoras.
3. El código verifica que cada cifra o nombre nuevo venga del texto original o de una respuesta.
"""

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from core.engine.verification import unsupported
from core.llm.client import LLMClient
from core.llm.structured import generate_structured
from core.profile.snapshot import ExperienceSnap

MAX_QUESTIONS = 6
_SKIP = re.compile(r"^\s*(no\s*s[eé]|n/?a|no aplica|ninguno|ninguna|-+|\.+)?\s*$", re.IGNORECASE)


def has_metric(text: str) -> bool:
    return bool(re.search(r"\d", text))


def strength(experience: ExperienceSnap) -> tuple[int, int]:
    """(logros con cifras, total de logros)."""
    return sum(has_metric(a.text) for a in experience.achievements), len(experience.achievements)


class Question(BaseModel):
    achievement_id: int | None = Field(default=None, description="Id del logro al que se refiere; null si es general")
    question: str = Field(description="Pregunta corta y concreta, en español, de tú")
    example: str = Field(default="", description="Ejemplo breve de respuesta")


class QuestionSet(BaseModel):
    questions: list[Question] = Field(default_factory=list)


class Proposal(BaseModel):
    achievement_id: int | None = Field(default=None, description="Id del logro mejorado; null si es un logro nuevo")
    text: str


class ProposalSet(BaseModel):
    proposals: list[Proposal] = Field(default_factory=list)


@dataclass
class CheckedProposal:
    achievement_id: int | None
    original: str
    proposed: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _achievement_lines(experience: ExperienceSnap) -> str:
    return "\n".join(f"{a.id}: {a.text}" for a in experience.achievements) or "(sin logros registrados)"


_QUESTIONS_PROMPT = """Eres un coach de empleabilidad. Ayuda a esta persona a fortalecer su experiencia \
con DATOS QUE SOLO ELLA SABE. No redactes nada todavía: solo pregunta.

CARGO: {role} en {company} ({period})
LOGROS ACTUALES (id: texto):
{achievements}

Haz como máximo {max_q} preguntas, priorizando los logros más débiles:
- Cifras: volumen (cuántas facturas, clientes, pedidos, personas), frecuencia, montos, tamaño del equipo.
- Herramientas o software que usaba para esa tarea.
- Resultados: qué mejoró gracias a su trabajo (tiempos, errores, ventas, satisfacción) y en cuánto, si lo sabe.
- Un logro o reconocimiento que no haya mencionado (pregunta general, achievement_id null).
No preguntes lo que ya está escrito. Preguntas cortas, de tú, con un ejemplo de respuesta."""

_PROPOSALS_PROMPT = """Reescribe los logros de este cargo usando SOLO el texto original y las \
respuestas de la persona. Si una respuesta está vacía o dice que no sabe, deja ese logro sin cambios \
(no lo incluyas).

CARGO: {role} en {company}
LOGROS ACTUALES (id: texto):
{achievements}

PREGUNTAS Y RESPUESTAS:
{answers}

Reglas:
1. Cada propuesta: una oración en primera persona del pasado, máximo 220 caracteres, sin punto final.
2. Incluye cifras, herramientas y resultados SOLO si aparecen en las respuestas o en el texto original. \
PROHIBIDO inventar o redondear cifras.
3. achievement_id = id del logro que mejora; null para un logro nuevo que surja de una respuesta.
4. Devuelve solo logros que realmente cambian."""


def generate_questions(llm: LLMClient, experience: ExperienceSnap) -> list[Question]:
    prompt = _QUESTIONS_PROMPT.format(
        role=experience.role, company=experience.company or "-", period=experience.period_text or "-",
        achievements=_achievement_lines(experience), max_q=MAX_QUESTIONS,
    )
    valid_ids = {a.id for a in experience.achievements}
    questions = generate_structured(llm, prompt, QuestionSet, cache=False).questions
    cleaned = []
    for q in questions[:MAX_QUESTIONS]:
        if q.question.strip():
            cleaned.append(q.model_copy(update={"achievement_id": q.achievement_id if q.achievement_id in valid_ids else None}))
    return cleaned


def propose_improvements(
    llm: LLMClient, experience: ExperienceSnap, answers: list[tuple[Question, str]]
) -> list[CheckedProposal]:
    answered = [(q, a.strip()) for q, a in answers if not _SKIP.match(a or "")]
    if not answered:
        return []
    answers_text = "\n".join(
        f"- [logro {q.achievement_id if q.achievement_id is not None else 'general'}] {q.question} → {a}"
        for q, a in answered
    )
    prompt = _PROPOSALS_PROMPT.format(
        role=experience.role, company=experience.company or "-",
        achievements=_achievement_lines(experience), answers=answers_text,
    )
    originals = {a.id: a.text for a in experience.achievements}
    all_answers = " ".join(a for _, a in answered)
    checked = []
    for p in generate_structured(llm, prompt, ProposalSet, cache=False).proposals:
        aid = p.achievement_id if p.achievement_id in originals else None
        original = originals.get(aid, "")
        text = p.text.strip().rstrip(".")
        if not text or text == original.rstrip("."):
            continue
        # Fuente válida: el logro original + lo que la persona respondió (+ cargo y empresa).
        source = f"{original} {all_answers} {experience.role} {experience.company}"
        checked.append(CheckedProposal(aid, original, text, unsupported(text, source)))
    return checked


def merge_achievements(experience: ExperienceSnap, accepted: list[CheckedProposal]) -> list[str]:
    """Lista final de logros: reemplaza los mejorados en su lugar y agrega los nuevos al final."""
    replacements = {p.achievement_id: p.proposed for p in accepted if p.achievement_id is not None}
    texts = [replacements.get(a.id, a.text) for a in experience.achievements]
    texts.extend(p.proposed for p in accepted if p.achievement_id is None)
    return texts
