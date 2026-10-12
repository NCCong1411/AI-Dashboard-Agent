"""Versioned phase-2 KPI catalog and semantic validation."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.analysis import AnalysisPlan, CATALOG_VERSION, DimensionId, KPIId


@dataclass(frozen=True)
class KPI:
    id: KPIId
    label_vi: str
    description_vi: str
    unit: str
    grain: str
    date_field: str
    view: str
    sql_expression: str
    source_columns: tuple[str, ...]
    dimensions: tuple[DimensionId, ...]


SALES_DIMENSIONS: tuple[DimensionId, ...] = (
    "day",
    "month",
    "quarter",
    "year",
    "state",
    "city",
    "property_type",
    "agent",
)

KPI_CATALOG: dict[KPIId, KPI] = {
    "sales_value": KPI(
        "sales_value", "Giá trị giao dịch", "Tổng giá trị giao dịch", "dataset_currency",
        "transaction", "transaction_date", "analytics.sales", "SUM(sale_price)",
        ("sale_price",), SALES_DIMENSIONS,
    ),
    "transaction_count": KPI(
        "transaction_count", "Số giao dịch", "Số giao dịch", "transaction",
        "transaction", "transaction_date", "analytics.sales", "COUNT(transaction_id)",
        ("transaction_id",), SALES_DIMENSIONS,
    ),
    "average_sale_value": KPI(
        "average_sale_value", "Giá trị giao dịch trung bình", "Giá trị trung bình trên giao dịch",
        "dataset_currency_per_transaction", "transaction", "transaction_date", "analytics.sales",
        "SUM(sale_price) / NULLIF(COUNT(transaction_id), 0)",
        ("sale_price", "transaction_id"), SALES_DIMENSIONS,
    ),
    "sold_property_count": KPI(
        "sold_property_count", "Số BĐS có giao dịch", "Số bất động sản khác nhau có giao dịch",
        "property", "filtered_transaction_set", "transaction_date", "analytics.sales",
        "COUNT(DISTINCT property_id)", ("property_id",), SALES_DIMENSIONS,
    ),
}

DIMENSION_COLUMNS: dict[DimensionId, str] = {
    "day": "transaction_date",
    "month": "date_trunc('month', transaction_date)",
    "quarter": "date_trunc('quarter', transaction_date)",
    "year": "date_trunc('year', transaction_date)",
    "state": "state",
    "city": "city",
    "property_type": "property_type",
    "agent": "agent_id",
}
FILTER_COLUMNS = {"state": "state", "city": "city", "property_type": "property_type", "agent": "agent_id"}


def validate_plan_semantics(plan: AnalysisPlan) -> None:
    if plan.catalog_version != CATALOG_VERSION:
        raise ValueError("catalog version mismatch")
    for kpi_id in plan.kpis:
        allowed = set(KPI_CATALOG[kpi_id].dimensions)
        unsupported = set(plan.dimensions) - allowed
        if unsupported:
            raise ValueError(f"unsupported dimensions for {kpi_id}: {sorted(unsupported)}")
    for filter_spec in plan.filters:
        if filter_spec.field not in FILTER_COLUMNS:
            raise ValueError(f"unsupported filter field: {filter_spec.field}")
        is_list = isinstance(filter_spec.value, list)
        if (filter_spec.op == "in") != is_list:
            raise ValueError("in requires a list; eq requires a scalar")
