"""Dashboard, widget, and precision-safe query result contracts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .analysis import AnalysisPlan, CATALOG_VERSION, KPIId, SCHEMA_VERSION


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuerySpec(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    plan: AnalysisPlan


class WidgetSpec(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=160)
    chart: Literal["card", "line", "bar", "horizontal_bar", "pie", "donut", "table"]
    query_id: str
    kpi: KPIId
    dimension: str | None = None


class DashboardSpec(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    catalog_version: Literal[CATALOG_VERSION]
    title: str = Field(min_length=1, max_length=255)
    queries: Annotated[list[QuerySpec], Field(min_length=1, max_length=6)]
    widgets: Annotated[list[WidgetSpec], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def references_are_valid(self) -> "DashboardSpec":
        queries = {query.id: query.plan for query in self.queries}
        if len(queries) != len(self.queries):
            raise ValueError("query ids must be unique")
        if len({widget.id for widget in self.widgets}) != len(self.widgets):
            raise ValueError("widget ids must be unique")
        for widget in self.widgets:
            plan = queries.get(widget.query_id)
            if plan is None or widget.kpi not in plan.kpis:
                raise ValueError("widget must reference a query containing its KPI")
            if widget.dimension is not None and widget.dimension not in plan.dimensions:
                raise ValueError("widget dimension must be present in its query")
        return self


class ResultColumn(StrictModel):
    name: str
    type: Literal["string", "integer", "decimal", "date", "datetime"]
    unit: str | None = None


class QueryResult(StrictModel):
    columns: list[ResultColumn]
    rows: list[dict[str, Any]]
    latency_ms: int = Field(ge=0)
    status: Literal["ok", "no_data", "error"]
    warnings: list[str] = Field(default_factory=list)

    @field_validator("rows", mode="before")
    @classmethod
    def encode_decimal_as_exact_string(cls, rows: Any) -> Any:
        if not isinstance(rows, list):
            return rows
        return [
            {key: format(value, "f") if isinstance(value, Decimal) else value for key, value in row.items()}
            for row in rows
        ]

    @model_validator(mode="after")
    def validate_shape_and_decimal_encoding(self) -> "QueryResult":
        column_names = {column.name for column in self.columns}
        decimal_names = {column.name for column in self.columns if column.type == "decimal"}
        for row in self.rows:
            if set(row) != column_names:
                raise ValueError("each row must exactly match result columns")
            for name in decimal_names:
                value = row[name]
                if value is not None:
                    if not isinstance(value, str):
                        raise ValueError("decimal cells must use base-10 JSON strings")
                    try:
                        Decimal(value)
                    except InvalidOperation as error:
                        raise ValueError("invalid decimal cell") from error
        return self
