from sqlalchemy import select

from core.bot import tokens
from core.bot.models import BotToken
from core.db import session_scope
from tests.test_api import _h, _username


def _bot(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create(client, sub="ana", label="Portátil") -> dict:
    r = client.post("/bot-tokens", json={"label": label}, headers=_h(sub))
    assert r.status_code == 201, r.text
    return r.json()


class TestBotTokens:
    def test_create_shows_the_token_once_and_stores_only_its_hash(self, client):
        out = _create(client)
        assert out["token"].startswith("cvb_") and len(out["token"]) > 40
        assert out["hint"] == out["token"][-4:] and out["label"] == "Portátil"
        listed = client.get("/bot-tokens", headers=_h("ana")).json()
        assert [t["id"] for t in listed] == [out["id"]] and "token" not in listed[0]
        with session_scope() as s:
            row = s.scalar(select(BotToken))
            assert row.token_hash != out["token"] and out["token"] not in (row.token_hash, row.hint, row.label)

    def test_bot_token_works_like_the_persons_session(self, client):
        token = _create(client)["token"]
        assert client.get("/me", headers=_bot(token)).status_code == 200
        assert client.get("/applications", headers=_bot(token)).status_code == 200
        assert tokens.resolve(token) == _username(client, "ana")

    def test_bot_cannot_manage_tokens_or_link_profiles(self, client):
        token = _create(client)["token"]
        assert client.get("/bot-tokens", headers=_bot(token)).status_code == 403
        assert client.post("/bot-tokens", json={}, headers=_bot(token)).status_code == 403
        r = client.post("/me/link-legacy", json={"username": "x", "password": "y"}, headers=_bot(token))
        assert r.status_code == 403

    def test_revoked_token_stops_working(self, client):
        out = _create(client)
        assert client.delete(f"/bot-tokens/{out['id']}", headers=_h("ana")).status_code == 204
        assert client.get("/me", headers=_bot(out["token"])).status_code == 401
        assert client.get("/bot-tokens", headers=_h("ana")).json() == []
        assert client.delete(f"/bot-tokens/{out['id']}", headers=_h("ana")).status_code == 404

    def test_tokens_are_isolated_between_accounts(self, client):
        out = _create(client, "ana")
        assert client.get("/bot-tokens", headers=_h("luis")).json() == []
        assert client.delete(f"/bot-tokens/{out['id']}", headers=_h("luis")).status_code == 404
        assert client.get("/me", headers=_bot(out["token"])).status_code == 200  # sigue vigente

    def test_unknown_or_malformed_tokens_are_rejected(self, client):
        _create(client)
        for bad in ("cvb_" + "a" * 43, "cvb_", "cvb_" + "x" * 200):
            assert client.get("/me", headers=_bot(bad)).status_code == 401

    def test_limit_of_active_tokens(self, client):
        created = [_create(client, label=f"t{i}") for i in range(tokens.MAX_ACTIVE)]
        assert client.post("/bot-tokens", json={}, headers=_h("ana")).status_code == 409
        client.delete(f"/bot-tokens/{created[0]['id']}", headers=_h("ana"))
        assert client.post("/bot-tokens", json={}, headers=_h("ana")).status_code == 201

    def test_last_use_is_recorded(self, client):
        out = _create(client)
        assert out["last_used_at"] is None
        client.get("/me", headers=_bot(out["token"]))
        assert client.get("/bot-tokens", headers=_h("ana")).json()[0]["last_used_at"] is not None
