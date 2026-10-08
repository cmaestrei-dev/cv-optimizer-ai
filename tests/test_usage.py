from core import usage
from core.profile import service as profiles


def test_global_daily_cap(monkeypatch):
    monkeypatch.setattr(profiles, "_ready", False)
    profiles.ensure_ready()
    for name in ("ana", "eve"):
        profiles.create_user(name)
    monkeypatch.setenv("AI_GLOBAL_DAILY_CALLS", "3")
    usage.add("ana", 2)
    usage.check("eve")  # 2 de 3 en todo el servicio: todavía puede
    usage.add("eve", 1)
    try:
        usage.check("eve")
        raise AssertionError("debió frenarse")
    except usage.QuotaExceededError as e:
        assert "servicio" in str(e)
