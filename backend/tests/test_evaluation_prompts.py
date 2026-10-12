"""Schema, coverage, and semantic checks for the P0-T03 evaluation corpus."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest


PROMPTS = Path(__file__).parent / "evaluation" / "prompts.json"
EXPECTED_COUNTS = {"valid": 20, "ambiguous": 5, "unsupported": 5}
KPI_FACT = {
    "sales_value": "transactions",
    "transaction_count": "transactions",
    "average_sale_value": "transactions",
    "sold_property_count": "transactions",
    "offer_count": "offers",
    "accepted_offer_rate": "offers",
    "repair_cost": "repairs",
}
FACT_DATE = {
    "transactions": "transaction_date",
    "offers": "offer_date",
    "repairs": "repair_date",
}
FACT_DIMENSIONS = {
    "transactions": {"day", "month", "quarter", "year", "state", "city", "property_type", "agent"},
    "offers": {"day", "month", "quarter", "year", "state", "city", "property_type"},
    "repairs": {"day", "month", "quarter", "year", "state", "city", "property_type"},
}


@pytest.fixture(scope="module")
def corpus() -> dict[str, Any]:
    return json.loads(PROMPTS.read_text(encoding="utf-8"))


def test_exact_category_ids_and_phase_counts(corpus: dict[str, Any]) -> None:
    cases = corpus["cases"]
    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert len({case["prompt"] for case in cases}) == 30
    counts = Counter(case["category"] for case in cases)
    assert counts == EXPECTED_COUNTS
    assert corpus["evaluation_policy"]["required_categories"] == EXPECTED_COUNTS
    for category, count in EXPECTED_COUNTS.items():
        assert {case["id"] for case in cases if case["category"] == category} == {
            f"{category}_{index:03d}" for index in range(1, count + 1)
        }

    phase_counts = Counter(case["phase_tag"] for case in cases)
    assert phase_counts == {"phase_2": 23, "phase_4": 7}
    valid_phase_counts = Counter(
        case["phase_tag"] for case in cases if case["category"] == "valid"
    )
    assert valid_phase_counts == {"phase_2": 14, "phase_4": 6}
    for case in cases:
        assert bool(case.get("reevaluate_after_phase_4")) == (
            case["phase_tag"] == "phase_4"
        )


def test_policy_makes_scoring_and_evidence_explicit(corpus: dict[str, Any]) -> None:
    policy = corpus["evaluation_policy"]
    assert policy["total_cases"] == 30
    assert policy["report_mock_and_live_separately"] is True
    assert set(policy["allowed_run_statuses"]) == {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
    assert {"BLOCKED", "NOT_RUN", "SKIPPED"} <= set(policy["not_pass_statuses"])
    assert "sql_result" in policy["valid_case_pass_requires"]
    assert "authorization" in policy["valid_case_pass_requires"]
    assert "required_question" in policy["ambiguous_case_pass_requires"]
    assert "explanation" in policy["unsupported_case_pass_requires"]
    assert "artifact" in policy["evidence_required"]
    assert policy["phase_2_precheck"] == {
        "valid": 14,
        "ambiguous": 4,
        "unsupported": 5,
        "is_release_gate": False,
    }
    assert policy["phase_4_full_run"]["valid_pass_threshold"] == 18


def expected_scope(authorization: dict[str, Any], filters: list[dict[str, Any]]) -> str:
    profile = authorization["session_profile"]
    state_filter = next(
        (item["value"] for item in filters if item["field"] == "state"), None
    )
    if profile == "ALL":
        return state_filter or "ALL"
    if state_filter is not None and state_filter != profile:
        return "EMPTY"
    return profile


def test_valid_oracles_are_complete_and_semantically_consistent(
    corpus: dict[str, Any],
) -> None:
    policy = corpus["evaluation_policy"]
    valid_cases = [case for case in corpus["cases"] if case["category"] == "valid"]
    seen_kpis: set[str] = set()
    seen_dimensions: set[str] = set()
    seen_charts: set[str] = set()
    for case in valid_cases:
        oracle = case["oracle"]
        assert oracle["outcome"] == "plan"
        assert {
            "kpis",
            "dimensions",
            "filters",
            "time",
            "sort",
            "limit",
            "widgets",
            "authorization",
        } <= oracle.keys()
        assert oracle["kpis"] and oracle["widgets"]
        assert len(oracle["widgets"]) <= 8
        assert len(set(oracle["kpis"])) == len(oracle["kpis"])

        expected_phase_kpis = set(policy[f"{case['phase_tag']}_kpis"])
        assert set(oracle["kpis"]) <= expected_phase_kpis
        facts = {KPI_FACT[kpi] for kpi in oracle["kpis"]}
        allowed_dimensions = set.intersection(
            *(FACT_DIMENSIONS[fact] for fact in facts)
        )
        assert set(oracle["dimensions"]) <= allowed_dimensions
        assert set(oracle["dimensions"]) <= set(policy["allowed_dimensions"])

        time = oracle["time"]
        assert time["mode"] in {"absolute", "all_time", "absolute_per_fact"}
        if time["mode"].startswith("absolute"):
            assert date.fromisoformat(time["start"]) < date.fromisoformat(
                time["end_exclusive"]
            )
        if time["mode"] == "absolute_per_fact":
            assert len(facts) > 1
            assert time["date_fields"] == {
                kpi: FACT_DATE[KPI_FACT[kpi]] for kpi in oracle["kpis"]
            }
        else:
            assert len(facts) == 1
            assert time["date_field"] == FACT_DATE[next(iter(facts))]

        for filter_item in oracle["filters"]:
            assert filter_item["field"] in {"state", "city", "property_type", "agent"}
            assert filter_item["op"] == "eq"
            assert filter_item["value"] not in (None, "")
        sortable = set(oracle["kpis"]) | set(oracle["dimensions"])
        assert all(item["field"] in sortable for item in oracle["sort"])
        assert all(item["direction"] in {"asc", "desc"} for item in oracle["sort"])

        widget_kpis = {widget["kpi"] for widget in oracle["widgets"]}
        assert widget_kpis == set(oracle["kpis"])
        for widget in oracle["widgets"]:
            assert widget["chart"] in policy["allowed_charts"]
            if "dimension" in widget:
                assert widget["dimension"] in oracle["dimensions"]
            else:
                assert widget["chart"] == "card"

        authorization = oracle["authorization"]
        assert authorization["actor_role"] == "builder"
        assert authorization["session_profile"] in {"ALL", "CA", "TX"}
        assert authorization["agent_allowed"] is True
        assert authorization["scope_rule"] == "intersect_with_session"
        assert authorization["effective_scope"] == expected_scope(
            authorization, oracle["filters"]
        )
        if authorization["effective_scope"] == "EMPTY":
            assert authorization["expected_data_status"] == "no_data"
            assert authorization["must_not_escalate_scope"] is True

        if len(facts) > 1:
            assert oracle["must_not_join_facts"] is True
            groups = {group["id"]: group["fact"] for group in oracle["query_groups"]}
            assert set(groups.values()) == facts
            assert all(widget["query_group"] in groups for widget in oracle["widgets"])

        seen_kpis.update(oracle["kpis"])
        seen_dimensions.update(oracle["dimensions"])
        seen_charts.update(widget["chart"] for widget in oracle["widgets"])

    assert seen_kpis == set(KPI_FACT)
    assert seen_dimensions == set(policy["allowed_dimensions"])
    assert seen_charts == set(policy["allowed_charts"])


def test_clarification_and_refusal_oracles_never_plan_or_query(
    corpus: dict[str, Any],
) -> None:
    for case in corpus["cases"]:
        if case["category"] == "valid":
            continue
        oracle = case["oracle"]
        assert oracle["must_not_query"] is True
        assert oracle["must_not_generate_plan"] is True
        authorization = oracle["authorization"]
        assert authorization["actor_role"] in {"builder", "viewer"}
        assert authorization["session_profile"] in {"ALL", "CA", "TX"}
        if case["category"] == "ambiguous":
            assert oracle["outcome"] == "clarification"
            assert oracle["reason_codes"]
            assert "?" in oracle["required_question"]
            assert authorization["must_not_change_scope"] is True
        else:
            assert oracle["outcome"] == "refusal"
            assert oracle["reason_code"]
            assert oracle["explanation_must_include"]


def test_security_hitl_and_failure_scenarios_are_defined(
    corpus: dict[str, Any]
) -> None:
    by_id = {case["id"]: case for case in corpus["cases"]}
    viewer = by_id["unsupported_005"]["oracle"]["authorization"]
    assert viewer["actor_role"] == "viewer"
    assert viewer["agent_allowed"] is False
    assert viewer["http_status"] == 403
    assert by_id["unsupported_004"]["oracle"]["reason_code"] == (
        "arbitrary_sql_and_pii_exfiltration"
    )
    empty_scope = by_id["valid_014"]["oracle"]["authorization"]
    assert empty_scope["effective_scope"] == "EMPTY"
    assert empty_scope["must_not_escalate_scope"] is True

    acceptance = (PROMPTS.parents[3] / "docs" / "acceptance-report.md").read_text(
        encoding="utf-8"
    )
    for required in (
        "Stale draft/base version",
        "Double click/retry approval",
        "Restart khi `awaiting_approval`",
        "LLM 429/timeout",
        "DB timeout 5 giây",
        "Một widget lỗi",
    ):
        assert required in acceptance

