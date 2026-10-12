"""Fail-closed ownership boundaries used by Alembic autogenerate."""

from __future__ import annotations

from typing import Any


OWNED_SCHEMAS = frozenset({"app", "analytics"})


def include_owned_name(
    name: str | None, object_type: str, parent_names: dict[str, str | None]
) -> bool:
    """Prevent reflection of default/public and other non-owned schemas."""
    if object_type == "schema":
        return name in OWNED_SCHEMAS
    schema_name = parent_names.get("schema_name")
    if object_type in {"table", "index", "unique_constraint", "foreign_key_constraint"}:
        return schema_name in OWNED_SCHEMAS
    return schema_name is None or schema_name in OWNED_SCHEMAS


def include_owned_object(
    obj: Any,
    _name: str | None,
    _object_type: str,
    reflected: bool,
    _compare_to: Any,
) -> bool:
    """Second guard: never compare a reflected object outside owned schemas."""
    schema = getattr(obj, "schema", None)
    table = getattr(obj, "table", None)
    if schema is None and table is not None:
        schema = getattr(table, "schema", None)
    if reflected:
        return schema in OWNED_SCHEMAS
    return schema is None or schema in OWNED_SCHEMAS


def reject_injected_connection(connection: object | None) -> None:
    """Alembic must construct its own engine from the gated migration URL."""
    if connection is not None:
        raise RuntimeError(
            "Injected Alembic connections are disabled because they bypass migration "
            "credential and backup-target validation"
        )
