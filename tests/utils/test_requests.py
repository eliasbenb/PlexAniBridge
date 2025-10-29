"""Tests for selective request session behavior."""

import types
from typing import Any

import pytest
import requests

from src.utils import requests as requests_module
from src.utils.requests import SelectiveVerifySession


@pytest.fixture(autouse=True)
def restore_log(monkeypatch):
    """Restore the original requests log after each test."""
    dummy_logger = types.SimpleNamespace(
        debug=lambda *_, **__: None,
        error=lambda *_, **__: None,
    )
    monkeypatch.setattr(requests_module, "log", dummy_logger)


def test_selective_verify_session_sets_verify_false_for_whitelist(monkeypatch):
    """Test that SelectiveVerifySession sets verify=False for whitelisted domains."""
    captured: dict[str, Any] = {}

    def fake_request(self, method, url, *args, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs
        return "ok"

    monkeypatch.setattr(requests.Session, "request", fake_request, raising=False)

    session = SelectiveVerifySession(whitelist={"example.com"})
    result = session.request("GET", "https://example.com/api")

    assert result == "ok"
    assert captured["kwargs"].get("verify") is False


def test_selective_verify_session_leaves_verify_for_other_domains(monkeypatch):
    """Test that SelectiveVerifySession does not modify verify for other domains."""
    captured = {}

    def fake_request(self, method, url, *args, **kwargs):
        captured["kwargs"] = kwargs
        return "resp"

    monkeypatch.setattr(requests.Session, "request", fake_request, raising=False)

    session = SelectiveVerifySession(whitelist={"whitelisted.com"})
    result = session.request("GET", "https://other.com/resource")

    assert result == "resp"
    assert "verify" not in captured["kwargs"]


def test_selective_verify_session_logs_error_on_failure(monkeypatch):
    """Test that SelectiveVerifySession logs an error when a request fails."""
    errors: list[str] = []

    def error_logger(message, **_):
        errors.append(message)

    dummy_logger = types.SimpleNamespace(
        debug=lambda *_, **__: None,
        error=error_logger,
    )
    monkeypatch.setattr(requests_module, "log", dummy_logger)

    class BoomError(RuntimeError):
        pass

    def fake_request(self, method, url, *args, **kwargs):
        raise BoomError("boom")

    monkeypatch.setattr(requests.Session, "request", fake_request, raising=False)

    session = SelectiveVerifySession(whitelist={"fail.com"})

    with pytest.raises(BoomError):
        session.request("GET", "https://fail.com/endpoint")

    assert errors and "fail.com" in errors[0]
