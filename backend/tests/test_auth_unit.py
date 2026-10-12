"""Fast unit checks for password/session/auth boundary primitives."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.auth.dependencies import require_builder, require_trusted_origin
from app.auth.dependencies import database_session
from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import hash_session_token, new_session_token
from app.config import Settings
from app.db.models import User
from fastapi.exceptions import RequestValidationError


def settings() -> Settings:
    return Settings(app_env="test", _env_file=None)


def request(origin: str | None) -> Request:
    headers = [] if origin is None else [(b"origin", origin.encode())]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers})


def test_argon2_password_and_opaque_session_token() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "correct horse battery staple") is True
    assert verify_password(password_hash, "wrong password") is False
    assert verify_password(None, "wrong password") is False
    token = new_session_token()
    assert token not in hash_session_token(token)
    assert len(hash_session_token(token)) == 64


def test_origin_and_builder_role_are_server_side_guards() -> None:
    require_trusted_origin(request("http://localhost:3000"), settings())
    with pytest.raises(HTTPException) as missing:
        require_trusted_origin(request(None), settings())
    assert missing.value.status_code == 403
    duplicate = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [
                (b"origin", b"http://localhost:3000"),
                (b"origin", b"http://evil.invalid"),
            ],
        }
    )
    with pytest.raises(HTTPException) as duplicated:
        require_trusted_origin(duplicate, settings())
    assert duplicated.value.status_code == 403
    viewer = User(
        username="viewer",
        password_hash="not-returned",
        role="viewer",
        scope_profile="CA",
    )
    with pytest.raises(HTTPException) as denied:
        require_builder(viewer)
    assert denied.value.status_code == 403


def test_seed_script_contains_no_password_literal() -> None:
    source = (BACKEND / "scripts" / "seed_users.py").read_text(encoding="utf-8")
    assert "SEED_BUILDER_ALL_PASSWORD" in source
    assert "SEED_VIEWER_CA_PASSWORD" in source
    assert "no demo password is hardcoded" in source
    assert "UserSession.revoked_at.is_(None)" in source
    assert ".with_for_update()" in source
    login_source = (BACKEND / "app" / "api" / "auth.py").read_text(encoding="utf-8")
    assert ".with_for_update()" in login_source


def test_validation_error_does_not_echo_submitted_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    main = importlib.import_module("app.main")
    secret = "sensitive-password-value"
    error = {
        "type": "string_too_long",
        "loc": ("body", "password"),
        "msg": "String should have at most 1024 characters",
        "input": secret,
        "ctx": {"max_length": 1024},
    }
    exception = RequestValidationError([error])
    response = asyncio.run(main.sanitized_validation_error(request(None), exception))
    payload = json.loads(response.body)
    assert response.status_code == 422
    assert secret not in response.body.decode()
    assert "input" not in payload["detail"][0]
    assert "ctx" not in payload["detail"][0]

    def no_database_needed():
        yield None

    main.app.dependency_overrides[database_session] = no_database_needed
    try:
        with TestClient(main.app) as client:
            route_response = client.post(
                "/api/auth/login",
                headers={"Origin": "http://localhost:3000"},
                json={"username": "someone", "password": secret * 100},
            )
        assert route_response.status_code == 422
        assert secret not in route_response.text
        assert "input" not in route_response.json()["detail"][0]
    finally:
        main.app.dependency_overrides.clear()
