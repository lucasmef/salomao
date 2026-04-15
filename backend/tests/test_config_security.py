from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings


def _set_server_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_MODE", "server")
    monkeypatch.setenv("SESSION_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "fedcba9876543210fedcba9876543210")


def test_server_mode_rejects_placeholder_session_secret(monkeypatch) -> None:
    _set_server_env(monkeypatch)
    monkeypatch.setenv("SESSION_SECRET", "troque-isto-por-um-segredo-forte")

    with pytest.raises(ValueError, match="SESSION_SECRET"):
        Settings()


def test_server_mode_rejects_short_field_encryption_key(monkeypatch) -> None:
    _set_server_env(monkeypatch)
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "curta-demais")

    with pytest.raises(ValueError, match="FIELD_ENCRYPTION_KEY"):
        Settings()


def test_server_mode_disables_api_docs_by_default(monkeypatch) -> None:
    _set_server_env(monkeypatch)
    monkeypatch.delenv("API_DOCS_ENABLED", raising=False)
    get_settings.cache_clear()

    import app.main as app_main

    app_main = importlib.reload(app_main)
    app = app_main.create_app()

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None

    get_settings.cache_clear()


def test_frontend_catch_all_blocks_reserved_api_doc_paths() -> None:
    import app.main as app_main

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app_main.configure_frontend_routes(app, blocked_paths=app_main.RESERVED_API_DOC_PATHS)

    client = TestClient(app)

    try:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = client.get(path)
            assert response.status_code == 404
    finally:
        client.close()
