from datetime import date

import pytest

from core.db import database_url, session_scope, upgrade_schema
from core.profile import repository as repo
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


class TestService:
    @pytest.fixture(autouse=True)
    def _fresh(self, monkeypatch):
        from core.profile import service

        monkeypatch.setattr(service, "_ready", False)
        self.service = service

    def test_profile_status(self):
        self.service.ensure_ready()
        self.service.create_user("ana", full_name="Ana")
        assert self.service.profile_status("ana") == (False, False, False)
        self.service.add_experience("ana", role="Auxiliar", company="ACME", achievements=["Facturé"])
        self.service.add_skill("ana", "Excel", "Herramientas y software")
        self.service.add_education("ana", title="Técnico", institution="SENA", period_text="2020")
        assert self.service.profile_status("ana") == (True, True, True)

    def test_experience_update_replaces_achievements(self):
        self.service.ensure_ready()
        self.service.create_user("ana")
        self.service.add_experience("ana", role="Aux", achievements=["a", "b"])
        exp = self.service.list_experiences("ana")[0]
        self.service.update_experience("ana", exp.id, achievements=["c"], role="Auxiliar")
        updated = self.service.list_experiences("ana")[0]
        assert (updated.role, [a.text for a in updated.achievements]) == ("Auxiliar", ["c"])

    def test_unknown_user_raises(self):
        self.service.ensure_ready()
        with pytest.raises(repo.NotFoundError):
            self.service.list_skills("nadie")
