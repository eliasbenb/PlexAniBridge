"""Tests for HTTP Basic Authentication middleware and integration."""

import base64
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.web import app as app_module
from src.web.middlewares.basic_auth import BasicAuthMiddleware


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    """Build an Authorization header for HTTP Basic credentials."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_basic_auth_middleware_challenges_and_allows_access() -> None:
    """BasicAuthMiddleware challenges invalid credentials and allows valid ones."""
    test_app = FastAPI()
    test_app.add_middleware(
        BasicAuthMiddleware,
        username="admin",
        password="secret",
        realm="Realm",
    )

    @test_app.get("/protected")
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(test_app)

    # Missing credentials
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == 'Basic realm="Realm"'

    # Wrong credentials
    wrong = client.get("/protected", headers=_basic_auth_header("admin", "wrong"))
    assert wrong.status_code == 401

    # Correct credentials
    success = client.get("/protected", headers=_basic_auth_header("admin", "secret"))
    assert success.status_code == 200
    assert success.json() == {"ok": True}


def test_create_app_registers_basic_auth_middleware_when_configured(
    monkeypatch, tmp_path
) -> None:
    """create_app should attach BasicAuthMiddleware when credentials are configured."""
    test_config = SimpleNamespace(
        web_basic_auth_username="admin",
        web_basic_auth_password=SecretStr("secret"),
        web_basic_auth_realm="Realm",
    )
    monkeypatch.setattr(app_module, "config", test_config, raising=False)

    # Ensure the SPA assets check passes
    index_file = tmp_path / "index.html"
    index_file.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(app_module, "FRONTEND_BUILD_DIR", tmp_path, raising=False)

    app = app_module.create_app()

    middleware_classes = {middleware.cls for middleware in app.user_middleware}
    assert BasicAuthMiddleware in middleware_classes


def test_create_app_skips_basic_auth_without_complete_credentials(
    monkeypatch, tmp_path
) -> None:
    """create_app should skip BasicAuthMiddleware if either credential is missing."""
    incomplete_config = SimpleNamespace(
        web_basic_auth_username="admin",
        web_basic_auth_password=None,
        web_basic_auth_realm="Realm",
    )
    monkeypatch.setattr(app_module, "config", incomplete_config, raising=False)

    index_file = tmp_path / "index.html"
    index_file.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(app_module, "FRONTEND_BUILD_DIR", tmp_path, raising=False)

    app = app_module.create_app()

    middleware_classes = {middleware.cls for middleware in app.user_middleware}
    assert BasicAuthMiddleware not in middleware_classes
