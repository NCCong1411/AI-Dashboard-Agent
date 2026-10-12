"""Authentication lifecycle tests against an explicit PostgreSQL test database."""

from __future__ import annotations

import importlib
import os
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as OrmSession

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.auth.dependencies import database_session, require_builder, runtime_engine
from app.auth.passwords import hash_password
from app.auth.sessions import hash_session_token
from app.config import get_settings
from app.db.models import Session, User
from scripts.seed_users import ACCOUNTS, seed


@pytest.fixture
def auth_context(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, object, User, User]]:
    value = os.getenv("AUTH_TEST_DATABASE_URL", "")
    if not value:
        pytest.skip("requires AUTH_TEST_DATABASE_URL for an actual PostgreSQL runtime login")
    url = make_url(value)
    if "test" not in (url.database or "").lower():
        pytest.fail("refusing auth integration test: database name must contain 'test'")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("RUNTIME_DATABASE_URL", value)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    get_settings.cache_clear()
    runtime_engine.cache_clear()
    engine = create_engine(url)
    suffix = uuid.uuid4().hex[:10]
    with OrmSession(engine) as database, database.begin():
        builder = User(
            username=f"auth_builder_{suffix}",
            password_hash=hash_password("builder integration password"),
            role="builder",
            scope_profile="TX",
        )
        viewer = User(
            username=f"auth_viewer_{suffix}",
            password_hash=hash_password("viewer integration password"),
            role="viewer",
            scope_profile="CA",
        )
        database.add_all((builder, viewer))
    with OrmSession(engine) as database:
        builder = database.scalar(select(User).where(User.username == f"auth_builder_{suffix}"))
        viewer = database.scalar(select(User).where(User.username == f"auth_viewer_{suffix}"))
        assert builder is not None and viewer is not None
        database.expunge_all()

    def override_database() -> Iterator[OrmSession]:
        with OrmSession(engine) as database:
            yield database

    main = importlib.import_module("app.main")
    main = importlib.reload(main)
    main.app.dependency_overrides[database_session] = override_database
    with TestClient(main.app) as client:
        yield client, engine, builder, viewer
    main.app.dependency_overrides.clear()
    with OrmSession(engine) as database, database.begin():
        database.execute(delete(Session).where(Session.user_id.in_((builder.id, viewer.id))))
        database.execute(delete(User).where(User.id.in_((builder.id, viewer.id))))
    engine.dispose()
    runtime_engine.cache_clear()
    get_settings.cache_clear()


def test_login_fixation_expiry_revocation_and_server_identity(auth_context) -> None:
    client, engine, builder, viewer = auth_context
    origin = {"Origin": "http://localhost:3000"}
    assert client.post(
        "/api/auth/login",
        headers={"Origin": "http://evil.invalid"},
        json={"username": builder.username, "password": "builder integration password"},
    ).status_code == 403

    fixed_token = "attacker-fixed-session-token"
    with OrmSession(engine) as database, database.begin():
        database.add(
            Session(
                user_id=builder.id,
                token_hash=hash_session_token(fixed_token),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    client.cookies.set(
        "dashboard_session", fixed_token, domain="testserver.local", path="/"
    )
    response = client.post(
        "/api/auth/login",
        headers=origin,
        json={"username": builder.username, "password": "builder integration password"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "username": builder.username,
        "role": "builder",
        "scope_profile": "TX",
    }
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    issued_token = client.cookies.get("dashboard_session")
    assert issued_token and issued_token != fixed_token
    with OrmSession(engine) as database:
        fixed = database.scalar(
            select(Session).where(Session.token_hash == hash_session_token(fixed_token))
        )
        assert fixed is not None and fixed.revoked_at is not None

    assert client.get("/api/auth/me").json()["scope_profile"] == "TX"
    assert client.post(
        "/api/auth/login",
        headers=origin,
        json={
            "username": builder.username,
            "password": "builder integration password",
            "role": "viewer",
        },
    ).status_code == 422

    with OrmSession(engine) as database, database.begin():
        active = database.scalar(
            select(Session).where(Session.token_hash == hash_session_token(issued_token))
        )
        assert active is not None
        active.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get("/api/auth/me").status_code == 401

    response = client.post(
        "/api/auth/login",
        headers=origin,
        json={"username": builder.username, "password": "builder integration password"},
    )
    assert response.status_code == 200
    logout_token = client.cookies.get("dashboard_session")
    assert client.post("/api/auth/logout", headers=origin).status_code == 204
    with OrmSession(engine) as database:
        revoked = database.scalar(
            select(Session).where(Session.token_hash == hash_session_token(logout_token))
        )
        assert revoked is not None and revoked.revoked_at is not None
    assert client.get("/api/auth/me").status_code == 401

    with pytest.raises(HTTPException) as denied:
        require_builder(viewer)
    assert denied.value.status_code == 403


def test_demo_seed_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    value = os.getenv("AUTH_TEST_DATABASE_URL", "")
    if not value:
        pytest.skip("requires AUTH_TEST_DATABASE_URL for seed integration")
    url = make_url(value)
    if "test" not in (url.database or "").lower():
        pytest.fail("refusing seed integration test: database name must contain 'test'")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("RUNTIME_DATABASE_URL", value)
    for *_, variable in ACCOUNTS:
        monkeypatch.setenv(variable, f"integration-only-{variable.lower()}")
    get_settings.cache_clear()
    engine = create_engine(url)
    reset_session_id = uuid.uuid4()
    usernames = [account[0] for account in ACCOUNTS]
    with OrmSession(engine) as database:
        existing = {
            user.username: (user.password_hash, user.role, user.scope_profile, user.is_active)
            for user in database.scalars(select(User).where(User.username.in_(usernames)))
        }
    try:
        seed()
        with OrmSession(engine) as database, database.begin():
            reset_user = database.scalar(
                select(User).where(User.username == ACCOUNTS[0][0])
            )
            assert reset_user is not None
            database.add(
                Session(
                    id=reset_session_id,
                    user_id=reset_user.id,
                    token_hash=hash_session_token(uuid.uuid4().hex),
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        seed()
        with OrmSession(engine) as database:
            seeded = list(database.scalars(select(User).where(User.username.in_(usernames))))
            assert len(seeded) == 4
            assert {(user.username, user.role, user.scope_profile) for user in seeded} == {
                (username, role, scope) for username, role, scope, _ in ACCOUNTS
            }
            reset_session = database.get(Session, reset_session_id)
            assert reset_session is not None and reset_session.revoked_at is not None
    finally:
        with OrmSession(engine) as database, database.begin():
            database.execute(delete(Session).where(Session.id == reset_session_id))
            created_ids = list(
                database.scalars(
                    select(User.id).where(
                        User.username.in_(set(usernames) - set(existing))
                    )
                )
            )
            if created_ids:
                database.execute(delete(Session).where(Session.user_id.in_(created_ids)))
                database.execute(delete(User).where(User.id.in_(created_ids)))
            for username, values in existing.items():
                user = database.scalar(select(User).where(User.username == username))
                assert user is not None
                user.password_hash, user.role, user.scope_profile, user.is_active = values
        engine.dispose()
        get_settings.cache_clear()
