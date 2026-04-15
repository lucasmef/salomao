import asyncio
from types import SimpleNamespace

from app.api.routes import imports as imports_routes
from app.api.routes import purchase_planning as purchase_routes


class _FakeDbSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeUploadFile:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


def test_upload_linx_sales_calls_refresh_orchestrator(monkeypatch) -> None:
    db = _FakeDbSession()
    company = SimpleNamespace(id="company-1")
    refresh_calls: list[tuple[object, object, object]] = []

    monkeypatch.setattr("app.api.routes.imports.get_current_company", lambda current_db: company)
    monkeypatch.setattr("app.api.routes.imports.ensure_pre_import_backup", lambda source: None)
    monkeypatch.setattr(
        "app.api.routes.imports.import_linx_sales",
        lambda current_db, current_company, filename, content: SimpleNamespace(message="ok"),
    )
    monkeypatch.setattr(
        "app.api.routes.imports.build_data_refresh_request",
        lambda source_family, affected_dates=None: {
            "source_family": source_family,
            "affected_dates": tuple(affected_dates or ()),
        },
    )
    monkeypatch.setattr(
        "app.api.routes.imports.finalize_data_refresh",
        lambda current_db, current_company, request: refresh_calls.append(
            (current_db, current_company, request)
        ),
    )

    result = asyncio.run(
        imports_routes.upload_linx_sales(
            db,
            _FakeUploadFile("linx-sales.xls", b"sales"),
        )
    )

    assert result.message == "ok"
    assert refresh_calls == [
        (
            db,
            company,
            {
                "source_family": "sales",
                "affected_dates": (),
            },
        )
    ]


def test_trigger_inter_statement_sync_calls_refresh_orchestrator(monkeypatch) -> None:
    db = _FakeDbSession()
    company = SimpleNamespace(id="company-1")
    payload = SimpleNamespace(account_id=None, start_date=None, end_date=None)
    refresh_calls: list[tuple[object, object, object]] = []

    monkeypatch.setattr("app.api.routes.imports.get_current_company", lambda current_db: company)
    monkeypatch.setattr(
        "app.api.routes.imports.sync_inter_statement",
        lambda current_db, current_company, account_id=None, start_date=None, end_date=None: SimpleNamespace(message="ok"),
    )
    monkeypatch.setattr(
        "app.api.routes.imports.build_data_refresh_request",
        lambda source_family, affected_dates=None: {
            "source_family": source_family,
            "affected_dates": tuple(affected_dates or ()),
        },
    )
    monkeypatch.setattr(
        "app.api.routes.imports.finalize_data_refresh",
        lambda current_db, current_company, request: refresh_calls.append(
            (current_db, current_company, request)
        ),
    )

    result = imports_routes.trigger_inter_statement_sync(payload, db)

    assert result.message == "ok"
    assert refresh_calls == [
        (
            db,
            company,
            {
                "source_family": "inter_statement",
                "affected_dates": (),
            },
        )
    ]


def test_post_purchase_plan_calls_refresh_orchestrator(monkeypatch) -> None:
    db = _FakeDbSession()
    company = SimpleNamespace(id="company-1")
    current_user = SimpleNamespace(id="user-1")
    refresh_calls: list[tuple[object, object, object]] = []

    monkeypatch.setattr("app.api.routes.purchase_planning.get_current_company", lambda current_db: company)
    monkeypatch.setattr(
        "app.api.routes.purchase_planning.create_purchase_plan",
        lambda current_db, current_company, payload, actor_user: SimpleNamespace(id="plan-1"),
    )
    monkeypatch.setattr(
        "app.api.routes.purchase_planning.build_data_refresh_request",
        lambda source_family, affected_dates=None: {
            "source_family": source_family,
            "affected_dates": tuple(affected_dates or ()),
        },
    )
    monkeypatch.setattr(
        "app.api.routes.purchase_planning.finalize_data_refresh",
        lambda current_db, current_company, request: refresh_calls.append(
            (current_db, current_company, request)
        ),
    )

    result = purchase_routes.post_purchase_plan(SimpleNamespace(), db, current_user)

    assert result.id == "plan-1"
    assert db.commits == 1
    assert refresh_calls == [
        (
            db,
            company,
            {
                "source_family": "purchase_payables",
                "affected_dates": (),
            },
        )
    ]
