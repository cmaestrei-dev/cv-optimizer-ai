from typing import Literal

from pydantic import BaseModel, Field

from core.llm.client import Image, LLMClient
from core.llm.structured import generate_structured


class NotAVacancyError(ValueError):
    pass


class Requirement(BaseModel):
    text: str = Field(description="Requisito tal como aparece en la vacante, en su idioma original")
    kind: Literal["obligatorio", "deseable"] = Field(
        description="'deseable' solo si la vacante lo marca como plus, deseable, valorado o similar"
    )
    category: Literal[
        "herramienta",
        "conocimiento",
        "habilidad_blanda",
        "experiencia",
        "formacion",
        "idioma",
        "certificacion",
        "otro",
    ]


class VacancyAnalysis(BaseModel):
    is_vacancy: bool = Field(description="false si la entrada no es una oferta de empleo")
    role: str = Field(default="", description="Cargo exacto, tal como aparece")
    company: str = Field(default="", description="Empresa; vacío si no aparece")
    language: str = Field(default="", description="Código ISO del idioma de la oferta: es, en, pt...")
    area: str = Field(
        default="",
        description="Área profesional en 1-3 palabras: Administrativa, Operaciones y logística, "
        "Ventas, Tecnología, Salud, Contabilidad...",
    )
    seniority: str = Field(default="", description="Nivel si se deduce: practicante, junior, semi-senior, senior, líder")
    location: str = Field(default="", description="Ciudad/país; vacío si no aparece")
    modality: str = Field(default="", description="Presencial, Híbrido o Remoto; vacío si no aparece")
    min_years_experience: float | None = Field(
        default=None, description="Años mínimos de experiencia exigidos; null si no se indican"
    )
    summary: str = Field(default="", description="Un párrafo con el propósito del puesto")
    requirements: list[Requirement] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(
        default_factory=list,
        description="Términos que un reclutador buscaría (herramientas, conocimientos, competencias), "
        "tal como aparecen en la oferta, sin duplicados",
    )

    @property
    def must_haves(self) -> list[Requirement]:
        return [r for r in self.requirements if r.kind == "obligatorio"]

    def to_legacy_markdown(self) -> str:
        """Formato que consumen los prompts actuales (ROLE/COMPANY/LANGUAGE/AREA + secciones)."""
        lines = [
            f"ROLE: {self.role}",
            f"COMPANY: {self.company or 'No especificada'}",
            f"LANGUAGE: {self.language}",
            f"AREA: {self.area}",
            "",
            "About the Role:",
            self.summary,
            "",
            "Requirements:",
            *[
                f"- {r.text}{' (deseable)' if r.kind == 'deseable' else ''}"
                for r in self.requirements
            ],
            "",
            "Responsibilities:",
            *[f"- {r}" for r in self.responsibilities],
        ]
        return "\n".join(lines).strip()


_PROMPT = """Analiza esta oferta de empleo (texto y/o imagen), de cualquier profesión o sector, \
y extrae sus datos como un sistema ATS.

Reglas:
1. Conserva los términos en el idioma original de la oferta; no los traduzcas.
2. Separa cada requisito en un elemento propio. Márcalo como "deseable" solo si la oferta lo \
presenta como plus, deseable, valorado o similar; si no, es "obligatorio".
3. No inventes datos: si algo no aparece, deja el campo vacío o null.
4. Si la entrada no es una oferta de empleo, devuelve is_vacancy=false y el resto vacío."""


def analyze_vacancy(
    llm: LLMClient,
    text: str = "",
    images: tuple[Image, ...] = (),
) -> VacancyAnalysis:
    if not text.strip() and not images:
        raise ValueError("Se necesita el texto o una imagen de la vacante.")
    prompt = _PROMPT
    if text.strip():
        prompt += f"\n\nTEXTO DE LA OFERTA:\n{text.strip()}"
    analysis = generate_structured(llm, prompt, VacancyAnalysis, images=images)
    if not analysis.is_vacancy:
        raise NotAVacancyError("La entrada no contiene información válida de una vacante.")
    return analysis
