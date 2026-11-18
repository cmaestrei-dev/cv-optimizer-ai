"""Lectura ATS del PDF: el texto que extrae un lector de PDF debe estar completo, en orden y con tildes.

Los ATS no ven el diseño: leen la capa de texto. Esta prueba falla si un cambio de plantilla rompe eso
(versalitas que dejan el texto en minúsculas, columnas que mezclan el orden, ligaduras, caracteres perdidos).
"""

from core.engine.document import CVBullet, CVDocument, CVExperience, render
from models import UserProfile
from utils.pdf_extractor import extract_text_from_pdf

CONTACT = UserProfile(username="x", full_name="Camilo Maestre Ñúñez", email="camilo@example.com", phone="300 000 0000",
                      linkedin_url="https://www.linkedin.com/in/ejemplo", github_url="https://github.com/ejemplo",
                      headline="Desarrollador Full Stack | FastAPI | React", city="Cartagena, Colombia")


def _bullet(i: int, text: str) -> CVBullet:
    return CVBullet(achievement_id=i, text=text, original=text, score=1.0 - i / 100)


DOC = CVDocument(
    language="es",
    summary="Desarrollador de software con experiencia en APIs, pagos en línea y seguridad.",
    experiences=[
        CVExperience("Desarrollador Fullstack", "El Arte de Nicolás", "Mayo 2026 - Presente", "Colombia · Remoto", [
            _bullet(1, "Integré la pasarela Wompi con webhooks firmados y conciliación automática"),
            _bullet(2, "Modelé en PostgreSQL reservas y pagos con restricciones de unicidad"),
        ]),
        CVExperience("Analista de Ciberseguridad Jr", "Equimat", "Enero 2026 - Abril 2026", "Colombia", [
            _bullet(3, "Contuve una intrusión y endurecí 6 estaciones de trabajo con UFW"),
        ]),
    ],
    education=["Ingeniería de Sistemas - Universidad de Cartagena | 2022 - 2027"],
    skill_groups=[("Lenguajes de Programación", ["Python", "TypeScript"]), ("Bases de Datos", ["PostgreSQL", "MongoDB"])],
)


def _text() -> str:
    result = render(CVDocument.from_dict(DOC.to_dict()), CONTACT)
    assert result.pages == 1
    return extract_text_from_pdf(result.pdf) or ""


def test_every_field_is_in_the_text_layer():
    text = _text()
    for expected in ["Camilo Maestre Ñúñez", "Desarrollador Full Stack | FastAPI | React", "Cartagena, Colombia",
                     "camilo@example.com", "300 000 0000", "linkedin.com/in/ejemplo", "github.com/ejemplo",
                     "Integré la pasarela Wompi con webhooks firmados y conciliación automática",
                     "Mayo 2026 - Presente", "El Arte de Nicolás", "Ingeniería de Sistemas", "Universidad de Cartagena",
                     "2022 - 2027", "Lenguajes de Programación:", "Python, TypeScript"]:
        assert expected in text, f"falta en la capa de texto: {expected!r}"


def test_headings_are_real_uppercase_text_in_reading_order():
    text = _text()
    headings = ["PERFIL PROFESIONAL", "EXPERIENCIA LABORAL", "EDUCACIÓN", "HABILIDADES"]
    positions = [text.find(h) for h in headings]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions)
    # cada cargo va antes que su fecha y que sus viñetas; la experiencia más reciente primero
    assert text.find("Desarrollador Fullstack") < text.find("Mayo 2026") < text.find("Integré la pasarela")
    assert text.find("Integré la pasarela") < text.find("Analista de Ciberseguridad Jr")


def test_no_ligatures_or_replacement_characters():
    text = _text()
    assert not any(ch in text for ch in "ﬀﬁﬂﬃﬄ�")  # ﬀ ﬁ ﬂ ﬃ ﬄ y «�»
