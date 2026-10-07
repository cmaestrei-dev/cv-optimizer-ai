"""Importación de un CV o del PDF de LinkedIn al perfil estructurado.

La IA solo EXTRAE (copia) datos del texto del PDF. El código verifica que cada logro y cada
habilidad aparezcan realmente en el PDF, descarta lo que no, y evita duplicar lo que el perfil ya tiene.
"""

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator

from config import SKILL_CATEGORIES
from core.engine.verification import unsupported
from core.llm.client import LLMClient
from core.llm.structured import generate_structured
from core.profile.repository import skill_key
from core.profile.snapshot import ProfileSnapshot


class ImportedExperience(BaseModel):
    role: str = Field(description="Cargo, tal como aparece")
    company: str = ""
    period_text: str = Field(default="", description="Periodo, ej. 'Enero 2022 - Presente' (sin la duración)")
    country: str = ""
    modality: str = Field(default="", description="Presencial, Híbrido o Remoto si aparece")
    achievements: list[str] = Field(
        default_factory=list,
        description="Funciones y logros COPIADOS del texto, uno por elemento; vacío si no hay descripción",
    )


class ImportedSkill(BaseModel):
    name: str
    category: str = Field(default="Otros", description=f"Una de: {', '.join(SKILL_CATEGORIES)}")

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        return value if value in SKILL_CATEGORIES else "Otros"


class ImportedEducation(BaseModel):
    title: str = Field(description="Título, carrera, curso o certificación")
    institution: str = ""
    period_text: str = ""


class ImportedCV(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    experiences: list[ImportedExperience] = Field(default_factory=list)
    skills: list[ImportedSkill] = Field(default_factory=list)
    education: list[ImportedEducation] = Field(default_factory=list)


_PROMPT = """Extrae los datos de este CV (puede ser el PDF que exporta LinkedIn). NO redactes ni \
mejores nada: copia los textos tal como están.

Reglas:
1. Experiencias: una por cargo (si en una empresa hubo varios cargos, uno por cargo). En el PDF de \
LinkedIn la empresa suele ir antes del cargo, y junto a las fechas aparece la duración entre \
paréntesis, p. ej. "(2 años 3 meses)": NO la incluyas en el periodo. "Present"/"actualidad" = "Presente".
2. Logros: copia cada función o logro de la descripción como un elemento, con sus palabras y cifras \
exactas. Si un cargo no tiene descripción, deja la lista vacía. No inventes funciones.
3. Habilidades: solo las que aparecen escritas (secciones como "Aptitudes principales", "Top Skills", \
"Idiomas", "Languages" o listas de herramientas). Los idiomas van en la categoría "Idiomas".
4. Educación: títulos, carreras, cursos y certificaciones ("Certifications"/"Licencias y certificaciones").
5. Si un dato no está, déjalo vacío.

TEXTO DEL CV:
{text}"""


def extract_cv(llm: LLMClient, pdf_text: str) -> ImportedCV:
    return generate_structured(llm, _PROMPT.format(text=pdf_text[:30000]), ImportedCV)


def _present(text: str, haystack_key: str) -> bool:
    key = skill_key(re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ#+&]+", " ", text))
    return bool(key) and f" {key} " in haystack_key


@dataclass
class ImportPlan:
    """Lo que se propone importar, con lo descartado y lo repetido explicados."""

    data: ImportedCV
    new_experiences: list[int] = field(default_factory=list)  # índices en data.experiences
    duplicate_experiences: list[int] = field(default_factory=list)
    new_skills: list[int] = field(default_factory=list)
    new_education: list[int] = field(default_factory=list)
    discarded: list[str] = field(default_factory=list)


def plan_import(imported: ImportedCV, pdf_text: str, profile: ProfileSnapshot) -> ImportPlan:
    haystack = f" {skill_key(re.sub(r'[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ#+&]+', ' ', pdf_text))} "
    plan = ImportPlan(data=imported)

    # Verificación: lo que no aparece en el PDF no se importa.
    for exp in imported.experiences:
        kept = []
        for achievement in exp.achievements:
            problems = unsupported(achievement, pdf_text)
            if problems:
                plan.discarded.append(f"Logro de {exp.role}: «{achievement[:60]}» ({'; '.join(problems)})")
            else:
                kept.append(achievement.strip())
        exp.achievements = [a for a in kept if a]
    skills = []
    for skill in imported.skills:
        if _present(skill.name, haystack):
            skills.append(skill)
        else:
            plan.discarded.append(f"Habilidad «{skill.name}»: no aparece escrita en el PDF")
    imported.skills = skills

    existing_exp = {(skill_key(e.role), skill_key(e.company)) for e in profile.experiences}
    for i, exp in enumerate(imported.experiences):
        if not exp.role.strip():
            continue
        target = plan.duplicate_experiences if (skill_key(exp.role), skill_key(exp.company)) in existing_exp else plan.new_experiences
        target.append(i)

    existing_skills = {skill_key(s.name) for s in profile.skills}
    seen = set(existing_skills)
    for i, skill in enumerate(imported.skills):
        key = skill_key(skill.name)
        if key and key not in seen:
            seen.add(key)
            plan.new_skills.append(i)

    existing_edu = {(skill_key(e.title), skill_key(e.institution)) for e in profile.education}
    plan.new_education = [
        i for i, e in enumerate(imported.education)
        if e.title.strip() and (skill_key(e.title), skill_key(e.institution)) not in existing_edu
    ]
    return plan
