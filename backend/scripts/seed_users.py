"""Idempotently seed four local demo accounts from environment passwords."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.auth.passwords import hash_password
from app.config import Settings, get_settings
from app.db.connections import create_runtime_engine
from app.db.models import Session as UserSession
from app.db.models import User


ACCOUNTS = (
    ("builder_all", "builder", "ALL", "SEED_BUILDER_ALL_PASSWORD"),
    ("viewer_all", "viewer", "ALL", "SEED_VIEWER_ALL_PASSWORD"),
    ("viewer_ca", "viewer", "CA", "SEED_VIEWER_CA_PASSWORD"),
    ("builder_tx", "builder", "TX", "SEED_BUILDER_TX_PASSWORD"),
)


def required_password(settings: Settings, variable: str) -> str:
    secret = getattr(settings, variable.lower())
    if secret is None:
        raise RuntimeError(f"{variable} is required; no demo password is hardcoded")
    return secret.get_secret_value()


def seed() -> None:
    settings = get_settings()
    passwords = {
        variable: required_password(settings, variable) for *_, variable in ACCOUNTS
    }
    engine = create_runtime_engine(settings)
    try:
        with Session(engine) as database, database.begin():
            for username, role, scope, variable in ACCOUNTS:
                user = database.scalar(
                    select(User).where(User.username == username).with_for_update()
                )
                password_hash = hash_password(passwords[variable])
                if user is None:
                    database.add(
                        User(
                            username=username,
                            password_hash=password_hash,
                            role=role,
                            scope_profile=scope,
                        )
                    )
                else:
                    database.execute(
                        update(UserSession)
                        .where(
                            UserSession.user_id == user.id,
                            UserSession.revoked_at.is_(None),
                        )
                        .values(revoked_at=datetime.now(UTC))
                    )
                    user.password_hash = password_hash
                    user.role = role
                    user.scope_profile = scope
                    user.is_active = True
    finally:
        engine.dispose()


if __name__ == "__main__":
    seed()
    print("Seeded 4 demo users without printing credentials.")
