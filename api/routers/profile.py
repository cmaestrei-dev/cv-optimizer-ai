"""Perfil de la cuenta: contacto, experiencias con logros, habilidades y educación.

Las modificaciones devuelven el perfil completo actualizado (una sola fuente de verdad para el cliente).
"""

import threading
import time

from fastapi import APIRouter, HTTPException, status

from api.auth import CurrentAccount
from api.schemas import (
    AchievementOut,
    AchievementsIn,
    Contact,
    ContactOut,
    EducationIn,
    EducationOut,
    ExperienceIn,
    ExperienceOut,
    LinkLegacyIn,
    MeOut,
    ProfileOut,
    SkillIn,
    SkillOut,
)
from core.profile import service
from core.profile.interview import strength
from core.profile.links import safe_link

router = APIRouter(tags=["perfil"])

# Intentos de vincular un perfil anterior (adivinar contraseñas): por cuenta (5 cada 15 min) y por perfil
# objetivo (10 por hora, porque crear cuentas nuevas es gratis). En memoria: el servicio corre en 1 instancia.
_LINK_ATTEMPTS: dict[str, list[float]] = {}
_LINK_LOCK = threading.Lock()
_LINK_LIMITS = {"cuenta": (5, 15 * 60), "perfil": (10, 60 * 60)}


def _take_link_attempt(account_key: str, target_key: str) -> list[str]:
    """Registra el intento ANTES de verificar (las ráfagas simultáneas no se cuelan) o lanza 429."""
    now = time.time()
    keys = {"cuenta": f"cuenta:{account_key}", "perfil": f"perfil:{target_key}"}
    with _LINK_LOCK:
        for kind, key in keys.items():
            limit, window = _LINK_LIMITS[kind]
            recent = [t for t in _LINK_ATTEMPTS.get(key, []) if now - t < window]
            _LINK_ATTEMPTS[key] = recent
            if len(recent) >= limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos. Espera un rato y vuelve a intentarlo.")
        for key in keys.values():
            _LINK_ATTEMPTS[key].append(now)
    return list(keys.values())


def _release_link_attempt(keys: list[str]) -> None:
    """Un intento exitoso no cuenta como fallido."""
    with _LINK_LOCK:
        for key in keys:
            if _LINK_ATTEMPTS.get(key):
                _LINK_ATTEMPTS[key].pop()


def _contact(username: str) -> ContactOut:
    user = service.get_user(username)
    return ContactOut(
        full_name=user.full_name, email=user.email, phone=user.phone,
        linkedin_url=safe_link(user.linkedin_url), github_url=safe_link(user.github_url),
    )


def _profile(username: str) -> ProfileOut:
    snap = service.snapshot(username)
    counts = [strength(e) for e in snap.experiences]
    return ProfileOut(
        contact=_contact(username),
        experiences=[
            ExperienceOut(
                id=e.id, role=e.role, company=e.company, period_text=e.period_text, country=e.country,
                modality=e.modality, achievements=[AchievementOut(id=a.id, text=a.text) for a in e.achievements],
            )
            for e in snap.experiences
        ],
        skills=[SkillOut(id=k.id, name=k.name, category=k.category) for k in snap.skills],
        education=[
            EducationOut(id=d.id, title=d.title, institution=d.institution, period_text=d.period_text,
                         description=d.description)
            for d in snap.education
        ],
        achievements_with_numbers=sum(c[0] for c in counts),
        achievements_total=sum(c[1] for c in counts),
    )


@router.get("/me", response_model=MeOut)
def me(account: CurrentAccount) -> MeOut:
    has_experience, has_skills, has_education = service.profile_status(account.username)
    return MeOut(email=account.email, contact=_contact(account.username), has_experience=has_experience,
                 has_skills=has_skills, has_education=has_education)


@router.post("/me/link-legacy", response_model=MeOut)
def link_legacy(body: LinkLegacyIn, account: CurrentAccount) -> MeOut:
    """Vincula el perfil que la persona usaba en la versión anterior (Streamlit), con su contraseña."""
    attempt = _take_link_attempt(account.subject, service.legacy_key(body.username))
    try:
        username = service.link_legacy_profile(account.subject, body.username, body.password)
    except service.LinkError as e:
        time.sleep(1)  # frena la adivinación de contraseñas
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    _release_link_attempt(attempt)
    has_experience, has_skills, has_education = service.profile_status(username)
    return MeOut(email=account.email, contact=_contact(username), has_experience=has_experience,
                 has_skills=has_skills, has_education=has_education)


@router.put("/me/contact", response_model=ContactOut)
def update_contact(body: Contact, account: CurrentAccount) -> ContactOut:
    service.update_user(account.username, **body.model_dump())
    return _contact(account.username)


@router.get("/profile", response_model=ProfileOut)
def get_profile(account: CurrentAccount) -> ProfileOut:
    return _profile(account.username)


@router.post("/experiences", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def add_experience(body: ExperienceIn, account: CurrentAccount) -> ProfileOut:
    service.add_experience(account.username, **body.model_dump())
    return _profile(account.username)


@router.put("/experiences/{experience_id}", response_model=ProfileOut)
def update_experience(experience_id: int, body: ExperienceIn, account: CurrentAccount) -> ProfileOut:
    fields = body.model_dump()
    service.update_experience(account.username, experience_id, fields.pop("achievements"), **fields)
    return _profile(account.username)


@router.post("/experiences/{experience_id}/achievements", response_model=ProfileOut)
def append_achievements(experience_id: int, body: AchievementsIn, account: CurrentAccount) -> ProfileOut:
    service.append_achievements(account.username, experience_id, body.texts)
    return _profile(account.username)


@router.delete("/experiences/{experience_id}", response_model=ProfileOut)
def delete_experience(experience_id: int, account: CurrentAccount) -> ProfileOut:
    service.delete_experience(account.username, experience_id)
    return _profile(account.username)


@router.post("/skills", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def add_skill(body: SkillIn, account: CurrentAccount) -> ProfileOut:
    if not service.add_skill(account.username, body.name, body.category):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya tienes esa habilidad")
    return _profile(account.username)


@router.delete("/skills/{skill_id}", response_model=ProfileOut)
def delete_skill(skill_id: int, account: CurrentAccount) -> ProfileOut:
    service.delete_skill(account.username, skill_id)
    return _profile(account.username)


@router.post("/education", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def add_education(body: EducationIn, account: CurrentAccount) -> ProfileOut:
    service.add_education(account.username, **body.model_dump())
    return _profile(account.username)


@router.delete("/education/{education_id}", response_model=ProfileOut)
def delete_education(education_id: int, account: CurrentAccount) -> ProfileOut:
    service.delete_education(account.username, education_id)
    return _profile(account.username)
