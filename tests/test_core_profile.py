from datetime import date

import pytest

from core.db import database_url, session_scope, upgrade_schema
from core.profile import repository as repo
from core.profile.legacy import (
    parse_education_markdown,
    parse_experience_markdown,
    render_education_markdown,
    render_experiences_markdown,
    render_skills_markdown,
)
from core.profile.migration import migrate_all, migrate_user
from core.profile.periods import parse_period


@pytest.fixture
def db():
    upgrade_schema()
    return session_scope


class TestDatabaseUrl:
    def test_neon_url_uses_psycopg3(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x.neon.tech/db?sslmode=require")
        assert database_url() == "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"

    def test_postgres_scheme_alias(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h/db")
        assert database_url().startswith("postgresql+psycopg://")

    def test_local_sqlite_fallback(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATABASE_URL")
        monkeypatch.setattr("config.DATA_DIR", str(tmp_path))
        assert database_url() == f"sqlite:///{tmp_path / 'cv_core.db'}"


class TestPeriods:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Febrero 2024 - Diciembre 2025", (2024, 2, 2025, 12, False)),
            ("Enero 2022 - Presente", (2022, 1, None, None, True)),
            ("Septiembre de 2023 - actualidad", (2023, 9, None, None, True)),
            ("2022-2027", (2022, None, 2027, None, False)),
            ("(2025-2026)", (2025, None, 2026, None, False)),
            ("01/2020 – 06/2021", (2020, 1, 2021, 6, False)),
            ("Mar 2019 a Jul 2020", (2019, 3, 2020, 7, False)),
            ("2021", (2021, None, 2021, None, False)),
            ("Enero 2019 a la fecha", (2019, 1, None, None, True)),
            ("", (None, None, None, None, False)),
        ],
    )
    def test_parse(self, text, expected):
        p = parse_period(text)
        assert (p.start_year, p.start_month, p.end_year, p.end_month, p.is_current) == expected

    def test_months(self):
        assert parse_period("Enero 2022 - Presente").months(date(2026, 10, 1)) == 58
        assert parse_period("Febrero 2024 - Diciembre 2025").months() == 23
        assert parse_period("").months() is None

    def test_current_sorts_first(self):
        keys = [parse_period(t).sort_key for t in ("2018 - 2019", "Enero 2022 - Presente", "2020 - 2023")]
        assert max(keys) == parse_period("Enero 2022 - Presente").sort_key


class TestSchema:
    def test_alembic_schema_matches_models(self, db):
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        command.check(cfg)  # falla si los modelos cambian sin una migración nueva

    def test_upgrade_is_idempotent(self, db):
        upgrade_schema()


class TestRepository:
    def test_users(self, db):
        with db() as s:
            repo.create_user(s, "ana", full_name="Ana", password_hash="h", salt="s", unknown="x")
            with pytest.raises(repo.UserExistsError):
                repo.create_user(s, "ana")
        with db() as s:
            assert repo.list_usernames(s) == ["ana"]
            user = repo.get_user(s, "ana")
            repo.update_user(s, user, email="ana@x.co")
        with db() as s:
            assert repo.get_user(s, "ana").email == "ana@x.co"

    def test_experiences_sorted_with_ordered_achievements(self, db):
        with db() as s:
            user = repo.create_user(s, "ana")
            repo.add_experience(s, user, role="Asistente", company="A", period_text="2018 - 2019")
            repo.add_experience(
                s, user, role="Auxiliar", company="B", period_text="Enero 2022 - Presente",
                achievements=["Primero", "  ", "Segundo"],
            )
        with db() as s:
            user = repo.get_user(s, "ana")
            exps = repo.list_experiences(s, user)
            assert [e.role for e in exps] == ["Auxiliar", "Asistente"]
            assert [a.text for a in exps[0].achievements] == ["Primero", "Segundo"]
            assert exps[0].is_current and exps[0].start_year == 2022

    def test_cannot_touch_other_users_records(self, db):
        with db() as s:
            ana = repo.create_user(s, "ana")
            eve = repo.create_user(s, "eve")
            exp = repo.add_experience(s, ana, role="Auxiliar")
            skill = repo.add_skill(s, ana, "Excel")
            edu = repo.add_education(s, ana, title="Técnico")
            with pytest.raises(repo.NotFoundError):
                repo.update_experience(s, eve, exp.id, role="Hackeado")
            with pytest.raises(repo.NotFoundError):
                repo.delete_experience(s, eve, exp.id)
            with pytest.raises(repo.NotFoundError):
                repo.delete_skill(s, eve, skill.id)
            with pytest.raises(repo.NotFoundError):
                repo.delete_education(s, eve, edu.id)

    def test_update_and_replace_achievements(self, db):
        with db() as s:
            user = repo.create_user(s, "ana")
            exp = repo.add_experience(s, user, role="Aux", achievements=["a", "b"])
            repo.update_experience(s, user, exp.id, role="Auxiliar", period_text="2020 - 2021")
            repo.replace_achievements(s, exp, ["c"])
        with db() as s:
            exp = repo.list_experiences(s, repo.get_user(s, "ana"))[0]
            assert (exp.role, exp.end_year, [a.text for a in exp.achievements]) == ("Auxiliar", 2021, ["c"])

    def test_skills_dedupe_ignoring_case_and_accents(self, db):
        with db() as s:
            user = repo.create_user(s, "ana")
            assert repo.add_skill(s, user, "Facturación  Electrónica", "Conocimientos del área")
            assert repo.add_skill(s, user, "facturacion electronica") is None
            assert repo.add_skill(s, user, "   ") is None
            assert [k.name for k in repo.list_skills(s, user)] == ["Facturación  Electrónica"]

    def test_delete_user_cascades(self, db):
        with db() as s:
            user = repo.create_user(s, "ana")
            repo.add_experience(s, user, role="Aux", achievements=["a"])
            repo.add_skill(s, user, "Excel")
            repo.add_education(s, user, title="Técnico")
        with db() as s:
            repo.delete_user(s, "ana")
        from sqlalchemy import text

        with db() as s:
            for table in ("users", "experiences", "achievements", "skills", "education"):
                assert s.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0


class TestLegacyParsing:
    def test_experience_header_and_mixed_bullets(self):
        content = (
            "### Analista TI - El Arte de Nicolás | Febrero 2024 - Diciembre 2025 | [Colombia] | [Híbrido]\n\n"
            "*   Lideré la estrategia digital.\n"
            "- Diseñé la arquitectura de datos.\n"
            "Texto sin viñeta.\n"
            "1. Integré APIs."
        )
        [exp] = parse_experience_markdown(content)
        assert (exp.role, exp.company, exp.period_text, exp.country, exp.modality) == (
            "Analista TI", "El Arte de Nicolás", "Febrero 2024 - Diciembre 2025", "Colombia", "Híbrido"
        )
        assert exp.achievements == [
            "Lideré la estrategia digital.", "Diseñé la arquitectura de datos.",
            "Texto sin viñeta.", "Integré APIs.",
        ]

    def test_multiple_blocks_and_headerless_text(self):
        entries = parse_experience_markdown("- suelto\n### A - B | 2020\n- x\n### C\n- y")
        assert [e.role for e in entries] == ["(Sin cargo)", "A", "C"]

    def test_education_formats(self):
        assert parse_education_markdown("### Técnico - SENA | 2020 - 2021\n- Énfasis en contabilidad")[0].description == (
            "Énfasis en contabilidad"
        )
        flat = parse_education_markdown(
            "- Ingeniería de Sistemas - Universidad de Cartagena (2022-2027)\nCreación de APIs - Platzi (2025-2026)"
        )
        assert [(e.title, e.institution, e.period_text) for e in flat] == [
            ("Ingeniería de Sistemas", "Universidad de Cartagena", "2022-2027"),
            ("Creación de APIs", "Platzi", "2025-2026"),
        ]

    def test_render_round_trip(self, db):
        with db() as s:
            user = repo.create_user(s, "ana")
            repo.add_experience(
                s, user, role="Auxiliar", company="ACME", period_text="Enero 2022 - Presente",
                country="Colombia", modality="Presencial", achievements=["Gestioné facturación"],
            )
            repo.add_skill(s, user, "Excel", "Herramientas y software")
            repo.add_education(s, user, title="Técnico", institution="SENA", period_text="2020 - 2021")
            exp_md = render_experiences_markdown(repo.list_experiences(s, user))
            edu_md = render_education_markdown(repo.list_education(s, user))
            skills_md = render_skills_markdown(repo.list_skills(s, user))
        assert exp_md == (
            "### Auxiliar - ACME | Enero 2022 - Presente | Colombia | Presencial\n- Gestioné facturación"
        )
        assert parse_experience_markdown(exp_md)[0].achievements == ["Gestioné facturación"]
        assert edu_md == "### Técnico - SENA | 2020 - 2021"
        assert skills_md == "- **Excel** -> [Herramientas y software]\n"


_ROWS = {
    "profile": {"full_name": "Ana Pérez", "email": "ana@x.co", "password_hash": "h", "salt": "s", "id": 7},
    "experiences": [
        "### Auxiliar - ACME | Enero 2022 - Presente | Colombia | Presencial\n- Facturé\n- Concilié",
        "### Practicante - Beta\n- Archivé",
    ],
    "skills": [("Excel", "Herramientas y software"), ("excel", "Otros"), ("SAP", None)],
    "education": ["### Técnico - SENA | 2020 - 2021"],
}


class TestMigration:
    def test_migrate_user(self, db):
        with db() as s:
            report = migrate_user(s, "ana", _ROWS)
        assert (report.experiences, report.achievements, report.skills, report.duplicate_skills,
                report.education) == (2, 3, 2, 1, 1)
        assert report.warnings == ["Experiencia sin periodo: 'Practicante'"]
        with db() as s:
            user = repo.get_user(s, "ana")
            assert (user.full_name, user.password_hash, user.salt) == ("Ana Pérez", "h", "s")
            assert [k.category for k in repo.list_skills(s, user)] == ["Herramientas y software", "Otros"]

    def test_migration_is_idempotent(self, db):
        with db() as s:
            migrate_user(s, "ana", _ROWS)
        with db() as s:
            assert migrate_user(s, "ana", _ROWS).skipped
            assert len(repo.list_experiences(s, repo.get_user(s, "ana"))) == 2

    def test_end_to_end_from_legacy_storage(self, db, monkeypatch, tmp_path):
        import storage
        from models import UserProfile

        monkeypatch.setattr("config.DATA_DIR", str(tmp_path / "legacy"))
        monkeypatch.setattr("storage._db._inited", False)
        profile = UserProfile(username="ana", full_name="Ana Pérez")
        profile.set_password("clave-ana-123")
        storage.save_profile("ana", profile.to_dict())
        storage.prepend_knowledge_base("ana", "### Auxiliar - ACME | 2022 - 2024\n- Facturé")
        storage.append_skill("ana", "- **Excel** -> [Herramientas y software]\n")
        storage.prepend_education("ana", "### Técnico - SENA | 2020 - 2021")

        with db() as s:
            [report] = migrate_all(s, storage.list_profiles(), storage.export_profile_rows)
        assert (report.experiences, report.skills, report.education) == (1, 1, 1)
        with db() as s:
            user = repo.get_user(s, "ana")
            migrated = UserProfile(username="ana", password_hash=user.password_hash, salt=user.salt)
            assert migrated.verify_password("clave-ana-123")


class TestService:
    @pytest.fixture(autouse=True)
    def _fresh(self, monkeypatch):
        from core.profile import service

        monkeypatch.setattr(service, "_ready", False)
        self.service = service

    def test_ensure_ready_migrates_only_once(self):
        exported = []

        def export(username):
            exported.append(username)
            return _ROWS

        reports = self.service.ensure_ready(lambda: ["ana"], export)
        assert [r.username for r in reports] == ["ana"] and exported == ["ana"]
        self.service.delete_user("ana")
        self.service._ready = False  # nuevo proceso
        assert self.service.ensure_ready(lambda: ["ana"], export) == []
        assert self.service.list_usernames() == []  # un usuario borrado no "resucita"

    def test_skipping_legacy_does_not_mark_migration_done(self):
        assert self.service.ensure_ready(lambda: 1 / 0, lambda u: {}, migrate_legacy=False) == []
        self.service._ready = False
        reports = self.service.ensure_ready(lambda: ["ana"], lambda u: _ROWS)
        assert [r.username for r in reports] == ["ana"]

    def test_profile_status_and_legacy_markdown(self):
        self.service.ensure_ready(lambda: [], lambda u: {})
        self.service.create_user("ana", full_name="Ana")
        assert self.service.profile_status("ana") == (False, False, False)
        self.service.add_experience("ana", role="Auxiliar", company="ACME", achievements=["Facturé"])
        self.service.add_skill("ana", "Excel", "Herramientas y software")
        self.service.add_education("ana", title="Técnico", institution="SENA", period_text="2020")
        assert self.service.profile_status("ana") == (True, True, True)
        exp_md, skills_md, edu_md = self.service.legacy_markdown("ana")
        assert exp_md == "### Auxiliar - ACME\n- Facturé"
        assert skills_md == "- **Excel** -> [Herramientas y software]\n"
        assert edu_md == "### Técnico - SENA | 2020"

    def test_experience_update_replaces_achievements(self):
        self.service.ensure_ready(lambda: [], lambda u: {})
        self.service.create_user("ana")
        self.service.add_experience("ana", role="Aux", achievements=["a", "b"])
        exp = self.service.list_experiences("ana")[0]
        self.service.update_experience("ana", exp.id, achievements=["c"], role="Auxiliar")
        updated = self.service.list_experiences("ana")[0]
        assert (updated.role, [a.text for a in updated.achievements]) == ("Auxiliar", ["c"])

    def test_unknown_user_raises(self):
        self.service.ensure_ready(lambda: [], lambda u: {})
        with pytest.raises(repo.NotFoundError):
            self.service.list_skills("nadie")
