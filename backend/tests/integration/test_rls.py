"""RLS checks using real PostgreSQL login roles on an explicit test database."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError


READER_GROUPS = {
    "ALL": "analytics_reader_all",
    "CA": "analytics_reader_ca",
    "TX": "analytics_reader_tx",
}
EXPECTED = {
    "ALL": {"transactions": 1000, "sales": "870798679.64", "offers": 125, "repairs": 125},
    "CA": {"transactions": 135, "sales": "107064313.73", "offers": 14, "repairs": 14},
    "TX": {"transactions": 132, "sales": "128635636.80", "offers": 11, "repairs": 18},
}


def reader_url(scope: str) -> URL:
    variable = f"READER_{scope}_TEST_DATABASE_URL"
    value = os.getenv(variable, "")
    if not value:
        pytest.skip(f"requires {variable} for an actual PostgreSQL reader login")
    url = make_url(value)
    if "test" not in (url.database or "").lower():
        pytest.fail(f"refusing RLS integration test: {variable} database must contain 'test'")
    if not url.username:
        pytest.fail(f"{variable} must contain an explicit login role")
    return url


def execute_must_fail(url: URL, statement: str) -> None:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with pytest.raises(DBAPIError) as raised:
                    connection.execute(text(statement))
                sqlstate = getattr(raised.value.orig, "sqlstate", None)
                if sqlstate is None:
                    sqlstate = getattr(raised.value.orig, "pgcode", None)
                assert sqlstate == "42501", (
                    f"expected insufficient_privilege, got SQLSTATE {sqlstate!r}"
                )
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.parametrize("scope", ["ALL", "CA", "TX"])
def test_reader_login_is_least_privileged_and_cannot_switch_scope(scope: str) -> None:
    url = reader_url(scope)
    own_group = READER_GROUPS[scope]
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            attributes = connection.execute(
                text(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                    "FROM pg_roles WHERE rolname=current_user"
                )
            ).one()
            assert tuple(attributes) == (False, False, False, False, False)
            assert connection.execute(
                text("SELECT pg_has_role(current_user, :role, 'MEMBER')"),
                {"role": own_group},
            ).scalar_one() is True
            for other_group in set(READER_GROUPS.values()) - {own_group}:
                assert connection.execute(
                    text("SELECT pg_has_role(current_user, :role, 'MEMBER')"),
                    {"role": other_group},
                ).scalar_one() is False
            assert connection.execute(
                text("SELECT has_database_privilege(current_user,current_database(),'CREATE')")
            ).scalar_one() is False
            for schema in ("public", "analytics", "app"):
                assert connection.execute(
                    text("SELECT has_schema_privilege(current_user,:schema,'CREATE')"),
                    {"schema": schema},
                ).scalar_one() is False
            assert connection.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) "
                    "AND n.nspname IN ('public','analytics','app')"
                )
            ).scalar_one() == 0
            inherited = connection.execute(
                text(
                    "SELECT r.rolname, r.rolsuper, r.rolcreatedb, r.rolcreaterole, "
                    "r.rolreplication, r.rolbypassrls, "
                    "has_database_privilege(r.oid,current_database(),'CREATE'), "
                    "has_schema_privilege(r.oid,'public','CREATE'), "
                    "has_schema_privilege(r.oid,'analytics','CREATE'), "
                    "has_schema_privilege(r.oid,'app','CREATE'), "
                    "EXISTS (SELECT 1 FROM pg_class c WHERE c.relowner=r.oid) "
                    "FROM pg_roles r WHERE r.rolname <> current_user "
                    "AND pg_has_role(current_user,r.oid,'MEMBER')"
                )
            ).all()
            for role in inherited:
                assert tuple(role[1:]) == (False,) * 10, (
                    f"reader can SET ROLE to privileged role {role[0]}"
                )
    finally:
        engine.dispose()

    for other_group in set(READER_GROUPS.values()) - {own_group}:
        execute_must_fail(url, f"SET ROLE {other_group}")


@pytest.mark.parametrize("scope", ["ALL", "CA", "TX"])
def test_direct_tables_and_security_invoker_views_enforce_scope(scope: str) -> None:
    url = reader_url(scope)
    expected = EXPECTED[scope]
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            states = set(
                connection.execute(text("SELECT DISTINCT state FROM public.properties")).scalars()
            )
            if scope != "ALL":
                assert states == {scope}
            direct = connection.execute(
                text(
                    "SELECT count(transaction_id), sum(sale_price) "
                    "FROM public.transactions"
                )
            ).one()
            view = connection.execute(
                text(
                    "SELECT count(transaction_id), sum(sale_price) "
                    "FROM analytics.sales"
                )
            ).one()
            assert direct[0] == view[0] == expected["transactions"]
            assert str(direct[1]) == str(view[1]) == expected["sales"]
            assert connection.execute(
                text("SELECT count(offer_id) FROM public.offers")
            ).scalar_one() == expected["offers"]
            assert connection.execute(
                text("SELECT count(offer_id) FROM analytics.offers")
            ).scalar_one() == expected["offers"]
            assert connection.execute(
                text("SELECT count(repair_id) FROM public.repairs")
            ).scalar_one() == expected["repairs"]
            assert connection.execute(
                text("SELECT count(repair_id) FROM analytics.repairs")
            ).scalar_one() == expected["repairs"]
            if scope != "ALL":
                for view_name in ("sales", "offers", "repairs"):
                    assert connection.execute(
                        text(f"SELECT count(*) FROM analytics.{view_name} WHERE state <> :scope"),
                        {"scope": scope},
                    ).scalar_one() == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("scope", ["ALL", "CA", "TX"])
def test_reader_cannot_read_pii_or_mutate(scope: str) -> None:
    url = reader_url(scope)
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            property_id = connection.execute(
                text("SELECT property_id FROM public.properties ORDER BY property_id LIMIT 1")
            ).scalar_one()
    finally:
        engine.dispose()
    for statement in (
        "SELECT address FROM public.properties LIMIT 1",
        "SELECT client_id FROM public.transactions LIMIT 1",
        "SELECT client_id FROM public.offers LIMIT 1",
        "SELECT description FROM public.repairs LIMIT 1",
        "SELECT email FROM public.clients LIMIT 1",
        "UPDATE public.properties SET city=city WHERE false",
        "DELETE FROM public.offers WHERE false",
        "INSERT INTO public.repairs (cost,description,property_id,repair_date) "
        f"VALUES (0,'probe',{int(property_id)},CURRENT_DATE)",
        'CREATE TABLE analytics."__reader_ddl_probe" (id integer)',
    ):
        execute_must_fail(url, statement)
