"""Perfil de la cuenta: contacto, experiencias con logros, habilidades y educación.

Las modificaciones devuelven el perfil completo actualizado (una sola fuente de verdad para el cliente).
"""

from fastapi import APIRouter, HTTPException, status

from api.auth import CurrentAccount
from api.schemas import (
    AchievementOut,
    AchievementsIn,
    Contact,
    EducationIn,
    EducationOut,
    ExperienceIn,
    ExperienceOut,
    MeOut,
    ProfileOut,
    SkillIn,
    SkillOut,
)
from core.profile import service
from core.profile.interview import strength

router = APIRouter(tags=["perfil"])


def _contact(username: str) -> Contact:
    user = service.get_user(username)
    return Contact(
        full_name=user.full_name, email=user.email, phone=user.phone,
        linkedin_url=user.linkedin_url, github_url=user.github_url,
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


@router.put("/me/contact", response_model=Contact)
def update_contact(body: Contact, account: CurrentAccount) -> Contact:
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
