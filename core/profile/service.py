"""Casos de uso del perfil para la UI (Streamlit hoy, FastAPI mañana).

Cada función abre y confirma su propia transacción y devuelve objetos ya cargados. La UI nunca
mantiene una sesión abierta: st.rerun() lanza una BaseException que, dentro de una sesión,
descartaría los cambios sin avisar.
"""

import logging
import threading
from collections.abc import Callable

from sqlalchemy import func, select

from core.db import session_scope, upgrade_schema
from core.profile import repository as repo
from core.profile.legacy import (
    render_education_markdown,
    render_experiences_markdown,
    render_skills_markdown,
)
from core.profile.migration import UserMigrationReport, migrate_all
from core.profile.models import AppMeta, Education, Experience, Skill, User
from core.profile.snapshot import (
    AchievementSnap,
    EducationSnap,
    ExperienceSnap,
    ProfileSnapshot,
    SkillSnap,
)

logger = logging.getLogger(__name__)

_LEGACY_MIGRATED_KEY = "legacy_migrated"
_ready_lock = threading.Lock()
_ready = False


def ensure_ready(
    legacy_usernames: Callable[[], list[str]],
    legacy_export: Callable[[str], dict],
    *,
    migrate_legacy: bool = True,
) -> list[UserMigrationReport]:
    """Aplica migraciones de esquema y, una única vez, importa los perfiles del almacenamiento anterior.

    Con migrate_legacy=False solo prepara el esquema y NO marca la migración como hecha, para que
    la fuente correcta pueda migrar después.
    """
    global _ready
    with _ready_lock:
        if _ready:
            return []
        upgrade_schema()
        reports: list[UserMigrationReport] = []
        if not migrate_legacy:
            _ready = True
            return reports
        with session_scope() as session:
            if session.get(AppMeta, _LEGACY_MIGRATED_KEY) is None:
                reports = migrate_all(session, legacy_usernames(), legacy_export)
                session.add(AppMeta(key=_LEGACY_MIGRATED_KEY, value=str(len(reports))))
        _ready = True
        return reports


# ── usuarios ──────────────────────────────────────────────────────────


def list_usernames() -> list[str]:
    with session_scope() as s:
        return repo.list_usernames(s)


def get_user(username: str) -> User | None:
    with session_scope() as s:
        return repo.get_user(s, username)


def create_user(username: str, **fields: str) -> None:
    with session_scope() as s:
        repo.create_user(s, username, **fields)


def update_user(username: str, **fields: str) -> None:
    with session_scope() as s:
        user = _require_user(s, username)
        repo.update_user(s, user, **fields)


def delete_user(username: str) -> None:
    with session_scope() as s:
        repo.delete_user(s, username)


def profile_status(username: str) -> tuple[bool, bool, bool]:
    """(tiene experiencia, tiene habilidades, tiene educación)."""
    with session_scope() as s:
        user = repo.get_user(s, username)
        if user is None:
            return False, False, False

        def count(model) -> int:
            return s.scalar(select(func.count()).select_from(model).where(model.user_id == user.id))

        return count(Experience) > 0, count(Skill) > 0, count(Education) > 0


def _require_user(session, username: str) -> User:
    user = repo.get_user(session, username)
    if user is None:
        raise repo.NotFoundError(f"Usuario {username}")
    return user


# ── experiencias ──────────────────────────────────────────────────────


def list_experiences(username: str) -> list[Experience]:
    with session_scope() as s:
        return repo.list_experiences(s, _require_user(s, username))


def add_experience(username: str, **fields) -> None:
    with session_scope() as s:
        repo.add_experience(s, _require_user(s, username), **fields)


def update_experience(username: str, experience_id: int, achievements: list[str], **fields: str) -> None:
    with session_scope() as s:
        experience = repo.update_experience(s, _require_user(s, username), experience_id, **fields)
        repo.replace_achievements(s, experience, achievements)


def delete_experience(username: str, experience_id: int) -> None:
    with session_scope() as s:
        repo.delete_experience(s, _require_user(s, username), experience_id)


# ── habilidades ───────────────────────────────────────────────────────


def list_skills(username: str) -> list[Skill]:
    with session_scope() as s:
        return repo.list_skills(s, _require_user(s, username))


def add_skill(username: str, name: str, category: str = "Otros") -> bool:
    """False si ya existía."""
    with session_scope() as s:
        return repo.add_skill(s, _require_user(s, username), name, category) is not None


def delete_skill(username: str, skill_id: int) -> None:
    with session_scope() as s:
        repo.delete_skill(s, _require_user(s, username), skill_id)


# ── educación ─────────────────────────────────────────────────────────


def list_education(username: str) -> list[Education]:
    with session_scope() as s:
        return repo.list_education(s, _require_user(s, username))


def add_education(username: str, **fields: str) -> None:
    with session_scope() as s:
        repo.add_education(s, _require_user(s, username), **fields)


def delete_education(username: str, education_id: int) -> None:
    with session_scope() as s:
        repo.delete_education(s, _require_user(s, username), education_id)


# ── puente con el generador actual ────────────────────────────────────


def legacy_markdown(username: str) -> tuple[str, str, str]:
    """(experiencias, habilidades, educación) en el Markdown que esperan los prompts actuales."""
    with session_scope() as s:
        user = _require_user(s, username)
        return (
            render_experiences_markdown(repo.list_experiences(s, user)),
            render_skills_markdown(repo.list_skills(s, user)),
            render_education_markdown(repo.list_education(s, user)),
        )


def snapshot(username: str) -> ProfileSnapshot:
    """Foto del perfil para el motor de CV (sin objetos de base de datos)."""
    with session_scope() as s:
        user = _require_user(s, username)
        return ProfileSnapshot(
            username=user.username,
            full_name=user.full_name,
            experiences=tuple(
                ExperienceSnap(
                    id=e.id, role=e.role, company=e.company, period_text=e.period_text,
                    period=e.period, country=e.country, modality=e.modality,
                    achievements=tuple(AchievementSnap(a.id, a.text) for a in e.achievements),
                )
                for e in repo.list_experiences(s, user)
            ),
            skills=tuple(SkillSnap(k.id, k.name, k.category) for k in repo.list_skills(s, user)),
            education=tuple(
                EducationSnap(
                    id=d.id, title=d.title, institution=d.institution,
                    period_text=d.period_text, period=d.period, description=d.description,
                )
                for d in repo.list_education(s, user)
            ),
        )
