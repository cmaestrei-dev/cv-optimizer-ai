"""Casos de uso del perfil para la UI (Streamlit hoy, FastAPI mañana).

Cada función abre y confirma su propia transacción y devuelve objetos ya cargados. La UI nunca
mantiene una sesión abierta: st.rerun() lanza una BaseException que, dentro de una sesión,
descartaría los cambios sin avisar.
"""

import hashlib
import logging
import re
import secrets
import threading

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from core.db import session_scope, upgrade_schema
from core.profile import repository as repo
from core.profile.importer import ImportedCV
from core.profile.links import with_scheme
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


SAAS_PREFIX = "saas:"


def account_username(subject: str, *, email: str = "", full_name: str = "") -> str:
    """Usuario interno de una cuenta del SaaS ("emisor|sub"); se crea la primera vez que entra."""
    for _ in range(2):  # dos primeras peticiones simultáneas: la segunda choca con la única y relee
        try:
            with session_scope() as s:
                user = s.scalar(select(User).where(User.auth_subject == subject))
                if user is None:
                    user = User(
                        # ":" no es válido en los nombres de perfil de Streamlit: nadie puede ocupar este antes.
                        username=SAAS_PREFIX + hashlib.sha256(subject.encode()).hexdigest()[:20], auth_subject=subject,
                        email=email.strip()[:200], full_name=full_name.strip()[:200],
                        # Contraseña local inutilizable: si una versión de Streamlit sin el filtro la listara,
                        # pediría una contraseña que nadie conoce en vez de abrirla.
                        password_hash=secrets.token_hex(32), salt=secrets.token_hex(32),
                    )
                    s.add(user)
                    s.flush()
                return user.username
        except IntegrityError:
            continue
    raise RuntimeError("No se pudo crear la cuenta")


class LinkError(ValueError):
    """No se pudo vincular el perfil anterior; el mensaje se muestra a la persona."""


def legacy_key(name: str) -> str:
    """Mismo nombre de perfil que crea Streamlit (ui/profile_form.py): minúsculas, espacios → "_"."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "", name.strip().lower().replace(" ", "_"))


_DUMMY_SALT = "00" * 32  # para que un perfil inexistente tarde lo mismo que una contraseña mala


def link_legacy_profile(subject: str, legacy_username: str, password: str) -> str:
    """Vincula un perfil de Streamlit (con su contraseña) a la cuenta del SaaS de `subject`.

    - Un solo mensaje para perfil inexistente, sin contraseña o contraseña mala (no revela qué existe).
    - La contraseña (PBKDF2, lento) se verifica FUERA de la transacción: no retiene conexiones.
    - Con la contraseña correcta se puede volver a vincular (mismo nivel de confianza que Streamlit):
      así un cambio de proveedor o de instancia de Clerk no deja el perfil huérfano.
    - El cambio es condicional (UPDATE … WHERE auth_subject = el leído): dos intentos simultáneos no se pisan.
    Devuelve el usuario interno resultante.
    """
    from models import UserProfile  # contraseña PBKDF2 de los perfiles de Streamlit

    wrong = LinkError("Usuario o contraseña incorrectos.")
    with session_scope() as s:
        legacy = repo.get_user(s, legacy_key(legacy_username))
        snapshot = (legacy.id, legacy.username, legacy.password_hash, legacy.salt, legacy.auth_subject) if legacy else None
    if snapshot is None or snapshot[1].startswith(SAAS_PREFIX):
        UserProfile(username="x", password_hash="0" * 64, salt=_DUMMY_SALT).verify_password(password)
        raise wrong
    legacy_id, username, password_hash, salt, linked_to = snapshot
    profile = UserProfile(username=username, password_hash=password_hash, salt=salt)
    if not profile.has_password:  # sin contraseña: mismo tiempo y mismo mensaje que una contraseña mala
        UserProfile(username="x", password_hash="0" * 64, salt=_DUMMY_SALT).verify_password(password)
        raise wrong
    if not profile.verify_password(password):
        raise wrong
    if linked_to == subject:
        return username
    with session_scope() as s:
        current = s.scalar(select(User).where(User.auth_subject == subject))
        if current is not None and current.id != legacy_id:
            if any(s.scalar(select(func.count()).select_from(m).where(m.user_id == current.id))
                   for m in (Experience, Skill, Education, _application_model())):
                raise LinkError("Tu cuenta nueva ya tiene datos. Vincula el perfil anterior antes de empezar a usarla.")
            s.delete(current)
            s.flush()  # libera auth_subject antes de asignarlo al perfil anterior
        condition = User.auth_subject.is_(None) if linked_to is None else User.auth_subject == linked_to
        moved = s.execute(update(User).where(User.id == legacy_id, condition).values(auth_subject=subject)).rowcount
        if moved != 1:  # otro intento lo vinculó entre la lectura y ahora
            raise LinkError("Ese perfil acaba de vincularse desde otra sesión. Intenta de nuevo.")
        return username


def _application_model():
    from core.tracking.models import Application  # el seguimiento depende del perfil, no al revés

    return Application


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
    with session_scope() as s:
        return apply_import_in(s, username, data, experiences=experiences, skills=skills, education=education,
                               fill_contact=fill_contact)


def apply_import_in(
    s, username: str, data: ImportedCV, *, experiences: list[int], skills: list[int], education: list[int],
    fill_contact: bool = False,
) -> dict[str, int]:
    """Lo mismo que `apply_import` dentro de una transacción ajena. Nunca duplica: compara con el perfil
    ACTUAL (no con el de cuando se leyó el PDF), así dos lecturas del mismo CV no suman dos veces."""
    counts = {"experiencias": 0, "logros": 0, "habilidades": 0, "estudios": 0}
    user = _require_user(s, username)
    have_exp = {(repo.skill_key(e.role), repo.skill_key(e.company)) for e in repo.list_experiences(s, user)}
    have_edu = {(repo.skill_key(e.title), repo.skill_key(e.institution)) for e in repo.list_education(s, user)}
    for i in dict.fromkeys(experiences):
        e = data.experiences[i]
        key = (repo.skill_key(e.role), repo.skill_key(e.company))
        if key in have_exp:
            continue
        have_exp.add(key)
        repo.add_experience(
            s, user, role=e.role, company=e.company, period_text=e.period_text,
            country=e.country, modality=e.modality, achievements=e.achievements,
        )
        counts["experiencias"] += 1
        counts["logros"] += len(e.achievements)
    for i in dict.fromkeys(skills):
        if repo.add_skill(s, user, data.skills[i].name, data.skills[i].category):
            counts["habilidades"] += 1
    for i in dict.fromkeys(education):
        e = data.education[i]
        key = (repo.skill_key(e.title), repo.skill_key(e.institution))
        if key in have_edu:
            continue
        have_edu.add(key)
        repo.add_education(s, user, title=e.title, institution=e.institution, period_text=e.period_text)
        counts["estudios"] += 1
    if fill_contact:
            for key in ("full_name", "email", "phone", "linkedin_url"):
                if not getattr(user, key) and getattr(data, key).strip():
                    value = getattr(data, key).strip()
                    setattr(user, key, with_scheme(value) if key == "linkedin_url" else value)
    s.flush()
    return counts
