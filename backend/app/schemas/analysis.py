"""Structured, compiler-safe analysis plan contracts."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CATALOG_VERSION = "1.0.0-import-baseline"
SCHEMA_VERSION = "1.0.0"
KPIId = Literal["sales_value", "transaction_count", "average_sale_value", "sold_property_count"]
DimensionId = Literal["day", "month", "quarter", "year", "state", "city", "property_type", "agent"]
FilterField = Literal["state", "city", "property_type", "agent"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DateRange(StrictModel):
    start: date | None = None
    end_exclusive: date | None = None

    @model_validator(mode="after")
    def ordered_or_all_time(self) -> "DateRange":
        if (self.start is None) != (self.end_exclusive is None):
            raise ValueError("start and end_exclusive must both be set or both be null")
        if self.start is not None and self.end_exclusive <= self.start:
            raise ValueError("end_exclusive must be after start")
        return self


class FilterSpec(StrictModel):
    field: FilterField
    op: Literal["eq", "in"]
    value: str | int | list[str] | list[int]


class SortSpec(StrictModel):
    field: KPIId | DimensionId
    direction: Literal["asc", "desc"] = "asc"


class AnalysisPlan(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    catalog_version: Literal[CATALOG_VERSION]
    kpis: Annotated[list[KPIId], Field(min_length=1, max_length=4)]
    dimensions: Annotated[list[DimensionId], Field(max_length=4)] = Field(default_factory=list)
    filters: Annotated[list[FilterSpec], Field(max_length=12)] = Field(default_factory=list)
    date_range: DateRange = Field(default_factory=DateRange)
    sort: Annotated[list[SortSpec], Field(max_length=4)] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def unique_fields(self) -> "AnalysisPlan":
        if len(set(self.kpis)) != len(self.kpis):
            raise ValueError("kpis must be unique")
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("dimensions must be unique")
        return self
