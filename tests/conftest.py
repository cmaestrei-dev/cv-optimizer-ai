import os
import tempfile

import pytest

# El bot (`runner`) nunca lee la configuración, el estado, el token de Telegram ni el navegador reales: en este
# computador eso hizo que una prueba de la vuelta diaria revisara los portales, creara una postulación en la app y
# abriera el navegador del bot. Se fija antes de que se importe `runner.config`, que lee estas variables al cargarse.
_BOT_DIRS = tempfile.mkdtemp(prefix="cvo-bot-tests-")
os.environ["CVO_BOT_CONFIG_DIR"] = os.path.join(_BOT_DIRS, "config")
os.environ["CVO_BOT_DATA_DIR"] = os.path.join(_BOT_DIRS, "datos")


@pytest.fixture(autouse=True)
def _isolate_databases(monkeypatch, tmp_path):
    """Ningún test toca la base real ni la IA real aunque el .env local tenga DATABASE_URL o llaves
    (así corren igual que en la CI, que no tiene ninguna)."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'core_test.db'}")
    for name in ("GEMINI_API_KEY", "DEEPSEEK_API_KEY", "LLM_EXTRACT", "LLM_WRITE", "AI_DAILY_CALLS"):
        monkeypatch.delenv(name, raising=False)


API_TEST_SECRET = "x" * 40


@pytest.fixture
def client(monkeypatch):
    """Cliente de la API con tokens de desarrollo; la cola de trabajos se ejecuta a mano (worker.run_once)."""
    from fastapi.testclient import TestClient

    from api.main import create_app
    from core.profile import service as profiles

    for name in ("AUTH_JWKS_URL", "AUTH_ISSUER", "AUTH_AUDIENCE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUTH_DEV_SECRET", API_TEST_SECRET)
    monkeypatch.setenv("AUTH_DEV_LOGIN", "1")
    monkeypatch.setenv("API_INPROCESS_WORKER", "0")
    monkeypatch.setattr(profiles, "_ready", False)
    with TestClient(create_app()) as c:
        yield c
