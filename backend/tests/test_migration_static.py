"""Static/unit safety checks for P1-T02 metadata and Alembic SQL."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import Settings
from app.db.connections import (
    create_runtime_engine,
    require_migration_ready,
    validate_separate_database_roles,
)
from app.db.migration_safety import (
    include_owned_name,
    include_owned_object,
    reject_injected_connection,
)
from app.db.models import Base


EXPECTED_TABLES = {
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


def settings(**values: object) -> Settings:
    return Settings(app_env="test", _env_file=None, **values)


def test_metadata_is_confined_to_app_schema() -> None:
    assert {table.name for table in Base.metadata.tables.values()} == EXPECTED_TABLES
    assert {table.schema for table in Base.metadata.tables.values()} == {"app"}


def test_version_and_approval_idempotency_constraints_exist() -> None:
    table = Base.metadata.tables["app.dashboard_versions"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("dashboard_id", "version_number") in unique_columns
    assert ("dashboard_id", "draft_hash") in unique_columns
    assert ("approval_key",) in unique_columns
    assert ("id", "dashboard_id") in unique_columns
    dashboards = Base.metadata.tables["app.dashboards"]
    current_version_fk = next(
        constraint
        for constraint in dashboards.foreign_key_constraints
        if constraint.name == "fk_dashboards_current_version_same_dashboard"
    )
    assert tuple(current_version_fk.column_keys) == ("current_version_id", "id")
    assert tuple(element.target_fullname for element in current_version_fk.elements) == (
        "app.dashboard_versions.id",
        "app.dashboard_versions.dashboard_id",
    )
    checkpoints = Base.metadata.tables["app.agent_checkpoints"]
    checkpoint_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in checkpoints.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("thread_id", "checkpoint_namespace", "checkpoint_id") in checkpoint_uniques


def test_migration_requires_backup_and_separate_role() -> None:
    with pytest.raises(RuntimeError, match="MIGRATION_DATABASE_URL"):
        require_migration_ready(settings())
    with pytest.raises(RuntimeError, match="MIGRATION_BACKUP_VERIFIED"):
        require_migration_ready(
            settings(migration_database_url="postgresql+psycopg://migrator:secret@db/test")
        )
    duplicate_role = settings(
        migration_database_url="postgresql+psycopg://same:migration-secret@db/test",
        runtime_database_url="postgresql+psycopg://same:runtime-secret@db/test",
        migration_backup_verified=True,
    )
    with pytest.raises(RuntimeError, match="must be different"):
        validate_separate_database_roles(duplicate_role)


def test_secret_values_are_masked() -> None:
    configured = settings(
        migration_database_url="postgresql+psycopg://migrator:do-not-print@db/test"
    )
    assert "do-not-print" not in repr(configured)
    assert "do-not-print" not in str(configured.migration_database_url)


def test_blank_urls_are_unset_and_operation_credentials_are_independent() -> None:
    configured = settings(
        runtime_database_url="   ",
        migration_database_url="postgresql+psycopg://migrator:secret@db/test",
        migration_backup_verified=True,
    )
    assert configured.runtime_database_url is None
    assert require_migration_ready(configured).username == "migrator"

    runtime_only = settings(
        runtime_database_url="postgresql+psycopg://runtime:secret@db/test",
        migration_database_url=" ",
    )
    engine = create_runtime_engine(runtime_only)
    try:
        assert engine.url.username == "runtime"
    finally:
        engine.dispose()


def test_autogenerate_filters_reflected_public_tables() -> None:
    public_table = Table("properties", MetaData(), Column("id", Integer), schema="public")
    default_schema_table = Table("properties", MetaData(), Column("id", Integer))
    app_table = Table("dashboards", MetaData(), Column("id", Integer), schema="app")
    assert include_owned_name("public", "schema", {}) is False
    assert include_owned_name(None, "schema", {}) is False
    assert (
        include_owned_name(
            "properties", "table", {"schema_name": "public", "schema_qualified_table_name": "public.properties"}
        )
        is False
    )
    assert include_owned_object(public_table, "properties", "table", True, None) is False
    assert (
        include_owned_object(default_schema_table, "properties", "table", True, None)
        is False
    )
    assert include_owned_object(app_table, "dashboards", "table", True, None) is True


def test_injected_alembic_connection_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="Injected Alembic connections are disabled"):
        reject_injected_connection(object())
    reject_injected_connection(None)


def test_inherited_role_audit_covers_database_and_relation_ownership() -> None:
    integration_source = (
        BACKEND / "tests" / "integration" / "test_migrations.py"
    ).read_text(encoding="utf-8")
    assert "has_database_privilege(r.oid, current_database(), 'CREATE')" in integration_source
    assert "WHERE c.relowner=r.oid" in integration_source
    assert "n.nspname IN ('app','analytics','public')" in integration_source


def test_backup_script_rejects_url_options_instead_of_discarding_them() -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")
    script = BACKEND.parent / "scripts" / "backup-db.ps1"
    environment = os.environ.copy()
    environment["MIGRATION_DATABASE_URL"] = (
        "postgresql+psycopg://migrator:do-not-print@localhost/test_db?sslmode=require"
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-File", str(script)],
        env=environment,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "query parameters and fragments are not supported" in output
    assert "do-not-print" not in output
    assert "postgresql+psycopg://" in script.read_text(encoding="utf-8")


def test_offline_migration_sql_only_creates_owned_schemas() -> None:
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
            "0001_app_schema",
            "--sql",
        ],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    sql = result.stdout.lower()
    assert "create schema app" in sql
    assert "create schema analytics" in sql
    assert "create table app.users" in sql
    assert "create table app.dashboard_versions" in sql
    assert "foreign key(current_version_id, id)" in sql
    assert "redacted-value" not in result.stdout + result.stderr
    source_tables = {
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
    assert not any(
        f"alter table public.{table}" in sql
        or f"drop table public.{table}" in sql
        or f"truncate table public.{table}" in sql
        for table in source_tables
    )

