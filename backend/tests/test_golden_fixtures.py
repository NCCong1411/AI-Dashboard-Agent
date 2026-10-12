"""Independent checks for the provisional P0-T02 import-file baseline."""

from __future__ import annotations

import importlib.util
import json
import re
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
AUDIT_SCRIPT = ROOT / "backend" / "scripts" / "audit_db.py"
GOLDEN_RESULTS = ROOT / "backend" / "tests" / "fixtures" / "golden_results.json"
GOLDEN_QUERIES = ROOT / "backend" / "tests" / "fixtures" / "golden_queries.sql"
CENT = Decimal("0.01")


def load_import_audit() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("audit_db_for_golden", AUDIT_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_import(module.DEFAULT_SQL)


@pytest.fixture(scope="module")
def source() -> dict[str, Any]:
    return load_import_audit()


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return json.loads(GOLDEN_RESULTS.read_text(encoding="utf-8"))


def selected_rows(
    source: dict[str, Any],
    fact: str,
    date_column: str,
    scope: str,
    start_date: str,
    end_date_exclusive: str,
) -> list[dict[str, Any]]:
    properties = {
        row["property_id"]: row for row in source["_rows"]["properties"]
    }
    return [
        row
        for row in source["_rows"][fact]
        if start_date <= row[date_column] < end_date_exclusive
        and (scope == "ALL" or properties[row["property_id"]]["state"] == scope)
    ]


def decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def calculate_case(
    source: dict[str, Any], case: dict[str, Any], kind: str
) -> dict[str, Any]:
    scope = case["scope"]
    start = case["start_date"]
    end = case["end_date_exclusive"]
    if kind == "sales":
        rows = selected_rows(source, "transactions", "transaction_date", scope, start, end)
        total = sum((row["sale_price"] for row in rows), Decimal(0)) if rows else None
        with localcontext() as context:
            context.prec = 40
            average = total / len(rows) if rows else None
        return {
            "status": "ok" if rows else "no_data",
            "sales_value": decimal_text(total),
            "transaction_count": len(rows),
            "average_sale_value": decimal_text(average),
            "sold_property_count": len({row["property_id"] for row in rows}),
        }
    if kind == "offers":
        rows = selected_rows(source, "offers", "offer_date", scope, start, end)
        accepted = sum(row["status"] == "accepted" for row in rows)
        with localcontext() as context:
            context.prec = 40
            rate = Decimal(accepted) / len(rows) if rows else None
        return {
            "status": "ok" if rows else "no_data",
            "offer_count": len(rows),
            "accepted_offer_count": accepted,
            "accepted_offer_rate": decimal_text(rate),
        }
    if kind == "repairs":
        rows = selected_rows(source, "repairs", "repair_date", scope, start, end)
        cost = sum((row["cost"] for row in rows), Decimal(0)) if rows else None
        return {
            "status": "ok" if rows else "no_data",
            "repair_row_count": len(rows),
            "repair_cost": decimal_text(cost),
        }
    raise AssertionError(f"unknown fact kind: {kind}")


def expected_groups(case: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if "expected" in case:
        return list(case["expected"].items())
    for kind in ("sales", "offers", "repairs"):
        key = f"expected_{kind}"
        if key in case:
            return [(kind, case[key])]
    raise AssertionError(f"case has no expected result: {case['id']}")


def test_source_identity_and_case_coverage(
    source: dict[str, Any], golden: dict[str, Any]
) -> None:
    assert source["source"]["sha256"] == golden["source"]["sha256"]
    assert golden["evidence_status"] == (
        "provisional_sql_import_baseline_live_database_unverified"
    )
    assert set(golden["kpi_ids"]) == {
        "sales_value",
        "transaction_count",
        "average_sale_value",
        "sold_property_count",
        "offer_count",
        "accepted_offer_rate",
        "repair_cost",
    }
    ids = {case["id"] for case in golden["cases"]}
    assert {f"all_time_{scope}" for scope in ("all", "ca", "tx")} <= ids
    assert {f"calendar_2025_{scope}" for scope in ("all", "ca", "tx")} <= ids
    assert {f"empty_2030_{scope}" for scope in ("all", "ca", "tx")} <= ids
    assert sum(case["id"].endswith("_inclusive") for case in golden["cases"]) == 6


def test_every_golden_result_matches_import_rows(
    source: dict[str, Any], golden: dict[str, Any]
) -> None:
    for case in golden["cases"]:
        for kind, expected in expected_groups(case):
            actual = calculate_case(source, case, kind)
            for field, value in actual.items():
                assert expected[field] == value, (case["id"], kind, field)
            if kind == "sales" and "average_fraction" in expected:
                fraction = expected["average_fraction"]
                if actual["transaction_count"] == 0:
                    assert fraction is None
                else:
                    assert fraction == {
                        "numerator": actual["sales_value"],
                        "denominator": actual["transaction_count"],
                    }
            if kind == "offers" and "accepted_offer_fraction" in expected:
                fraction = expected["accepted_offer_fraction"]
                if actual["offer_count"] == 0:
                    assert fraction is None
                else:
                    assert fraction == {
                        "numerator": actual["accepted_offer_count"],
                        "denominator": actual["offer_count"],
                    }


def test_money_is_exact_to_cent(source: dict[str, Any], golden: dict[str, Any]) -> None:
    for case in golden["cases"]:
        for kind, expected in expected_groups(case):
            money_fields = (
                ("sales_value", "average_sale_value")
                if kind == "sales"
                else ("repair_cost",)
                if kind == "repairs"
                else ()
            )
            actual = calculate_case(source, case, kind)
            for money_field in money_fields:
                if expected[money_field] is not None:
                    assert Decimal(actual[money_field]).quantize(CENT) == Decimal(
                        expected[money_field]
                    ).quantize(CENT)


def test_distinct_property_and_accepted_denominator(
    source: dict[str, Any], golden: dict[str, Any]
) -> None:
    all_time = next(case for case in golden["cases"] if case["id"] == "all_time_all")
    expected = all_time["expected"]
    assert expected["sales"]["sold_property_count"] == 125
    assert expected["sales"]["transaction_count"] == 1000
    assert expected["offers"]["accepted_offer_fraction"] == {
        "numerator": 35,
        "denominator": 125,
    }
    statuses = {row["status"] for row in source["_rows"]["offers"]}
    assert statuses - {"accepted", "rejected"}


def prepared_body(sql_text: str, name: str) -> str:
    match = re.search(
        rf"PREPARE\s+{re.escape(name)}\b.*?\bAS\s+(.*?);",
        sql_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, name
    return match.group(1).lower()


def test_golden_sql_uses_one_fact_and_correct_contract() -> None:
    sql_text = GOLDEN_QUERIES.read_text(encoding="utf-8")
    families = {
        "golden_sales": ("transactions", {"offers", "repairs"}),
        "golden_sales_dimensions": ("transactions", {"offers", "repairs"}),
        "golden_offers": ("offers", {"transactions", "repairs"}),
        "golden_offer_dimensions": ("offers", {"transactions", "repairs"}),
        "golden_repairs": ("repairs", {"transactions", "offers"}),
        "golden_repair_dimensions": ("repairs", {"transactions", "offers"}),
    }
    for name, (fact, forbidden_facts) in families.items():
        body = prepared_body(sql_text, name)
        assert f"public.{fact}" in body
        assert not any(f"public.{forbidden}" in body for forbidden in forbidden_facts)
        date_column = {
            "transactions": "transaction_date",
            "offers": "offer_date",
            "repairs": "repair_date",
        }[fact]
        assert f"{date_column} >= $2" in body
        assert f"{date_column} < $3" in body
    sales = prepared_body(sql_text, "golden_sales")
    offers = prepared_body(sql_text, "golden_offers")
    assert "count(distinct t.property_id)" in sales
    assert "filter (where o.status = 'accepted')" in offers
    assert "/ nullif(count(o.offer_id), 0)" in offers

