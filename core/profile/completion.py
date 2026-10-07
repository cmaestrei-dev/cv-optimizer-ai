"""Completar el perfil con lo que la persona hizo pero no escribió.

Tres ayudas, todas con la misma garantía: un logro solo se guarda si cada cifra, sigla y nombre
propio sale de las palabras del usuario (o de una tarea que él confirmó haber hecho).

- split_into_achievements: "cuéntamelo como te salga" → logros separados.
- typical_tasks + merge_task_details: lista de tareas típicas del cargo para reconocer lo olvidado.
- (en la UI) brechas de una vacante → "sí lo he hecho, así" → split_into_achievements.
"""

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from core.engine.verification import unsupported
from core.llm.client import LLMClient
from core.llm.structured import generate_structured
from core.profile.repository import skill_key
from core.profile.snapshot import ExperienceSnap

_WORD = re.compile(r"[a-z0-9áéíóúñü+#]{3,}")
DUPLICATE_THRESHOLD = 0.6


@dataclass
class Candidate:
    text: str
    problems: list[str] = field(default_factory=list)
    duplicate_of: str | None = None

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def suggested(self) -> bool:
        return self.ok and self.duplicate_of is None


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(skill_key(text)))


def find_duplicate(text: str, existing: list[str]) -> str | None:
    """Un logro existente casi igual (Jaccard de palabras ≥ 0.6), o None."""
    tokens = _tokens(text)
    for other in existing:
        other_tokens = _tokens(other)
        union = tokens | other_tokens
        if union and len(tokens & other_tokens) / len(union) >= DUPLICATE_THRESHOLD:
            return other
    return None


def _check(texts: list[str], source: str, experience: ExperienceSnap) -> list[Candidate]:
    existing = [a.text for a in experience.achievements]
    candidates, seen = [], set()
    for raw in texts:
        text = raw.strip().rstrip(".")
        key = skill_key(text)
        if not text or key in seen:
            continue
        seen.add(key)
        problems = unsupported(text, f"{source} {experience.role} {experience.company}")
        candidates.append(Candidate(text, problems, find_duplicate(text, existing + [c.text for c in candidates])))
    return candidates


class AchievementList(BaseModel):
    achievements: list[str] = Field(default_factory=list)


_SPLIT_PROMPT = """Separa en logros individuales lo que esta persona cuenta de su trabajo como \
{role} en {company}. Escribió como le salió; tu tarea es ordenar, no agregar.

{context}TEXTO DE LA PERSONA:
{text}

Reglas:
1. Un logro por cada tarea, responsabilidad o resultado distinto que mencione.
2. Redacción profesional en primera persona del pasado ("hacía las facturas" → "Elaboré las facturas"), \
en español de Colombia, máximo 200 caracteres, sin punto final. Cambia expresiones coloquiales por \
el término del oficio con el mismo significado ("los que debían plata" → "clientes con saldos pendientes").
3. Usa SOLO lo que la persona dijo: conserva sus cifras, herramientas y nombres exactamente. \
PROHIBIDO agregar cifras, herramientas, resultados o responsabilidades que no mencionó.
4. Si el texto no describe trabajo, devuelve la lista vacía."""


def split_into_achievements(
    llm: LLMClient, experience: ExperienceSnap, raw_text: str, *, context: str = ""
) -> list[Candidate]:
    if not raw_text.strip():
        return []
    prompt = _SPLIT_PROMPT.format(
        role=experience.role, company=experience.company or "-", text=raw_text.strip(),
        context=f"CONTEXTO: {context}\n\n" if context else "",
    )
    result = generate_structured(llm, prompt, AchievementList, cache=False)
    return _check(result.achievements, raw_text, experience)


class TaskList(BaseModel):
    tasks: list[str] = Field(default_factory=list)


_TASKS_PROMPT = """Lista entre 10 y 14 tareas que suele hacer una persona con el cargo de {role} \
en {company}{period}, para que la persona MARQUE cuáles hizo y así recuerde lo que olvidó poner en su CV.

Ya tiene escrito esto (no lo repitas):
{existing}

Reglas:
1. Cada tarea en primera persona del pasado (español de Colombia, "yo": "Actualicé", nunca voseo) y \
genérica: SIN cifras, SIN marcas de software y SIN resultados (eso lo agrega la persona si aplica). \
Ej.: "Elaboré facturas de venta".
2. Tareas concretas del oficio y del sector de la empresa, de las más comunes a las menos.
3. Máximo 120 caracteres cada una, sin punto final."""


def typical_tasks(llm: LLMClient, experience: ExperienceSnap) -> list[str]:
    existing = "\n".join(f"- {a.text}" for a in experience.achievements) or "(nada)"
    prompt = _TASKS_PROMPT.format(
        role=experience.role, company=experience.company or "su empresa",
        period=f" ({experience.period_text})" if experience.period_text else "", existing=existing,
    )
    tasks = generate_structured(llm, prompt, TaskList).tasks
    existing_texts = [a.text for a in experience.achievements]
    cleaned = []
    for task in tasks:
        task = task.strip().rstrip(".")
        if task and not find_duplicate(task, existing_texts + cleaned):
            cleaned.append(task)
    return cleaned[:14]


_MERGE_PROMPT = """Cada línea tiene una tarea que la persona confirmó haber hecho y un detalle que \
ella agregó. Escribe un logro por línea que combine la tarea con TODO el detalle (conserva cada \
cifra y nombre del detalle), usando SOLO esas palabras: no agregues cifras, herramientas ni \
resultados. Primera persona del pasado, máximo 220 caracteres, sin punto final. Devuelve exactamente \
un logro por línea, en el mismo orden.

{items}"""


def merge_task_details(
    llm: LLMClient, experience: ExperienceSnap, items: list[tuple[str, str]]
) -> list[Candidate]:
    """items: (tarea confirmada, detalle opcional). Sin detalle, la tarea se usa tal cual."""
    plain = [task for task, detail in items if not detail.strip()]
    detailed = [(task, detail.strip()) for task, detail in items if detail.strip()]
    texts, source = list(plain), " ".join(plain)
    if detailed:
        lines = "\n".join(f"{i}. Tarea: {t} | Detalle: {d}" for i, (t, d) in enumerate(detailed, start=1))
        merged = generate_structured(llm, _MERGE_PROMPT.format(items=lines), AchievementList, cache=False).achievements
        if len(merged) != len(detailed):
            merged = [""] * len(detailed)
        for (task, detail), text in zip(detailed, merged, strict=True):
            # Si la IA perdió una cifra del detalle, se conserva todo tal cual: el dato de la persona manda.
            lost = set(re.findall(r"\d+", detail)) - set(re.findall(r"\d+", text))
            texts.append(f"{task} ({detail})" if lost or not text.strip() else text)
        source += " " + " ".join(f"{t} {d}" for t, d in detailed)
    return _check(texts, source, experience)
