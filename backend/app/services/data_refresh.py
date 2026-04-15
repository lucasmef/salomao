from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from app.db.models.security import Company
from app.services.cache_invalidation import clear_finance_analytics_caches
from app.services.purchase_planning import clear_purchase_planning_overview_cache

SourceFamily = Literal[
    "sales",
    "receivables",
    "customers",
    "products",
    "movements",
    "purchase_payables",
    "inter_statement",
    "inter_charges",
    "auto_sync",
    "ofx",
    "table_import",
    "historical_cashbook",
]

PRIMARY_API_SOURCE_FAMILIES: frozenset[SourceFamily] = frozenset(
    {
        "sales",
        "receivables",
        "customers",
        "products",
        "movements",
        "purchase_payables",
        "inter_statement",
        "inter_charges",
        "auto_sync",
    }
)

BACKUP_MANUAL_SOURCE_FAMILIES: frozenset[SourceFamily] = frozenset(
    {
        "ofx",
        "table_import",
        "historical_cashbook",
    }
)


@dataclass(frozen=True, slots=True)
class DataRefreshRequest:
    source_family: SourceFamily
    affected_dates: tuple[date, ...] = ()
    touches_finance_analytics: bool = False
    touches_sales_history: bool = False
    touches_purchase_planning: bool = False
    is_primary_api: bool = False
    is_backup_manual: bool = False


_SOURCE_REFRESH_MATRIX: dict[SourceFamily, DataRefreshRequest] = {
    "sales": DataRefreshRequest(
        source_family="sales",
        touches_finance_analytics=True,
        touches_sales_history=True,
        is_primary_api=True,
    ),
    "receivables": DataRefreshRequest(
        source_family="receivables",
        touches_finance_analytics=True,
        is_primary_api=True,
    ),
    "customers": DataRefreshRequest(
        source_family="customers",
        is_primary_api=True,
    ),
    "products": DataRefreshRequest(
        source_family="products",
        touches_purchase_planning=True,
        is_primary_api=True,
    ),
    "movements": DataRefreshRequest(
        source_family="movements",
        touches_finance_analytics=True,
        touches_purchase_planning=True,
        is_primary_api=True,
    ),
    "purchase_payables": DataRefreshRequest(
        source_family="purchase_payables",
        touches_finance_analytics=True,
        touches_purchase_planning=True,
        is_primary_api=True,
    ),
    "inter_statement": DataRefreshRequest(
        source_family="inter_statement",
        touches_finance_analytics=True,
        is_primary_api=True,
    ),
    "inter_charges": DataRefreshRequest(
        source_family="inter_charges",
        touches_finance_analytics=True,
        is_primary_api=True,
    ),
    "auto_sync": DataRefreshRequest(
        source_family="auto_sync",
        touches_finance_analytics=True,
        touches_sales_history=True,
        touches_purchase_planning=True,
        is_primary_api=True,
    ),
    "ofx": DataRefreshRequest(
        source_family="ofx",
        touches_finance_analytics=True,
        is_backup_manual=True,
    ),
    "table_import": DataRefreshRequest(
        source_family="table_import",
        touches_finance_analytics=True,
        touches_purchase_planning=True,
        is_backup_manual=True,
    ),
    "historical_cashbook": DataRefreshRequest(
        source_family="historical_cashbook",
        touches_finance_analytics=True,
        is_backup_manual=True,
    ),
}


def build_data_refresh_request(
    source_family: SourceFamily,
    *,
    affected_dates: tuple[date, ...] | list[date] | None = None,
) -> DataRefreshRequest:
    base_request = _SOURCE_REFRESH_MATRIX[source_family]
    return DataRefreshRequest(
        source_family=base_request.source_family,
        affected_dates=tuple(affected_dates or ()),
        touches_finance_analytics=base_request.touches_finance_analytics,
        touches_sales_history=base_request.touches_sales_history,
        touches_purchase_planning=base_request.touches_purchase_planning,
        is_primary_api=base_request.is_primary_api,
        is_backup_manual=base_request.is_backup_manual,
    )


def finalize_data_refresh(
    db: Session,
    company: Company,
    request: DataRefreshRequest,
) -> None:
    if request.touches_purchase_planning:
        clear_purchase_planning_overview_cache(company.id)

    if request.touches_finance_analytics:
        clear_finance_analytics_caches(
            company.id,
            include_sales_history=request.touches_sales_history,
            db=db,
            company=company,
            affected_dates=request.affected_dates,
        )
