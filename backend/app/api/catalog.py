"""Role-aware business catalog endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.analytics.catalog import DIMENSION_COLUMNS, KPI_CATALOG
from app.auth.dependencies import CurrentUser
from app.schemas.analysis import CATALOG_VERSION, DimensionId, KPIId


router = APIRouter(prefix="/api", tags=["catalog"])


class CatalogKPI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: KPIId
    label_vi: str
    description_vi: str
    unit: str
    grain: str
    date_field: str
    dimensions: list[DimensionId]
    view: str | None = None
    sql_expression: str | None = None
    source_columns: list[str] | None = None


class CatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_version: str
    default_date_range: str
    money_encoding: str
    kpis: list[CatalogKPI]
    dimension_fields: dict[DimensionId, str] | None = None


@router.get("/catalog", response_model=CatalogResponse, response_model_exclude_none=True)
def get_catalog(user: CurrentUser) -> CatalogResponse:
    builder = user.role == "builder"
    return CatalogResponse(
        catalog_version=CATALOG_VERSION,
        default_date_range="all_available_data",
        money_encoding="base_10_string",
        dimension_fields=DIMENSION_COLUMNS if builder else None,
        kpis=[
            CatalogKPI(
                id=item.id,
                label_vi=item.label_vi,
                description_vi=item.description_vi,
                unit=item.unit,
                grain=item.grain,
                date_field=item.date_field,
                dimensions=list(item.dimensions),
                view=item.view if builder else None,
                sql_expression=item.sql_expression if builder else None,
                source_columns=list(item.source_columns) if builder else None,
            )
            for item in KPI_CATALOG.values()
        ],
    )
