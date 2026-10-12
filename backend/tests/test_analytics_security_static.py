"""Static regression checks for the P1-T03 security boundary."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import Settings
from app.db.connections import create_reader_engine


MIGRATION = BACKEND / "alembic" / "versions" / "0002_analytics_security.py"


def settings(**values: object) -> Settings:
    return Settings(app_env="test", _env_file=None, **values)


def offline_sql() -> str:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "MIGRATION_DATABASE_URL": (
                "postgresql+psycopg://migration_role:redacted-value@localhost/test_db"
            ),
            "MIGRATION_BACKUP_VERIFIED": "true",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(BACKEND / "alembic.ini"),
            "upgrade",
            "head",
            "--sql",
        ],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "redacted-value" not in result.stdout + result.stderr
    return result.stdout.lower()


def test_reader_engine_has_no_default_scope_and_requires_distinct_roles() -> None:
    configured = settings(
        reader_all_database_url="postgresql+psycopg://reader_all:secret@db/test",
        reader_ca_database_url="postgresql+psycopg://reader_ca:secret@db/test",
        reader_tx_database_url="postgresql+psycopg://reader_tx:secret@db/test",
    )
    engine = create_reader_engine(configured, "CA")
    try:
        assert engine.url.username == "reader_ca"
    finally:
        engine.dispose()
    with pytest.raises(ValueError, match="ALL, CA, or TX"):
        create_reader_engine(configured, "")  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="READER_ALL_DATABASE_URL is required"):
        create_reader_engine(settings(), "ALL")
    with pytest.raises(RuntimeError, match="must use a database role distinct"):
        create_reader_engine(
            settings(
                reader_all_database_url="postgresql+psycopg://shared:one@db/test",
                reader_ca_database_url="postgresql+psycopg://shared:two@db/test",
            ),
            "CA",
        )


def test_security_migration_has_rls_invoker_views_and_column_grants() -> None:
    sql = offline_sql()
    for table in ("properties", "transactions", "offers", "repairs"):
        assert f"alter table public.{table} enable row level security" in sql
        for scope in ("all", "ca", "tx"):
            assert f"create policy {table}_reader_{scope}" in sql
    for view in ("sales", "offers", "repairs"):
        assert f"create view analytics.{view} with (security_invoker = true" in sql
    assert "grant select (property_id, city, property_type_id, state)" in sql
    assert "grant select (transaction_id, agent_id, property_id, sale_price, transaction_date)" in sql
    assert "grant select (offer_id, offer_amount, offer_date, property_id, status)" in sql
    assert "grant select (repair_id, cost, property_id, repair_date)" in sql
    assert "grant select on analytics.sales, analytics.offers, analytics.repairs" in sql


def test_security_migration_contains_no_secret_or_source_dml() -> None:
    source = MIGRATION.read_text(encoding="utf-8").lower()
    assert "password" not in source
    assert "insert into public." not in source
    assert "update public." not in source
    assert "delete from public." not in source
    assert not re.search(r"(?m)^\s*(?:op\.execute\([^\n]*)?truncate\s+", source)
    grant_lines = "\n".join(
        line for line in offline_sql().splitlines() if "grant select (" in line
    )
    for pii_column in ("address", "zip_code", "client_id", "description"):
        assert pii_column not in grant_lines


def test_security_migration_fails_closed_on_public_grants_and_existing_consumers() -> None:
    source = MIGRATION.read_text(encoding="utf-8").lower()
    assert "acl.grantee = 0" in source
    assert "unsafe public schema create privilege" in source
    assert "unsafe public source privileges" in source
    assert "review/removal of existing scoped-table consumers" in source
    assert "aclexplode" in source


def test_reader_factory_registers_live_principal_scope_validation() -> None:
    source = (BACKEND / "app" / "db" / "connections.py").read_text(encoding="utf-8").lower()
    for fragment in (
        'listens_for(engine, "connect")',
        "rolbypassrls",
        "rolinherit",
        "pg_has_role(current_user",
        "has_column_privilege",
        "has_table_privilege",
        "has_any_column_privilege",
        "'usage'",
        "dbapi_connection.rollback()",
        "invalid scope membership",
        "unexpected principal",
        "unexpected role",
    ):
        assert fragment in source
