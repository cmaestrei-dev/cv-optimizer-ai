"""Las migraciones nunca deben perder datos (en SQLite, recrear una tabla la borra y dispara cascadas)."""

import shutil

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from core.db import get_engine, session_scope
from core.profile import service as profiles
from core.tracking import service as tracking

TABLES = ("users", "experiences", "achievements", "skills", "education", "applications", "application_events", "cv_documents")


def _cfg(script_location: str | None = None) -> Config:
    cfg = Config("alembic.ini")
    cfg.attributes["skip_logging_config"] = True
    if script_location:
        cfg.set_main_option("script_location", script_location)
    return cfg


def _counts() -> dict[str, int]:
    with get_engine().connect() as c:
        return {t: c.execute(text(f"select count(*) from {t}")).scalar() for t in TABLES}


@pytest.fixture
def populated(monkeypatch):
    monkeypatch.setattr(profiles, "_ready", False)
    profiles.ensure_ready()
    profiles.create_user("dianita")
    profiles.add_experience("dianita", role="Auxiliar Administrativa", achievements=["Facturé", "Concilié"])
    profiles.add_skill("dianita", "Excel")
    profiles.add_education("dianita", title="Tecnóloga")
    app_id = tracking.create_application("dianita", role="Aux")
    tracking.attach_cv("dianita", app_id, pdf=b"%PDF", docx=b"PK", markdown="", language="es", filename="cv.pdf")
    before = _counts()
    assert all(before.values())
    return before


def test_0004_keeps_every_row(populated):
    command.downgrade(_cfg(), "0003")
    assert _counts() == populated
    command.upgrade(_cfg(), "head")
    assert _counts() == populated
    with session_scope() as s:  # las llaves foráneas vuelven a quedar activas para la app
        assert s.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_future_batch_migrations_cannot_cascade_deletes(populated, tmp_path):
    """Una migración que recrea `users` (modo batch) no debe borrar en cascada lo que cuelga de ella."""
    scripts = tmp_path / "migrations"
    shutil.copytree("migrations", scripts, ignore=shutil.ignore_patterns("__pycache__"))
    (scripts / "versions" / "9999_recrea_users.py").write_text(
        '"""prueba"""\n'
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "revision = '9999'\n"
        "down_revision = '0004'\n"
        "branch_labels = None\n"
        "depends_on = None\n\n\n"
        "def upgrade():\n"
        "    with op.batch_alter_table('users', recreate='always') as batch:\n"
        "        batch.add_column(sa.Column('prueba', sa.String(), nullable=True))\n\n\n"
        "def downgrade():\n"
        "    pass\n"
    )
    command.upgrade(_cfg(str(scripts)), "9999")
    assert _counts() == populated
    with session_scope() as s:
        assert s.execute(text("PRAGMA foreign_keys")).scalar() == 1
