import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from api import auth
from core.profile import service as profiles
from core.tracking import service as tracking
from tests.conftest import API_TEST_SECRET as SECRET


def _token(sub: str, *, email: str = "", secret: str = SECRET, iss: str = auth.DEV_ISSUER, ttl: int = 600, **extra) -> str:
    now = int(time.time())
    return jwt.encode({"iss": iss, "sub": sub, "email": email, "iat": now, "exp": now + ttl, **extra}, secret, algorithm="HS256")


def _h(sub: str, **kw) -> dict:
    return {"Authorization": f"Bearer {_token(sub, **kw)}"}


def _username(client, sub: str) -> str:
    client.get("/me", headers=_h(sub))
    return profiles.account_username(f"{auth.DEV_ISSUER}|{sub}")


class TestAuth:
    def test_routes_are_published(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert {"/me", "/profile", "/experiences", "/applications", "/applications/{application_id}/sent",
                "/cvs/{cv_id}/{fmt}", "/market"} <= set(paths)
        assert client.get("/health").json() == {"status": "ok"}

    def test_token_is_required_and_verified(self, client):
        assert client.get("/me").status_code == 401
        assert client.get("/me", headers={"Authorization": "Bearer basura"}).status_code == 401
        assert client.get("/me", headers=_h("ana", secret="y" * 40)).status_code == 401  # firma ajena
        assert client.get("/me", headers=_h("ana", ttl=-120)).status_code == 401  # vencido
        assert client.get("/me", headers=_h("ana", iss="otro")).status_code == 401
        none_alg = jwt.encode({"iss": "dev", "sub": "ana", "exp": int(time.time()) + 600}, None, algorithm="none")
        assert client.get("/me", headers={"Authorization": f"Bearer {none_alg}"}).status_code == 401

    def test_dev_secret_never_opens_the_production_database(self, client, monkeypatch):
        monkeypatch.setattr(auth, "database_url", lambda: "postgresql+psycopg://prod")
        assert client.get("/me", headers=_h("ana")).status_code == 503

    def test_short_or_missing_config_is_unavailable(self, client, monkeypatch):
        monkeypatch.setenv("AUTH_DEV_SECRET", "corto")
        assert client.get("/me", headers=_h("ana", secret="corto" * 7)).status_code == 503
        monkeypatch.delenv("AUTH_DEV_SECRET")
        assert client.get("/me", headers=_h("ana")).status_code == 503

    def test_identity_provider_tokens_via_jwks(self, client, monkeypatch):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        monkeypatch.setenv("AUTH_JWKS_URL", "https://idp.example/.well-known/jwks.json")
        monkeypatch.setenv("AUTH_ISSUER", "https://idp.example")
        monkeypatch.setenv("AUTH_AUDIENCE", "cv-optimizer")
        auth._jwks_client.cache_clear()
        monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [{**jwk, "kid": "k1", "use": "sig"}]})

        def signed(**claims):
            now = int(time.time())
            body = {"iss": "https://idp.example", "sub": "google-123", "aud": "cv-optimizer", "exp": now + 600, **claims}
            return {"Authorization": "Bearer " + jwt.encode(body, key, algorithm="RS256", headers={"kid": "k1"})}

        me = client.get("/me", headers=signed(email="dianita@example.com", name="Diana"))
        assert me.status_code == 200 and me.json()["contact"]["full_name"] == "Diana"
        assert client.get("/me", headers=signed(aud="otra-app")).status_code == 401
        assert client.get("/me", headers=signed(iss="https://evil.example")).status_code == 401
        no_aud = jwt.encode({"iss": "https://idp.example", "sub": "x", "exp": int(time.time()) + 600}, key,
                            algorithm="RS256", headers={"kid": "k1"})
        assert client.get("/me", headers={"Authorization": f"Bearer {no_aud}"}).status_code == 401
        # Cabecera manipulada: llave RSA real pero "alg: ES256" → 401, no un error 500
        good = signed()["Authorization"].split()[1]
        header, payload, signature = good.split(".")
        forged_header = jwt.utils.base64url_encode(json.dumps({"alg": "ES256", "kid": "k1", "typ": "JWT"}).encode()).decode()
        assert client.get("/me", headers={"Authorization": f"Bearer {forged_header}.{payload}.{signature}"}).status_code == 401
        unknown_kid = jwt.encode({"iss": "https://idp.example", "sub": "x", "aud": "cv-optimizer", "exp": int(time.time()) + 600},
                                 key, algorithm="RS256", headers={"kid": "otra"})
        assert client.get("/me", headers={"Authorization": f"Bearer {unknown_kid}"}).status_code == 401
        # Con JWKS configurado, un token HS256 firmado con el secreto de desarrollo ya no vale
        assert client.get("/me", headers=_h("ana")).status_code == 401
        # Sin audiencia configurada, el modo de producción no arranca (evita reutilizar tokens de otras apps)
        monkeypatch.delenv("AUTH_AUDIENCE")
        assert client.get("/me", headers=signed()).status_code == 503
        auth._jwks_client.cache_clear()

    def test_accounts_are_created_once_and_hidden_from_streamlit(self, client):
        profiles.create_user("perfil_viejo")
        first = client.get("/me", headers=_h("ana", email="ana@example.com"))
        assert first.status_code == 200 and first.json()["contact"]["email"] == "ana@example.com"
        assert client.get("/me", headers=_h("ana", email="otro@example.com")).json()["contact"]["email"] == "ana@example.com"
        username = profiles.account_username("dev|ana")
        assert username.startswith("saas:") and profiles.list_usernames() == ["perfil_viejo"]
        # Contraseña local inutilizable: aunque una versión vieja de Streamlit la listara, no se abriría sola
        from models import UserProfile
        user = profiles.get_user(username)
        legacy = UserProfile(username=username, password_hash=user.password_hash, salt=user.salt)
        assert legacy.has_password and not legacy.verify_password("") and not legacy.verify_password(username)


class TestProfile:
    def test_full_profile_flow(self, client):
        h = _h("ana")
        r = client.post("/experiences", headers=h, json={
            "role": "Auxiliar Administrativa", "company": "Nissan", "period_text": "Marzo 2023 - Presente",
            "achievements": ["Elaboré 180 facturas al mes", "Atendí clientes"],
        })
        assert r.status_code == 201
        exp = r.json()["experiences"][0]
        assert exp["role"] == "Auxiliar Administrativa" and len(exp["achievements"]) == 2
        assert (r.json()["achievements_with_numbers"], r.json()["achievements_total"]) == (1, 2)

        r = client.post(f"/experiences/{exp['id']}/achievements", headers=h, json={"texts": ["Concilié cartera"]})
        assert [a["text"] for a in r.json()["experiences"][0]["achievements"]][-1] == "Concilié cartera"
        r = client.put(f"/experiences/{exp['id']}", headers=h, json={
            "role": "Asistente Administrativa", "company": "Nissan", "period_text": "2023 - Presente", "achievements": ["Uno"],
        })
        assert r.json()["experiences"][0]["role"] == "Asistente Administrativa"
        assert r.json()["experiences"][0]["period_text"] == "2023 - Presente"

        assert client.post("/skills", headers=h, json={"name": "Excel", "category": "Herramientas y software"}).status_code == 201
        assert client.post("/skills", headers=h, json={"name": " excel "}).status_code == 409
        r = client.post("/education", headers=h, json={"title": "Tecnóloga en Gestión Administrativa", "institution": "SENA"})
        skill_id, edu_id = r.json()["skills"][0]["id"], r.json()["education"][0]["id"]
        me = client.get("/me", headers=h).json()
        assert (me["has_experience"], me["has_skills"], me["has_education"]) == (True, True, True)

        r = client.put("/me/contact", headers=h, json={"full_name": "Ana Pérez", "linkedin_url": "https://linkedin.com/in/ana"})
        assert r.json()["full_name"] == "Ana Pérez"
        assert client.put("/me/contact", headers=h, json={"linkedin_url": "javascript:alert(1)"}).status_code == 422
        r = client.put("/me/contact", headers=h, json={"linkedin_url": "www.linkedin.com/in/ana"})
        assert r.json()["linkedin_url"] == "https://www.linkedin.com/in/ana"
        # Un enlace guardado en otro formato (Streamlit, importación vieja) no rompe la lectura del perfil
        profiles.update_user(_username(client, "ana"), linkedin_url="mi perfil de linkedin")
        assert client.get("/me", headers=h).status_code == 200 and client.get("/profile", headers=h).status_code == 200

        client.delete(f"/skills/{skill_id}", headers=h)
        client.delete(f"/education/{edu_id}", headers=h)
        r = client.delete(f"/experiences/{exp['id']}", headers=h)
        assert r.json()["experiences"] == [] and r.json()["skills"] == [] and r.json()["education"] == []

    def test_validation(self, client):
        h = _h("ana")
        assert client.post("/experiences", headers=h, json={"role": "  "}).status_code == 422
        assert client.post("/experiences", headers=h, json={"role": "x" * 201}).status_code == 422
        assert client.post("/experiences", headers=h, json={"role": "A", "achievements": ["x"] * 61}).status_code == 422

    def test_accounts_are_isolated(self, client):
        ana, eve = _h("ana"), _h("eve")
        exp_id = client.post("/experiences", headers=ana, json={"role": "Aux", "achievements": ["a"]}).json()["experiences"][0]["id"]
        skill_id = client.post("/skills", headers=ana, json={"name": "Excel"}).json()["skills"][0]["id"]
        assert client.get("/profile", headers=eve).json()["experiences"] == []
        assert client.put(f"/experiences/{exp_id}", headers=eve, json={"role": "hack"}).status_code == 404
        assert client.post(f"/experiences/{exp_id}/achievements", headers=eve, json={"texts": ["hack"]}).status_code == 404
        assert client.delete(f"/experiences/{exp_id}", headers=eve).status_code == 404
        assert client.delete(f"/skills/{skill_id}", headers=eve).status_code == 404
        assert len(client.get("/profile", headers=ana).json()["experiences"][0]["achievements"]) == 1


class TestApplications:
    def test_manual_application_lifecycle(self, client):
        h = _h("ana")
        r = client.post("/applications", headers=h, json={"role": "Auxiliar", "company": "ACME", "platform": "Computrabajo"})
        assert r.status_code == 201
        app = r.json()
        assert app["status"] == "postulada" and app["applied_on"] == tracking.today().isoformat()
        assert app["next_action_on"] is not None  # seguimiento automático a los 7 días

        r = client.post(f"/applications/{app['id']}/status", headers=h, json={"status": "entrevista", "note": "Me llamaron"})
        assert r.json()["status_label"] == "Entrevista" and r.json()["events"][-1]["detail"] == "Me llamaron"
        r = client.post(f"/applications/{app['id']}/notes", headers=h, json={"note": "Entrevista el jueves"})
        assert r.json()["events"][-1]["kind"] == "nota"
        r = client.put(f"/applications/{app['id']}/follow-up", headers=h, json={"on": "2026-12-01", "what": "Escribirle"})
        assert r.json()["next_action_on"] == "2026-12-01"
        r = client.patch(f"/applications/{app['id']}", headers=h, json={"contact": "rrhh@acme.co", "url": "https://acme.co/1"})
        assert r.json()["contact"] == "rrhh@acme.co" and r.json()["url"] == "https://acme.co/1"
        assert client.patch(f"/applications/{app['id']}", headers=h, json={"url": "file:///etc/passwd"}).status_code == 422
        assert client.post(f"/applications/{app['id']}/status", headers=h, json={"status": "hackeada"}).status_code == 422
        assert client.post("/applications", headers=h, json={"role": "X", "status": "por_revisar"}).status_code == 422

        summary = client.get("/applications/summary", headers=h).json()
        assert summary["total"] == 1 and summary["by_status"]["entrevista"] == 1
        assert [a["id"] for a in client.get("/applications?view=activas", headers=h).json()] == [app["id"]]
        assert client.delete(f"/applications/{app['id']}", headers=h).status_code == 204
        assert client.get(f"/applications/{app['id']}", headers=h).status_code == 404

    def test_lists_do_not_load_cv_files(self, client):
        user = _username(client, "ana")
        app_id = tracking.create_application(user, role="Aux", status="guardada")
        tracking.attach_cv(user, app_id, pdf=b"%PDF" * 1000, docx=b"PK", markdown="", language="es", filename="cv.pdf")
        light = tracking.list_applications(user, with_files=False)[0].cvs[0]
        assert "pdf" not in light.__dict__ and "docx" not in light.__dict__ and light.pdf_sha256
        assert tracking.list_applications(user)[0].cvs[0].pdf.startswith(b"%PDF")  # Streamlit sí los necesita

    def test_views_and_inbox_ranking(self, client):
        h = _h("ana")
        user = _username(client, "ana")
        low = tracking.create_application(user, role="Baja", status="por_revisar", match_score=40)
        high = tracking.create_application(user, role="Alta", status="por_revisar", match_score=90,
                                           match_json=json.dumps({"score": 90}), analysis_json='{"role": "Alta"}')
        tracking.create_application(user, role="Descartada", status="descartada")
        sent = tracking.create_application(user, role="Enviada", status="postulada", applied_on=tracking.today())
        assert [a["id"] for a in client.get("/applications?view=bandeja", headers=h).json()] == [high, low]
        assert [a["role"] for a in client.get("/applications?view=todas", headers=h).json()] == ["Enviada"]
        assert [a["role"] for a in client.get("/applications?view=descartadas", headers=h).json()] == ["Descartada"]
        detail = client.get(f"/applications/{high}", headers=h).json()
        assert detail["match"] == {"score": 90} and detail["vacancy"] == {"role": "Alta"}
        assert client.get(f"/applications/{sent}", headers=h).json()["vacancy"] is None
        assert client.get("/applications?view=otra", headers=h).status_code == 422

    def test_exact_cv_download_and_sent_guarantee(self, client):
        ana, eve = _h("ana"), _h("eve")
        user = _username(client, "ana")
        app_id = tracking.create_application(user, role="Aux", status="guardada")
        other_app = tracking.create_application(user, role="Otra", status="guardada")
        cv_id = tracking.attach_cv(user, app_id, pdf=b"%PDF-1.7 cv", docx=b"PK docx", markdown="", language="es",
                                   filename="Ana_Aux.pdf")
        r = client.get(f"/cvs/{cv_id}/pdf", headers=ana)
        assert r.status_code == 200 and r.content == b"%PDF-1.7 cv"
        assert r.headers["x-content-sha256"] == tracking.sha256(b"%PDF-1.7 cv")
        assert "Ana_Aux.pdf" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
        assert client.get(f"/cvs/{cv_id}/docx", headers=ana).content == b"PK docx"
        assert client.get(f"/cvs/{cv_id}/pdf", headers=eve).status_code == 404

        # Solo un CV generado para ESA postulación puede marcarse como enviado
        assert client.post(f"/applications/{other_app}/sent", headers=ana, json={"cv_id": cv_id}).status_code == 404
        r = client.post(f"/applications/{app_id}/sent", headers=ana, json={"cv_id": cv_id, "platform": "LinkedIn"})
        assert r.json()["status"] == "postulada" and r.json()["cvs"][0]["sent_at"] is not None
        assert r.json()["cvs"][0]["intact"] is True and r.json()["platform"] == "LinkedIn"
        assert client.post(f"/applications/{app_id}/sent", headers=eve, json={"cv_id": cv_id}).status_code == 404

    def test_tampered_cv_is_not_served(self, client):
        from core.db import session_scope
        from core.tracking.models import CVDocumentRecord

        user = _username(client, "ana")
        app_id = tracking.create_application(user, role="Aux", status="guardada")
        cv_id = tracking.attach_cv(user, app_id, pdf=b"%PDF original", docx=b"PK", markdown="", language="es", filename="cv.pdf")
        with session_scope() as s:
            s.get(CVDocumentRecord, cv_id).pdf = b"%PDF alterado"
        assert client.get(f"/cvs/{cv_id}/pdf", headers=_h("ana")).status_code == 409
        assert client.get(f"/applications/{app_id}", headers=_h("ana")).json()["cvs"][0]["intact"] is False

    def test_other_accounts_applications_are_invisible(self, client):
        user = _username(client, "ana")
        app_id = tracking.create_application(user, role="Aux")
        eve = _h("eve")
        assert client.get("/applications?view=todas", headers=eve).json() == []
        for method, path, body in [
            ("get", f"/applications/{app_id}", None), ("patch", f"/applications/{app_id}", {"contact": "x"}),
            ("post", f"/applications/{app_id}/status", {"status": "rechazada"}),
            ("post", f"/applications/{app_id}/notes", {"note": "x"}),
            ("put", f"/applications/{app_id}/follow-up", {"on": None}),
            ("delete", f"/applications/{app_id}", None),
        ]:
            assert client.request(method, path, headers=eve, json=body).status_code == 404, path
        assert tracking.get_application(user, app_id).status == "guardada"


def test_market(client):
    user = _username(client, "ana")
    tracking.create_application(user, role="A", platform="LinkedIn", status="rechazada", match_score=60,
                                analysis_json=json.dumps({"is_vacancy": True, "keywords": ["Excel", "SAP"]}))
    r = client.get("/market", headers=_h("ana")).json()
    assert r["applications"] == 1 and r["analyzed"] == 1 and r["enough_data"] is False
    assert {k["keyword"] for k in r["keywords"]} == {"Excel", "SAP"}
    assert r["platforms"][0]["platform"] == "LinkedIn" and r["platforms"][0]["sent"] == 1


def test_dev_login_only_exists_in_local_development(client, monkeypatch):
    r = client.post("/dev/token", json={"name": "Diana Rojas"})
    assert r.status_code == 200
    token = r.json()["token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["contact"]["full_name"] == "Diana Rojas"
    assert profiles.account_username("dev|diana-rojas").startswith("saas:")
    # Con proveedor de identidad (producción) o con Postgres, el endpoint no responde aunque la ruta exista
    monkeypatch.setenv("AUTH_JWKS_URL", "https://idp.example/jwks")
    assert client.post("/dev/token", json={"name": "x"}).status_code == 404
    monkeypatch.delenv("AUTH_JWKS_URL")
    monkeypatch.setattr("api.routers.dev.database_url", lambda: "postgresql+psycopg://prod")
    assert client.post("/dev/token", json={"name": "x"}).status_code == 404
    # Nunca monkeypatch.undo(): revertiría también el aislamiento de la base (conftest)
    monkeypatch.setattr("api.routers.dev.database_url", lambda: "sqlite://")
    monkeypatch.delenv("AUTH_DEV_LOGIN")  # sin permiso explícito (despliegue mal configurado): cerrado
    assert client.post("/dev/token", json={"name": "x"}).status_code == 404


def test_dev_login_names_without_latin_letters_get_their_own_account(client):
    tokens = [client.post("/dev/token", json={"name": n}).json()["token"] for n in ("李雷", "Дмитрий", "Ana", "ana")]
    usernames = [client.get("/me", headers={"Authorization": f"Bearer {t}"}).status_code and
                 profiles.account_username(f"dev|{jwt.decode(t, options={'verify_signature': False})['sub']}") for t in tokens]
    assert len(set(usernames[:2])) == 2 and usernames[2] == usernames[3]


def test_dev_login_route_is_not_registered_without_dev_secret(monkeypatch):
    from api.main import create_app

    monkeypatch.setenv("AUTH_DEV_LOGIN", "1")
    monkeypatch.delenv("AUTH_DEV_SECRET", raising=False)
    assert "/dev/token" not in create_app().openapi()["paths"]


def test_frontend_contract_is_up_to_date(monkeypatch):
    """web/openapi.json (de donde salen los tipos del frontend) debe coincidir con la API."""
    import pathlib

    from api.main import create_app

    for name, value in (("AUTH_DEV_SECRET", "x" * 40), ("AUTH_DEV_LOGIN", "1")):  # igual que scripts/export_openapi.py
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AUTH_JWKS_URL", raising=False)
    committed = json.loads(pathlib.Path("web/openapi.json").read_text(encoding="utf-8"))
    assert create_app().openapi() == committed, (
        "La API cambió: python scripts/export_openapi.py web/openapi.json && (cd web && npm run api:types)"
    )


class TestLinkLegacy:
    @pytest.fixture
    def dianita(self, client, monkeypatch):
        from api.routers import profile as profile_router
        from models import UserProfile

        monkeypatch.setattr(profile_router, "_LINK_ATTEMPTS", {})  # el límite es global al proceso

        p = UserProfile(username="dianita")
        p.set_password("clave-de-dianita")
        profiles.create_user("dianita", full_name="Diana", password_hash=p.password_hash, salt=p.salt)
        profiles.add_experience("dianita", role="Auxiliar Administrativa", achievements=["Facturé"])
        profiles.create_user("sinclave")
        return client

    def test_links_with_password_and_keeps_all_data(self, dianita, monkeypatch):
        monkeypatch.setattr("api.routers.profile.time.sleep", lambda s: None)
        client, h = dianita, _h("google-diana")
        assert client.get("/profile", headers=h).json()["experiences"] == []  # cuenta nueva vacía
        assert client.post("/me/link-legacy", headers=h, json={"username": "dianita", "password": "mala"}).status_code == 422
        r = client.post("/me/link-legacy", headers=h, json={"username": " Dianita ", "password": "clave-de-dianita"})
        assert r.status_code == 200 and r.json()["has_experience"] is True
        assert client.get("/profile", headers=h).json()["experiences"][0]["role"] == "Auxiliar Administrativa"
        assert profiles.account_username("dev|google-diana") == "dianita"
        # Sigue disponible en Streamlit (con su contraseña) durante la transición; la cuenta vacía ya no existe
        assert profiles.list_usernames() == ["dianita", "sinclave"]
        # Con la contraseña correcta se puede volver a vincular (p. ej. al cambiar de instancia de Clerk);
        # sin ella, no: y el mensaje no revela que el perfil existe
        other = client.post("/me/link-legacy", headers=_h("eve"), json={"username": "dianita", "password": "x"})
        assert other.status_code == 422 and other.json()["detail"] == "Usuario o contraseña incorrectos."
        moved = client.post("/me/link-legacy", headers=_h("clerk-prod-diana"), json={"username": "dianita", "password": "clave-de-dianita"})
        assert moved.status_code == 200 and profiles.account_username("dev|clerk-prod-diana") == "dianita"

    def test_refuses_profiles_without_password_and_accounts_with_data(self, dianita, monkeypatch):
        monkeypatch.setattr("api.routers.profile.time.sleep", lambda s: None)
        client = dianita
        missing = client.post("/me/link-legacy", headers=_h("ana"), json={"username": "no-existe", "password": "x"})
        r = client.post("/me/link-legacy", headers=_h("ana"), json={"username": "sinclave", "password": "x"})
        assert r.status_code == missing.status_code == 422 and r.json()["detail"] == missing.json()["detail"]
        client.post("/experiences", headers=_h("ana"), json={"role": "Cajera"})
        r = client.post("/me/link-legacy", headers=_h("ana"), json={"username": "dianita", "password": "clave-de-dianita"})
        assert r.status_code == 422 and "ya tiene datos" in r.json()["detail"]
        assert client.post("/me/link-legacy", headers=_h("ana"), json={"username": "saas:x", "password": "x"}).status_code == 422

    def test_guessing_is_limited_per_account_and_per_profile(self, dianita, monkeypatch):
        from api.routers import profile as profile_router

        monkeypatch.setattr("api.routers.profile.time.sleep", lambda s: None)
        monkeypatch.setattr(profile_router, "_LINK_ATTEMPTS", {})
        client, h = dianita, _h("atacante")
        for _ in range(5):
            assert client.post("/me/link-legacy", headers=h, json={"username": "dianita", "password": "x"}).status_code == 422
        assert client.post("/me/link-legacy", headers=h, json={"username": "dianita", "password": "clave-de-dianita"}).status_code == 429
        # Muchas cuentas nuevas contra el mismo perfil: también se frena (10 por hora)
        for i in range(5):
            client.post("/me/link-legacy", headers=_h(f"bot{i}"), json={"username": "dianita", "password": "x"})
        assert client.post("/me/link-legacy", headers=_h("bot9"), json={"username": "dianita", "password": "x"}).status_code == 429

    def test_streamlit_style_names(self, dianita, monkeypatch):
        from models import UserProfile

        monkeypatch.setattr("api.routers.profile.time.sleep", lambda s: None)
        p = UserProfile(username="juan_perez")
        p.set_password("clave-juan-123")
        profiles.create_user("juan_perez", password_hash=p.password_hash, salt=p.salt)
        r = dianita.post("/me/link-legacy", headers=_h("juan"), json={"username": "Juan Perez", "password": "clave-juan-123"})
        assert r.status_code == 200


def test_clerk_tokens_are_checked_by_authorized_party(client, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    monkeypatch.setenv("AUTH_JWKS_URL", "https://cv.clerk.accounts.dev/.well-known/jwks.json")
    monkeypatch.setenv("AUTH_ISSUER", "https://cv.clerk.accounts.dev")
    monkeypatch.setenv("AUTH_AUTHORIZED_PARTIES", "https://cv-optimizer.run.app, http://localhost:5173")
    auth._jwks_client.cache_clear()
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [{**jwk, "kid": "k1", "use": "sig"}]})

    def bearer(**claims):  # un token de sesión de Clerk: sin aud, con azp
        now = int(time.time())
        body = {"iss": "https://cv.clerk.accounts.dev", "sub": "user_2abc", "sid": "sess_1", "exp": now + 60, **claims}
        return {"Authorization": "Bearer " + jwt.encode(body, key, algorithm="RS256", headers={"kid": "k1"})}

    assert client.get("/me", headers=bearer(azp="https://cv-optimizer.run.app")).status_code == 200
    assert client.get("/me", headers=bearer(azp="http://localhost:5173/")).status_code == 200
    assert client.get("/me", headers=bearer(azp="https://evil.example")).status_code == 401
    assert client.get("/me", headers=bearer()).status_code == 401  # sin azp: se rechaza
    monkeypatch.delenv("AUTH_AUTHORIZED_PARTIES")  # sin audiencia ni orígenes: no arranca
    assert client.get("/me", headers=bearer(azp="https://cv-optimizer.run.app")).status_code == 503
    auth._jwks_client.cache_clear()
