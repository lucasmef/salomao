from __future__ import annotations

from app.db.models.security import Company
from app.services.cache_invalidation import refresh_finance_analytics_caches
from app.services.data_refresh import build_data_refresh_request, finalize_data_refresh


def run_has_refreshable_changes(run) -> bool:
    return any(
        message
        for message in (
            run.inter_statement_message,
            run.inter_charges_message,
            run.customers_message,
            run.receivables_message,
            run.movements_message,
            run.products_message,
            run.purchase_payables_message,
        )
    )


def finalize_auto_sync_refresh(db, company: Company) -> None:
    refresh_request = build_data_refresh_request("auto_sync")
    finalize_data_refresh(db, company, refresh_request)
    refresh_finance_analytics_caches(db, company, include_sales_history=True)
