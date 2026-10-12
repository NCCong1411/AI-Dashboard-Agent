"""Destructive migration cycle against an explicitly restored test database only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings


SOURCE_TABLES = {
    "agencies",
    "agents",
    "agent_agencies",
    "appraisers",
    "clients",
    "inspectors",
    "neighbourhoods",
    "payment_methods",
    "property_types",
    "properties",
    "appraisals",
    "inspections",
    "offers",
    "property_neighbourhoods",
    "repairs",
    "transactions",
}
APP_TABLES = {
    "users",
    "sessions",
    "dashboards",
    "dashboard_versions",
    "conversations",
    "conversation_messages",
    "agent_checkpoints",
    "usage_records",
    "audit_events",
}
READER_TEST_URLS = {
    "analytics_reader_all": "READER_ALL_TEST_DATABASE_URL",
    "analytics_reader_ca": "READER_CA_TEST_DATABASE_URL",
    "analytics_reader_tx": "READER_TX_TEST_DATABASE_URL",
}


def integration_url() -> str:
    url = os.getenv("MIGRATION_TEST_DATABASE_URL", "")
    restored = os.getenv("MIGRATION_TEST_BACKUP_RESTORED", "").lower() == "true"
    if not url or not restored:
        pytest.skip(
            "requires MIGRATION_TEST_DATABASE_URL and MIGRATION_TEST_BACKUP_RESTORED=true"
        )
    database = make_url(url).database or ""
    if "test" not in database.lower():
        pytest.fail("refusing migration integration test: database name must contain 'test'")
    return url


def source_counts(connection) -> dict[str, int]:
    existing = set(inspect(connection).get_table_names(schema="public"))
    assert SOURCE_TABLES <= existing
    return {
        table: connection.execute(text(f'SELECT count(*) FROM public."{table}"')).scalar_one()
        for table in SOURCE_TABLES
    }


def restore_test_reader_memberships(engine) -> None:
    """Re-provision test memberships removed by DROP ROLE during downgrade."""
    memberships: list[tuple[str, str]] = []
    for group, variable in READER_TEST_URLS.items():
        value = os.getenv(variable, "")
        if not value:
            continue
        username = make_url(value).username
        if not username:
            pytest.fail(f"{variable} must contain an explicit login role")
        memberships.append((group, username))
    if not memberships:
        return
    with engine.begin() as connection:
        quote = connection.dialect.identifier_preparer.quote
        for group, username in memberships:
            connection.exec_driver_sql(f"GRANT {quote(group)} TO {quote(username)}")


def test_upgrade_downgrade_upgrade_preserves_source(monkeypatch: pytest.MonkeyPatch) -> None:
    url = integration_url()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MIGRATION_DATABASE_URL", url)
    monkeypatch.setenv("MIGRATION_BACKUP_VERIFIED", "true")
    get_settings.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            before = source_counts(connection)
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert set(inspect(connection).get_table_names(schema="app")) == APP_TABLES
            assert source_counts(connection) == before
        command.downgrade(config, "base")
        with engine.connect() as connection:
            assert not inspect(connection).has_schema("app")
            assert not inspect(connection).has_schema("analytics")
            assert source_counts(connection) == before
        command.upgrade(config, "head")
        restore_test_reader_memberships(engine)
        with engine.connect() as connection:
            assert set(inspect(connection).get_table_names(schema="app")) == APP_TABLES
            assert source_counts(connection) == before
    finally:
        engine.dispose()


def test_runtime_role_has_no_ddl_privileges() -> None:
    url = os.getenv("RUNTIME_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("requires RUNTIME_TEST_DATABASE_URL for the non-owner runtime role")
    if "test" not in (make_url(url).database or "").lower():
        pytest.fail("refusing privilege integration test: database name must contain 'test'")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            superuser, bypass_rls = connection.execute(
                text(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            ).one()
            assert superuser is False
            assert bypass_rls is False
            assert connection.execute(
                text(
                    "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
                )
            ).scalar_one() is False
            assert connection.execute(
                text("SELECT has_schema_privilege(current_user, 'app', 'CREATE')")
            ).scalar_one() is False
            assert connection.execute(
                text("SELECT has_schema_privilege(current_user, 'analytics', 'CREATE')")
            ).scalar_one() is False
            assert connection.execute(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ).scalar_one() is False
            owned = connection.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname IN ('app','analytics','public') AND c.relowner = "
                    "(SELECT oid FROM pg_roles WHERE rolname=current_user)"
                )
            ).scalar_one()
            assert owned == 0
            inherited_roles = connection.execute(
                text(
                    "SELECT r.rolname, r.rolsuper, r.rolbypassrls, "
                    "has_database_privilege(r.oid, current_database(), 'CREATE'), "
                    "has_schema_privilege(r.oid, 'app', 'CREATE'), "
                    "has_schema_privilege(r.oid, 'analytics', 'CREATE'), "
                    "has_schema_privilege(r.oid, 'public', 'CREATE'), "
                    "EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspowner=r.oid "
                    "AND n.nspname IN ('app','analytics','public')), "
                    "EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE c.relowner=r.oid "
                    "AND n.nspname IN ('app','analytics','public')) "
                    "FROM pg_roles r WHERE r.rolname <> current_user "
                    "AND pg_has_role(current_user, r.oid, 'MEMBER')"
                )
            ).all()
            for role in inherited_roles:
                assert role[1:] == (
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                ), (
                    f"runtime can SET ROLE to privileged role {role[0]}"
                )

        # A privilege introspection bug must not turn into an unnoticed DDL grant.
        for schema in ("app", "analytics", "public"):
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    with pytest.raises(DBAPIError):
                        connection.execute(
                            text(f'CREATE TABLE {schema}."__runtime_ddl_probe" (id integer)')
                        )
                finally:
                    transaction.rollback()
    finally:
        engine.dispose()

