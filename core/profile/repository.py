import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.profile.models import Achievement, Education, Experience, Skill, User

USER_FIELDS = ("full_name", "email", "phone", "linkedin_url", "github_url", "password_hash", "salt")


class UserExistsError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


def skill_key(name: str) -> str:
    """'  Excel  Avanzado ' y 'excel avanzado' son la misma habilidad."""
    text = unicodedata.normalize("NFKD", name.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


# ── usuarios ──────────────────────────────────────────────────────────


def list_usernames(session: Session) -> list[str]:
    return list(session.scalars(select(User.username).order_by(User.username)))


def get_user(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def create_user(session: Session, username: str, **fields: str) -> User:
    if get_user(session, username) is not None:
        raise UserExistsError(username)
    user = User(username=username, **{k: v for k, v in fields.items() if k in USER_FIELDS})
    session.add(user)
    session.flush()
    return user


def update_user(session: Session, user: User, **fields: str) -> None:
    for key, value in fields.items():
        if key in USER_FIELDS:
            setattr(user, key, value)


def delete_user(session: Session, username: str) -> None:
    user = get_user(session, username)
    if user is not None:
        session.delete(user)


# ── experiencias y logros ─────────────────────────────────────────────


def list_experiences(session: Session, user: User) -> list[Experience]:
    rows = session.scalars(
        select(Experience)
        .where(Experience.user_id == user.id)
        .options(selectinload(Experience.achievements))
    ).all()
    return sorted(rows, key=lambda e: (e.period.sort_key, e.id), reverse=True)


def _owned_experience(session: Session, user: User, experience_id: int) -> Experience:
    experience = session.scalar(
        select(Experience).where(Experience.id == experience_id, Experience.user_id == user.id)
    )
    if experience is None:
        raise NotFoundError(f"Experiencia {experience_id}")
    return experience


def add_experience(
    session: Session,
    user: User,
    *,
    role: str,
    company: str = "",
    period_text: str = "",
    country: str = "",
    modality: str = "",
    achievements: list[str] | None = None,
) -> Experience:
    experience = Experience(
        user_id=user.id, role=role.strip(), company=company.strip(),
        country=country.strip(), modality=modality.strip(),
    )
    experience.set_period(period_text)
    session.add(experience)
    session.flush()
    replace_achievements(session, experience, achievements or [])
    return experience


def update_experience(session: Session, user: User, experience_id: int, **fields: str) -> Experience:
    experience = _owned_experience(session, user, experience_id)
    for key in ("role", "company", "country", "modality"):
        if key in fields:
            setattr(experience, key, fields[key].strip())
    if "period_text" in fields:
        experience.set_period(fields["period_text"])
    return experience


def replace_achievements(session: Session, experience: Experience, texts: list[str]) -> None:
    experience.achievements.clear()
    session.flush()
    for position, text in enumerate(t.strip() for t in texts):
        if text:
            experience.achievements.append(Achievement(text=text, position=position))
    session.flush()


def append_achievements(session: Session, user: User, experience_id: int, texts: list[str]) -> int:
    """Agrega logros al final de un cargo del usuario. Devuelve cuántos agregó."""
    experience = _owned_experience(session, user, experience_id)
    start = max((a.position for a in experience.achievements), default=-1) + 1
    added = 0
    for text in (t.strip() for t in texts):
        if text:
            experience.achievements.append(Achievement(text=text, position=start + added))
            added += 1
    session.flush()
    return added


def delete_experience(session: Session, user: User, experience_id: int) -> None:
    session.delete(_owned_experience(session, user, experience_id))


# ── habilidades ───────────────────────────────────────────────────────


def list_skills(session: Session, user: User) -> list[Skill]:
    return list(
        session.scalars(select(Skill).where(Skill.user_id == user.id).order_by(Skill.id))
    )


def add_skill(session: Session, user: User, name: str, category: str = "Otros") -> Skill | None:
    """Devuelve None si el usuario ya tiene esa habilidad (sin distinguir mayúsculas ni tildes)."""
    key = skill_key(name)
    if not key:
        return None
    exists = session.scalar(select(Skill.id).where(Skill.user_id == user.id, Skill.name_key == key))
    if exists is not None:
        return None
    skill = Skill(user_id=user.id, name=name.strip(), name_key=key, category=category.strip() or "Otros")
    session.add(skill)
    session.flush()
    return skill


def delete_skill(session: Session, user: User, skill_id: int) -> None:
    skill = session.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id))
    if skill is None:
        raise NotFoundError(f"Habilidad {skill_id}")
    session.delete(skill)


# ── educación ─────────────────────────────────────────────────────────


def list_education(session: Session, user: User) -> list[Education]:
    rows = session.scalars(select(Education).where(Education.user_id == user.id)).all()
    return sorted(rows, key=lambda e: (e.period.sort_key, e.id), reverse=True)


def add_education(
    session: Session,
    user: User,
    *,
    title: str,
    institution: str = "",
    period_text: str = "",
    description: str = "",
) -> Education:
    education = Education(
        user_id=user.id, title=title.strip(), institution=institution.strip(),
        description=description.strip(),
    )
    education.set_period(period_text)
    session.add(education)
    session.flush()
    return education


def delete_education(session: Session, user: User, education_id: int) -> None:
    education = session.scalar(
        select(Education).where(Education.id == education_id, Education.user_id == user.id)
    )
    if education is None:
        raise NotFoundError(f"Educación {education_id}")
    session.delete(education)
