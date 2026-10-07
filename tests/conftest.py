import pytest


@pytest.fixture(autouse=True)
def _isolate_databases(monkeypatch, tmp_path):
    """Ningún test toca bases reales aunque el .env local tenga DATABASE_URL o credenciales de Turso."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'core_test.db'}")
    monkeypatch.setattr("storage._db._TURSO_URL", "")
    monkeypatch.setattr("storage._db._TURSO_TOKEN", "")
