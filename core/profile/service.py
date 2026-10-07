"""Casos de uso del perfil para la UI (Streamlit hoy, FastAPI mañana).

Cada función abre y confirma su propia transacción y devuelve objetos ya cargados. La UI nunca
mantiene una sesión abierta: st.rerun() lanza una BaseException que, dentro de una sesión,
descartaría los cambios sin avisar.
"""

import logging
import threading

from sqlalchemy import func, select

from core.db import session_scope, upgrade_schema
from core.profile import repository as repo
from core.profile.importer import ImportedCV
from core.profile.models import Education, Experience, Skill, User
from core.profile.snapshot import (
    AchievementSnap,
    EducationSnap,
    ExperienceSnap,
    ProfileSnapshot,
    SkillSnap,
)

logger = logging.getLogger(__name__)

_ready_lock = threading.Lock()
_ready = False


def ensure_ready() -> None:
    """Aplica las migraciones de esquema pendientes (una vez por proceso)."""
    global _ready
    with _ready_lock:
        if not _ready:
            upgrade_schema()
            _ready = True


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


def append_achievements(username: str, experience_id: int, texts: list[str]) -> int:
    with session_scope() as s:
        return repo.append_achievements(s, _require_user(s, username), experience_id, texts)


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


def apply_import(
    username: str,
    data: ImportedCV,
    *,
    experiences: list[int],
    skills: list[int],
    education: list[int],
    fill_contact: bool = False,
) -> dict[str, int]:
    """Guarda lo elegido de una importación en una sola transacción (todo o nada)."""
    counts = {"experiencias": 0, "logros": 0, "habilidades": 0, "estudios": 0}
    with session_scope() as s:
        user = _require_user(s, username)
        for i in experiences:
            e = data.experiences[i]
            repo.add_experience(
                s, user, role=e.role, company=e.company, period_text=e.period_text,
                country=e.country, modality=e.modality, achievements=e.achievements,
            )
            counts["experiencias"] += 1
            counts["logros"] += len(e.achievements)
        for i in skills:
            if repo.add_skill(s, user, data.skills[i].name, data.skills[i].category):
                counts["habilidades"] += 1
        for i in education:
            e = data.education[i]
            repo.add_education(s, user, title=e.title, institution=e.institution, period_text=e.period_text)
            counts["estudios"] += 1
        if fill_contact:
            for key in ("full_name", "email", "phone", "linkedin_url"):
                if not getattr(user, key) and getattr(data, key).strip():
                    setattr(user, key, getattr(data, key).strip())
    return counts
