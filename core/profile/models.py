from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.profile.periods import Period, parse_period


class AppMeta(Base):
    """Marcas de estado de la app (p. ej. si ya se migró el almacenamiento anterior)."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_auth_subject", "auth_subject", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    linkedin_url: Mapped[str] = mapped_column(String, default="")
    github_url: Mapped[str] = mapped_column(String, default="")
    password_hash: Mapped[str] = mapped_column(String, default="")
    salt: Mapped[str] = mapped_column(String, default="")
    # Cuenta del SaaS: "emisor|sub" del token del proveedor de identidad. Vacío = perfil de Streamlit.
    auth_subject: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    experiences: Mapped[list["Experience"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    skills: Mapped[list["Skill"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    education: Mapped[list["Education"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class _PeriodFields:
    """Texto original del periodo (lo que se muestra) + fechas parseadas (para ordenar y calcular)."""

    period_text: Mapped[str] = mapped_column(String, default="")
    start_year: Mapped[int | None] = mapped_column(Integer)
    start_month: Mapped[int | None] = mapped_column(Integer)
    end_year: Mapped[int | None] = mapped_column(Integer)
    end_month: Mapped[int | None] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(default=False)

    def set_period(self, text: str) -> None:
        parsed = parse_period(text)
        self.period_text = text.strip()
        self.start_year, self.start_month = parsed.start_year, parsed.start_month
        self.end_year, self.end_month = parsed.end_year, parsed.end_month
        self.is_current = parsed.is_current

    @property
    def period(self) -> Period:
        return Period(self.start_year, self.start_month, self.end_year, self.end_month, self.is_current)


class Experience(TimestampMixin, _PeriodFields, Base):
    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String)
    company: Mapped[str] = mapped_column(String, default="")
    country: Mapped[str] = mapped_column(String, default="")
    modality: Mapped[str] = mapped_column(String, default="")

    user: Mapped[User] = relationship(back_populates="experiences")
    achievements: Mapped[list["Achievement"]] = relationship(
        back_populates="experience",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Achievement.position",
    )


class Achievement(TimestampMixin, Base):
    """Un logro o responsabilidad = una viñeta: la unidad que el motor selecciona y reescribe."""

    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    experience_id: Mapped[int] = mapped_column(
        ForeignKey("experiences.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)

    experience: Mapped[Experience] = relationship(back_populates="achievements")


class Skill(TimestampMixin, Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("user_id", "name_key", name="uq_skills_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    name_key: Mapped[str] = mapped_column(String)  # nombre normalizado para evitar duplicados
    category: Mapped[str] = mapped_column(String, default="Otros")

    user: Mapped[User] = relationship(back_populates="skills")


class Education(TimestampMixin, _PeriodFields, Base):
    __tablename__ = "education"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String)
    institution: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")

    user: Mapped[User] = relationship(back_populates="education")
