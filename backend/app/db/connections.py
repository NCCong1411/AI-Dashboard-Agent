"""Separated runtime and migration SQLAlchemy connection factories."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

from app.config import Settings


ReaderScope = Literal["ALL", "CA", "TX"]
READER_URL_FIELDS: dict[ReaderScope, str] = {
    "ALL": "reader_all_database_url",
    "CA": "reader_ca_database_url",
    "TX": "reader_tx_database_url",
}
READER_GROUPS: dict[ReaderScope, str] = {
    "ALL": "analytics_reader_all",
    "CA": "analytics_reader_ca",
    "TX": "analytics_reader_tx",
}


def _configured_url(settings: Settings, field: str) -> URL:
    secret = getattr(settings, field)
    value = secret.get_secret_value() if secret is not None else ""
    if not value:
        raise RuntimeError(f"{field.upper()} is required for this database operation")
    return make_url(value)


def validate_separate_database_roles(settings: Settings) -> None:
    """Reject reusing the migration principal as the API runtime principal."""
    if settings.runtime_database_url is None or settings.migration_database_url is None:
        return
    runtime = _configured_url(settings, "runtime_database_url")
    migration = _configured_url(settings, "migration_database_url")
    if runtime.username == migration.username:
        raise RuntimeError("runtime and migration database roles must be different")


def require_migration_ready(settings: Settings) -> URL:
    """Enforce explicit credential separation and the operator backup gate."""
    validate_separate_database_roles(settings)
    url = _configured_url(settings, "migration_database_url")
    if not settings.migration_backup_verified:
        raise RuntimeError(
            "MIGRATION_BACKUP_VERIFIED=true is required after validating a fresh backup"
        )
    return url


def create_runtime_engine(settings: Settings) -> Engine:
    validate_separate_database_roles(settings)
    return create_engine(
        _configured_url(settings, "runtime_database_url"),
        pool_pre_ping=True,
        hide_parameters=True,
    )


def create_migration_engine(settings: Settings) -> Engine:
    return create_engine(
        require_migration_ready(settings),
        poolclass=NullPool,
        hide_parameters=True,
    )


def create_reader_engine(settings: Settings, scope: ReaderScope) -> Engine:
    """Create a pool for exactly one server-authorized analytics scope."""
    if scope not in READER_URL_FIELDS:
        raise ValueError("reader scope must be one of ALL, CA, or TX")
    selected_field = READER_URL_FIELDS[scope]
    selected_url = _configured_url(settings, selected_field)
    selected_user = selected_url.username
    if not selected_user:
        raise RuntimeError(f"{selected_field.upper()} must include an explicit database role")
    configured_fields = (
        "runtime_database_url",
        "migration_database_url",
        *READER_URL_FIELDS.values(),
    )
    for field in configured_fields:
        if field == selected_field or getattr(settings, field) is None:
            continue
        if _configured_url(settings, field).username == selected_user:
            raise RuntimeError(
                f"{selected_field.upper()} must use a database role distinct from {field.upper()}"
            )
    engine = create_engine(selected_url, pool_pre_ping=True, hide_parameters=True)

    @event.listens_for(engine, "connect")
    def validate_reader_principal(dbapi_connection, _connection_record) -> None:
        """Fail before a pooled connection can serve analytics outside its scope."""
        expected_group = READER_GROUPS[scope]
        groups = tuple(READER_GROUPS.values())
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(
                """
                SELECT current_user, r.rolsuper, r.rolcreatedb, r.rolcreaterole,
                       r.rolreplication, r.rolbypassrls, r.rolinherit,
                       has_database_privilege(current_user,current_database(),'CREATE'),
                       has_schema_privilege(current_user,'public','CREATE'),
                       has_schema_privilege(current_user,'analytics','CREATE'),
                       has_schema_privilege(current_user,'app','CREATE'),
                       EXISTS (
                         SELECT 1 FROM pg_class c
                         JOIN pg_namespace n ON n.oid=c.relnamespace
                         WHERE c.relowner=r.oid
                           AND n.nspname IN ('public','analytics','app')
                       ),
                       EXISTS (
                         SELECT 1 FROM pg_attribute a
                         JOIN pg_class c ON c.oid=a.attrelid
                         JOIN pg_namespace n ON n.oid=c.relnamespace
                         WHERE n.nspname='public'
                           AND c.relname IN (
                             'agencies','agents','agent_agencies','appraisers',
                             'clients','inspectors','neighbourhoods','payment_methods',
                             'property_types','properties','appraisals','inspections',
                             'offers','property_neighbourhoods','repairs','transactions'
                           )
                           AND a.attnum > 0 AND NOT a.attisdropped
                           AND has_column_privilege(
                             current_user,c.oid,a.attnum,'SELECT'
                           )
                           AND NOT (
                             (c.relname='properties' AND a.attname IN
                               ('property_id','city','property_type_id','state')) OR
                             (c.relname='transactions' AND a.attname IN
                               ('transaction_id','agent_id','property_id','sale_price',
                                'transaction_date')) OR
                             (c.relname='offers' AND a.attname IN
                               ('offer_id','offer_amount','offer_date','property_id','status')) OR
                             (c.relname='repairs' AND a.attname IN
                               ('repair_id','cost','property_id','repair_date')) OR
                             (c.relname='property_types' AND a.attname IN
                               ('property_type_id','type_name'))
                           )
                       ),
                       EXISTS (
                         SELECT 1 FROM pg_class c
                         JOIN pg_namespace n ON n.oid=c.relnamespace
                         WHERE n.nspname='public'
                           AND c.relname IN (
                             'agencies','agents','agent_agencies','appraisers',
                             'clients','inspectors','neighbourhoods','payment_methods',
                             'property_types','properties','appraisals','inspections',
                             'offers','property_neighbourhoods','repairs','transactions'
                           )
                           AND (
                             has_table_privilege(current_user,c.oid,'INSERT') OR
                             has_table_privilege(current_user,c.oid,'UPDATE') OR
                             has_table_privilege(current_user,c.oid,'DELETE') OR
                             has_table_privilege(current_user,c.oid,'TRUNCATE') OR
                             has_table_privilege(current_user,c.oid,'REFERENCES') OR
                             has_table_privilege(current_user,c.oid,'TRIGGER') OR
                             has_any_column_privilege(current_user,c.oid,'INSERT') OR
                             has_any_column_privilege(current_user,c.oid,'UPDATE') OR
                             has_any_column_privilege(current_user,c.oid,'REFERENCES')
                           )
                       )
                FROM pg_roles r WHERE r.rolname=current_user
                """
            )
            principal = cursor.fetchone()
            if principal is None:
                raise RuntimeError("analytics reader principal is not a PostgreSQL role")
            current_user = principal[0]
            if current_user != selected_user:
                raise RuntimeError("analytics reader URL resolved to an unexpected principal")
            if tuple(principal[1:6]) != (False,) * 5 or principal[6] is not True:
                raise RuntimeError("analytics reader principal has unsafe role attributes")
            if any(principal[7:]):
                raise RuntimeError("analytics reader principal has DDL or ownership privileges")

            cursor.execute(
                "SELECT pg_has_role(current_user,%s,'MEMBER'), "
                "pg_has_role(current_user,%s,'MEMBER'), "
                "pg_has_role(current_user,%s,'MEMBER')",
                groups,
            )
            memberships = dict(zip(groups, cursor.fetchone(), strict=True))
            if memberships.get(expected_group) is not True or sum(memberships.values()) != 1:
                raise RuntimeError("analytics reader principal has an invalid scope membership")
            cursor.execute(
                "SELECT pg_has_role(current_user,%s,'USAGE')", (expected_group,)
            )
            if cursor.fetchone()[0] is not True:
                raise RuntimeError("analytics reader scope membership is not inherited")

            cursor.execute(
                """
                SELECT r.rolname, r.rolsuper, r.rolcreatedb, r.rolcreaterole,
                       r.rolreplication, r.rolbypassrls,
                       has_database_privilege(r.oid,current_database(),'CREATE'),
                       has_schema_privilege(r.oid,'public','CREATE'),
                       has_schema_privilege(r.oid,'analytics','CREATE'),
                       has_schema_privilege(r.oid,'app','CREATE'),
                       EXISTS (
                         SELECT 1 FROM pg_class c
                         JOIN pg_namespace n ON n.oid=c.relnamespace
                         WHERE c.relowner=r.oid
                           AND n.nspname IN ('public','analytics','app')
                       )
                FROM pg_roles r
                WHERE r.rolname <> current_user
                  AND pg_has_role(current_user,r.oid,'MEMBER')
                """
            )
            for member_role in cursor.fetchall():
                if member_role[0] != expected_group:
                    raise RuntimeError(
                        "analytics reader principal belongs to an unexpected role"
                    )
                if any(member_role[1:]):
                    raise RuntimeError(
                        "analytics reader group has unsafe privileges or ownership"
                    )
        finally:
            cursor.close()
            dbapi_connection.rollback()

    return engine
