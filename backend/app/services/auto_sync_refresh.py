from __future__ import annotations

from app.db.models.security import Company
from app.services.data_refresh import build_data_refresh_request, finalize_data_refresh


def finalize_auto_sync_refresh(db, company: Company) -> None:
    refresh_request = build_data_refresh_request("auto_sync")
    finalize_data_refresh(db, company, refresh_request)
