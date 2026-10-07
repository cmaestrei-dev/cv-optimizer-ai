import pytest


@pytest.fixture(autouse=True)
def _isolate_databases(monkeypatch, tmp_path):
    """Ningún test toca la base real aunque el .env local tenga DATABASE_URL."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'core_test.db'}")
