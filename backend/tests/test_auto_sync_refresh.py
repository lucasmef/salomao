from types import SimpleNamespace

from app.services import auto_sync_refresh


def test_finalize_auto_sync_refresh_invalidates_and_warms_finance_caches(monkeypatch) -> None:
    events: list[tuple[object, ...]] = []
    company = SimpleNamespace(id="company-1")

    monkeypatch.setattr(
        auto_sync_refresh,
        "build_data_refresh_request",
        lambda source_family: events.append(("build", source_family))
        or SimpleNamespace(source_family=source_family),
    )
    monkeypatch.setattr(
        auto_sync_refresh,
        "finalize_data_refresh",
        lambda db, current_company, request: events.append(
            ("finalize", db, current_company.id, request.source_family)
        ),
    )
    monkeypatch.setattr(
        auto_sync_refresh,
        "refresh_finance_analytics_caches",
        lambda db, current_company, *, include_sales_history: events.append(
            ("warm", db, current_company.id, include_sales_history)
        ),
    )

    auto_sync_refresh.finalize_auto_sync_refresh("db", company)

    assert events == [
        ("build", "auto_sync"),
        ("finalize", "db", "company-1", "auto_sync"),
        ("warm", "db", "company-1", True),
    ]


def test_run_has_refreshable_changes_checks_all_auto_sync_messages() -> None:
    assert auto_sync_refresh.run_has_refreshable_changes(
        SimpleNamespace(
            inter_statement_message=None,
            inter_charges_message=None,
            customers_message=None,
            receivables_message=None,
            movements_message="Movimentos sincronizados.",
            products_message=None,
            purchase_payables_message=None,
        )
    )
    assert not auto_sync_refresh.run_has_refreshable_changes(
        SimpleNamespace(
            inter_statement_message=None,
            inter_charges_message=None,
            customers_message=None,
            receivables_message=None,
            movements_message=None,
            products_message=None,
            purchase_payables_message=None,
        )
    )
