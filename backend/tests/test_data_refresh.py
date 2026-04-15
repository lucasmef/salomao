from datetime import date

from app.services.data_refresh import (
    BACKUP_MANUAL_SOURCE_FAMILIES,
    PRIMARY_API_SOURCE_FAMILIES,
    build_data_refresh_request,
)


def test_primary_api_source_families_are_explicit() -> None:
    assert "purchase_payables" in PRIMARY_API_SOURCE_FAMILIES
    assert "inter_statement" in PRIMARY_API_SOURCE_FAMILIES
    assert "inter_charges" in PRIMARY_API_SOURCE_FAMILIES
    assert "ofx" not in PRIMARY_API_SOURCE_FAMILIES



def test_backup_manual_source_families_are_explicit() -> None:
    assert "ofx" in BACKUP_MANUAL_SOURCE_FAMILIES
    assert "table_import" in BACKUP_MANUAL_SOURCE_FAMILIES
    assert "historical_cashbook" in BACKUP_MANUAL_SOURCE_FAMILIES
    assert "sales" not in BACKUP_MANUAL_SOURCE_FAMILIES



def test_build_data_refresh_request_marks_purchase_payables_as_primary_api() -> None:
    refresh_request = build_data_refresh_request(
        "purchase_payables",
        affected_dates=[date(2026, 4, 14)],
    )

    assert refresh_request.source_family == "purchase_payables"
    assert refresh_request.is_primary_api is True
    assert refresh_request.is_backup_manual is False
    assert refresh_request.touches_finance_analytics is True
    assert refresh_request.touches_purchase_planning is True
    assert refresh_request.affected_dates == (date(2026, 4, 14),)



def test_build_data_refresh_request_marks_ofx_as_backup_manual() -> None:
    refresh_request = build_data_refresh_request("ofx")

    assert refresh_request.source_family == "ofx"
    assert refresh_request.is_primary_api is False
    assert refresh_request.is_backup_manual is True
    assert refresh_request.touches_finance_analytics is True
    assert refresh_request.touches_purchase_planning is False
