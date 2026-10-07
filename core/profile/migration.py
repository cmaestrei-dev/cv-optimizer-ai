"""Migración determinista (sin IA) del modelo Markdown anterior al perfil estructurado.

Solo lee el almacenamiento viejo y escribe en el nuevo: las tablas anteriores quedan intactas
como respaldo. Es idempotente: los usuarios que ya existen en el modelo nuevo se omiten.
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from core.profile import repository as repo
from core.profile.legacy import parse_education_markdown, parse_experience_markdown

logger = logging.getLogger(__name__)


@dataclass
class UserMigrationReport:
    username: str
    skipped: bool = False
    experiences: int = 0
    achievements: int = 0
    skills: int = 0
    duplicate_skills: int = 0
    education: int = 0
    warnings: list[str] = field(default_factory=list)


def migrate_user(session: Session, username: str, rows: dict) -> UserMigrationReport:
    """rows: salida de storage.export_profile_rows (profile, experiences, skills, education)."""
    report = UserMigrationReport(username=username)
    if repo.get_user(session, username) is not None:
        report.skipped = True
        return report

    profile = rows.get("profile") or {}
    user = repo.create_user(
        session, username, **{k: str(profile.get(k) or "") for k in repo.USER_FIELDS}
    )

    for content in rows.get("experiences", []):
        for parsed in parse_experience_markdown(content):
            if not parsed.period_text:
                report.warnings.append(f"Experiencia sin periodo: '{parsed.role}'")
            if parsed.role == "(Sin cargo)":
                report.warnings.append("Texto de experiencia sin encabezado '###'; revisar el cargo")
            repo.add_experience(
                session, user,
                role=parsed.role, company=parsed.company, period_text=parsed.period_text,
                country=parsed.country, modality=parsed.modality,
                achievements=parsed.achievements,
            )
            report.experiences += 1
            report.achievements += len([a for a in parsed.achievements if a.strip()])

    for name, category in rows.get("skills", []):
        if repo.add_skill(session, user, name, category or "Otros") is None:
            report.duplicate_skills += 1
        else:
            report.skills += 1

    for content in rows.get("education", []):
        for parsed in parse_education_markdown(content):
            repo.add_education(
                session, user, title=parsed.title, institution=parsed.institution,
                period_text=parsed.period_text, description=parsed.description,
            )
            report.education += 1

    session.flush()
    return report


def migrate_all(
    session: Session,
    usernames: Iterable[str],
    export_rows: Callable[[str], dict],
) -> list[UserMigrationReport]:
    reports = []
    for username in usernames:
        if repo.get_user(session, username) is not None:  # evita leer filas que no se usarán
            reports.append(UserMigrationReport(username=username, skipped=True))
            continue
        report = migrate_user(session, username, export_rows(username))
        logger.info("Migración %s: %s", username, report)
        reports.append(report)
    return reports
