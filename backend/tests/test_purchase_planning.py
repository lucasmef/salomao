from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.services.purchase_planning as purchase_planning_service
from app.db.models import audit as audit_models  # noqa: F401
from app.db.models import finance as finance_models  # noqa: F401
from app.db.models import linx as linx_models  # noqa: F401
from app.db.models import purchasing as purchasing_models  # noqa: F401
from app.db.models.base import Base
from app.db.models.purchasing import Supplier
from app.db.models.security import Company, User
from app.schemas.financial_entry import FinancialEntryCreate
from app.schemas.purchase_planning import (
    PurchaseBrandCreate,
    PurchaseInstallmentDraft,
    PurchaseInvoiceCreate,
    PurchasePlanCreate,
    PurchasePlanUpdate,
    PurchaseReturnCreate,
    PurchaseReturnUpdate,
    SupplierCreate,
    SupplierUpdate,
)
from app.services.bootstrap import ensure_company_catalog, run_company_data_maintenance
from app.services.finance_ops import create_entry
from app.services.purchase_planning import (
    PurchasePlanningFilters,
    build_purchase_planning_overview,
    create_brand,
    create_purchase_invoice,
    create_purchase_plan,
    create_purchase_return,
    delete_purchase_plan,
    delete_purchase_return,
    ensure_purchase_installment_financial_entries,
    list_purchase_invoice_suppliers,
    list_purchase_plans,
    list_purchase_returns,
    parse_purchase_invoice_text,
    reconcile_purchase_invoice_links,
    update_purchase_plan,
    update_purchase_return,
)
from app.services.purchase_planning import (
    create_supplier as create_supplier_service,
)
from app.services.purchase_planning import (
    update_supplier as update_supplier_service,
)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def create_company_context(db: Session) -> tuple[Company, User]:
    company = Company(legal_name="Salomao LTDA", trade_name="Salomao")
    db.add(company)
    db.flush()
    user = User(
        company_id=company.id,
        full_name="Teste",
        email="teste@example.com",
        password_hash="hash",
        role="admin",
    )
    db.add(user)
    db.flush()
    return company, user


def create_supplier(db: Session, company_id: str, name: str) -> Supplier:
    supplier = Supplier(
        company_id=company_id,
        name=name,
        default_payment_term="1x",
        payment_basis="delivery",
        has_purchase_invoices=False,
        is_active=True,
    )
    db.add(supplier)
    db.flush()
    return supplier


def create_collection(
    db: Session,
    company: Company,
    name: str,
    *,
    start_date: date = date(2026, 7, 1),
    end_date: date = date(2026, 7, 31),
) -> purchasing_models.CollectionSeason:
    normalized_name = name.lower()
    season_type = "winter" if "inverno" in normalized_name else "summer"
    collection = purchasing_models.CollectionSeason(
        company_id=company.id,
        name=name,
        season_year=start_date.year,
        season_type=season_type,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
    )
    db.add(collection)
    db.flush()
    return collection


def create_purchase_category(db: Session, company: Company) -> finance_models.Category:
    category = finance_models.Category(
        company_id=company.id,
        name="Compras",
        entry_kind="expense",
        report_group="Compras",
        report_subgroup="Compras",
        is_active=True,
    )
    db.add(category)
    db.flush()
    return category


def create_linx_sale(
    db: Session,
    company: Company,
    *,
    product_code: int,
    amount: Decimal,
    issue_date: datetime,
) -> linx_models.LinxMovement:
    movement = linx_models.LinxMovement(
        company_id=company.id,
        linx_transaction=product_code,
        movement_group="sale",
        movement_type="sale",
        issue_date=issue_date,
        product_code=product_code,
        quantity=Decimal("1"),
        cost_price=Decimal("10.00"),
        net_amount=amount,
        total_amount=amount,
        canceled=False,
        excluded=False,
    )
    db.add(movement)
    db.flush()
    return movement


def test_supplier_can_be_linked_to_multiple_brand_basis_plannings(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    veste = create_supplier(db_session, company.id, "Veste")

    john_john = create_brand(
        db_session,
        company,
        PurchaseBrandCreate(
            name="John John",
            planning_basis="brand",
            linx_brand_names=["John John"],
            supplier_ids=[veste.id],
        ),
        user,
    )
    dudalina = create_brand(
        db_session,
        company,
        PurchaseBrandCreate(
            name="Dudalina",
            planning_basis="brand",
            linx_brand_names=["Dudalina"],
            supplier_ids=[veste.id],
        ),
        user,
    )

    assert john_john.supplier_ids == [veste.id]
    assert dudalina.supplier_ids == [veste.id]
    links = db_session.scalars(
        select(purchasing_models.PurchaseBrandSupplier).where(
            purchasing_models.PurchaseBrandSupplier.supplier_id == veste.id,
        )
    ).all()
    assert len(links) == 2


def test_brand_basis_uses_product_brand_and_does_not_create_supplier_row(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    collection = create_collection(db_session, company, "Inverno 2026")
    veste = create_supplier(db_session, company.id, "Veste")
    john_john = create_brand(
        db_session,
        company,
        PurchaseBrandCreate(
            name="John John",
            planning_basis="brand",
            linx_brand_names=["John John"],
            supplier_ids=[veste.id],
        ),
        user,
    )
    dudalina = create_brand(
        db_session,
        company,
        PurchaseBrandCreate(
            name="Dudalina",
            planning_basis="brand",
            linx_brand_names=["Dudalina"],
            supplier_ids=[veste.id],
        ),
        user,
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            brand_id=john_john.id,
            supplier_ids=[veste.id],
            collection_id=collection.id,
            title="Pedido John John",
            purchased_amount=Decimal("1000.00"),
        ),
        user,
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            brand_id=dudalina.id,
            supplier_ids=[veste.id],
            collection_id=collection.id,
            title="Pedido Dudalina",
            purchased_amount=Decimal("800.00"),
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=101,
        brand_name="John John",
        supplier_name="Veste",
        collection_name="Inverno 2026",
    )
    create_linx_product(
        db_session,
        company,
        linx_code=102,
        brand_name="Dudalina",
        supplier_name="Veste",
        collection_name="Inverno 2026",
    )
    create_linx_sale(
        db_session,
        company,
        product_code=101,
        amount=Decimal("300.00"),
        issue_date=datetime(2026, 7, 10),
    )
    create_linx_sale(
        db_session,
        company,
        product_code=102,
        amount=Decimal("200.00"),
        issue_date=datetime(2026, 7, 11),
    )
    create_linx_purchase_movement(
        db_session,
        company,
        linx_transaction=101,
        product_code=101,
        document_number="101",
        movement_type="purchase_return",
        total_amount=Decimal("50.00"),
        launch_date=date(2026, 7, 12),
    )
    create_linx_purchase_movement(
        db_session,
        company,
        linx_transaction=102,
        product_code=102,
        document_number="102",
        movement_type="purchase_return",
        total_amount=Decimal("70.00"),
        launch_date=date(2026, 7, 13),
    )

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters(year=2026), mode="planning")
    rows_by_brand = {row.brand_name: row for row in overview.rows}

    assert rows_by_brand["John John"].sold_total == Decimal("300.00")
    assert rows_by_brand["John John"].returns_total == Decimal("50.00")
    assert rows_by_brand["Dudalina"].sold_total == Decimal("200.00")
    assert rows_by_brand["Dudalina"].returns_total == Decimal("70.00")
    assert "Veste" not in rows_by_brand
    assert "Não classificados" not in rows_by_brand


def test_brand_basis_unmatched_product_brand_supplier_does_not_create_supplier_row(
    db_session: Session,
) -> None:
    company, user = create_company_context(db_session)
    create_collection(db_session, company, "Inverno 2026")
    veste = create_supplier(db_session, company.id, "Veste")
    create_brand(
        db_session,
        company,
        PurchaseBrandCreate(
            name="John John",
            planning_basis="brand",
            linx_brand_names=["John John"],
            supplier_ids=[veste.id],
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=103,
        brand_name="Marca Sem Mapeamento",
        supplier_name="Veste",
        collection_name="Inverno 2026",
    )
    create_linx_purchase_movement(
        db_session,
        company,
        linx_transaction=103,
        product_code=103,
        document_number="103",
        movement_type="purchase_return",
        total_amount=Decimal("90.00"),
        launch_date=date(2026, 7, 10),
    )

    overview = build_purchase_planning_overview(
        db_session,
        company,
        PurchasePlanningFilters(year=2026),
        mode="planning",
    )
    rows_by_brand = {row.brand_name: row for row in overview.rows}

    assert "Veste" not in rows_by_brand
    assert "Não classificados" not in rows_by_brand


def create_linx_product(
    db: Session,
    company: Company,
    *,
    linx_code: int,
    supplier_name: str,
    collection_name: str,
    brand_name: str | None = None,
) -> linx_models.LinxProduct:
    product = linx_models.LinxProduct(
        company_id=company.id,
        linx_code=linx_code,
        description=f"Produto {linx_code}",
        supplier_name=supplier_name,
        collection_name=collection_name,
        brand_name=brand_name,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def create_linx_purchase_movement(
    db: Session,
    company: Company,
    *,
    linx_transaction: int,
    product_code: int,
    document_number: str,
    movement_type: str,
    total_amount: Decimal,
    launch_date: date,
) -> linx_models.LinxMovement:
    movement = linx_models.LinxMovement(
        company_id=company.id,
        linx_transaction=linx_transaction,
        movement_group="purchase",
        movement_type=movement_type,
        product_code=product_code,
        document_number=document_number,
        launch_date=datetime.combine(launch_date, datetime.min.time()),
        total_amount=total_amount,
        net_amount=total_amount,
        quantity=Decimal("1.00"),
        cost_price=total_amount,
        canceled=False,
        excluded=False,
    )
    db.add(movement)
    db.flush()
    return movement


def create_linx_sale_movement(
    db: Session,
    company: Company,
    *,
    linx_transaction: int,
    product_code: int,
    document_number: str,
    movement_type: str = "sale",
    net_amount: Decimal,
    launch_date: date | None = None,
    issue_date: date | None = None,
    quantity: Decimal = Decimal("1.00"),
    cost_price: Decimal = Decimal("0.00"),
) -> linx_models.LinxMovement:
    movement = linx_models.LinxMovement(
        company_id=company.id,
        linx_transaction=linx_transaction,
        movement_group="sale",
        movement_type=movement_type,
        product_code=product_code,
        document_number=document_number,
        launch_date=datetime.combine(launch_date, datetime.min.time()) if launch_date else None,
        issue_date=datetime.combine(issue_date, datetime.min.time()) if issue_date else None,
        total_amount=net_amount,
        net_amount=net_amount,
        quantity=quantity,
        cost_price=cost_price,
        canceled=False,
        excluded=False,
    )
    db.add(movement)
    db.flush()
    return movement


def create_generic_expense_category(db: Session, company: Company) -> finance_models.Category:
    category = finance_models.Category(
        company_id=company.id,
        name="Operacional",
        entry_kind="expense",
        report_group="Despesas",
        report_subgroup="Operacional",
        is_active=True,
    )
    db.add(category)
    db.flush()
    return category


def build_payload(*, supplier_ids: list[str], title: str) -> PurchasePlanCreate:
    return PurchasePlanCreate(
        supplier_ids=supplier_ids,
        title=title,
        order_date=date(2026, 3, 24),
        expected_delivery_date=date(2026, 4, 10),
        purchased_amount=Decimal("1000.00"),
        payment_term="3x",
        status="planned",
    )


def test_create_purchase_plan_allows_reusing_supplier_in_multiple_plans(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Unico")

    first_plan = create_purchase_plan(
        db_session,
        company,
        build_payload(supplier_ids=[supplier.id], title="Compra A"),
        user,
    )
    second_plan = create_purchase_plan(
        db_session,
        company,
        build_payload(supplier_ids=[supplier.id], title="Compra B"),
        user,
    )

    assert first_plan.supplier_ids == [supplier.id]
    assert second_plan.supplier_ids == [supplier.id]


def test_update_purchase_plan_allows_reusing_supplier_from_other_plan(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier_a = create_supplier(db_session, company.id, "Fornecedor A")
    supplier_b = create_supplier(db_session, company.id, "Fornecedor B")

    first_plan = create_purchase_plan(
        db_session,
        company,
        build_payload(supplier_ids=[supplier_a.id], title="Compra A"),
        user,
    )
    second_plan = create_purchase_plan(
        db_session,
        company,
        build_payload(supplier_ids=[supplier_b.id], title="Compra B"),
        user,
    )
    db_session.commit()

    kept_supplier_update = PurchasePlanUpdate(
        supplier_ids=[supplier_a.id],
        title="Compra A revisada",
        order_date=date(2026, 3, 24),
        expected_delivery_date=date(2026, 4, 15),
        purchased_amount=Decimal("1500.00"),
        payment_term="4x",
        status="confirmed",
    )
    updated_plan = update_purchase_plan(db_session, company, first_plan.id, kept_supplier_update, user)
    assert updated_plan.title == "Compra A revisada"
    assert updated_plan.supplier_ids == [supplier_a.id]

    reused_supplier_update = PurchasePlanUpdate(
        supplier_ids=[supplier_b.id],
        title="Compra A conflito",
        order_date=date(2026, 3, 24),
        expected_delivery_date=date(2026, 4, 20),
        purchased_amount=Decimal("1800.00"),
        payment_term="4x",
        status="planned",
    )
    updated_again = update_purchase_plan(db_session, company, first_plan.id, reused_supplier_update, user)

    assert updated_again.supplier_ids == [supplier_b.id]
    assert second_plan.supplier_ids == [supplier_b.id]


def test_purchase_return_crud_flow(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Devolucao")

    created = create_purchase_return(
        db_session,
        company,
        PurchaseReturnCreate(
            supplier_id=supplier.id,
            return_date=date(2026, 3, 31),
            amount=Decimal("245.90"),
            invoice_number="NF-100",
            status="request_open",
            notes="Devolucao parcial",
        ),
        user,
    )
    db_session.commit()

    assert created.supplier_id == supplier.id
    assert created.amount == Decimal("245.90")
    assert created.invoice_number == "NF-100"
    assert created.status == "request_open"

    listed = list_purchase_returns(db_session, company, year=2026, limit=20)
    assert len(listed) == 1
    assert listed[0].supplier_name == supplier.name

    updated = update_purchase_return(
        db_session,
        company,
        created.id,
        PurchaseReturnUpdate(
            supplier_id=supplier.id,
            return_date=date(2026, 4, 1),
            amount=Decimal("300.00"),
            invoice_number="NF-101",
            status="factory_pending",
            notes="Devolucao ajustada",
        ),
        user,
    )
    db_session.commit()

    assert updated.return_date == date(2026, 4, 1)
    assert updated.amount == Decimal("300.00")
    assert updated.invoice_number == "NF-101"
    assert updated.status == "factory_pending"

    delete_purchase_return(db_session, company, created.id, user)
    db_session.commit()

    assert list_purchase_returns(db_session, company, year=2026, limit=20) == []


def test_purchase_return_approval_does_not_generate_refund_entry(
    db_session: Session,
) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Aprovado")

    created = create_purchase_return(
        db_session,
        company,
        PurchaseReturnCreate(
            supplier_id=supplier.id,
            return_date=date(2026, 4, 1),
            amount=Decimal("180.50"),
            invoice_number="NF-200",
            status="refund_approved",
            notes="Reembolso aprovado sem lancamento automatico",
        ),
        user,
    )
    db_session.flush()

    purchase_return = db_session.get(purchasing_models.PurchaseReturn, created.id)
    assert purchase_return is not None
    assert purchase_return.refund_entry_id is None
    refund_entries = list(
        db_session.scalars(
            select(finance_models.FinancialEntry).where(
                finance_models.FinancialEntry.company_id == company.id,
                finance_models.FinancialEntry.source_system == "purchase_return_workflow",
                finance_models.FinancialEntry.is_deleted.is_(False),
            )
        )
    )
    assert refund_entries == []


def test_purchase_return_update_does_not_generate_refund_entry(
    db_session: Session,
) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Workflow")

    created = create_purchase_return(
        db_session,
        company,
        PurchaseReturnCreate(
            supplier_id=supplier.id,
            return_date=date(2026, 4, 1),
            amount=Decimal("180.50"),
            invoice_number="NF-200",
            status="request_open",
            notes="Aguardando retorno da fabrica",
        ),
        user,
    )
    db_session.flush()

    update_purchase_return(
        db_session,
        company,
        created.id,
        PurchaseReturnUpdate(
            supplier_id=supplier.id,
            return_date=date(2026, 4, 1),
            amount=Decimal("180.50"),
            invoice_number="NF-200",
            status="refund_approved",
            notes="Salto direto permitido",
        ),
        user,
    )
    db_session.flush()

    purchase_return = db_session.get(purchasing_models.PurchaseReturn, created.id)
    assert purchase_return is not None
    assert purchase_return.refund_entry_id is None

    active_refund_entries = list(
        db_session.scalars(
            select(finance_models.FinancialEntry).where(
                finance_models.FinancialEntry.company_id == company.id,
                finance_models.FinancialEntry.source_system == "purchase_return_workflow",
                finance_models.FinancialEntry.is_deleted.is_(False),
            )
        )
    )
    assert active_refund_entries == []


def test_purchase_return_update_preserves_existing_refund_entry(
    db_session: Session,
) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Antigo")
    legacy_category = finance_models.Category(
        company_id=company.id,
        code="LEGACY-RET",
        name="Transferencia entre Contas",
        entry_kind="transfer",
        report_group="Movimentacoes Internas",
        report_subgroup="Transferencias Internas",
        is_active=True,
    )
    db_session.add(legacy_category)
    created = create_purchase_return(
        db_session,
        company,
        PurchaseReturnCreate(
            supplier_id=supplier.id,
            return_date=date(2026, 4, 1),
            amount=Decimal("180.50"),
            invoice_number="NF-200",
            status="request_open",
            notes="Aguardando retorno da fabrica",
        ),
        user,
    )
    db_session.flush()
    purchase_return = db_session.get(purchasing_models.PurchaseReturn, created.id)
    assert purchase_return is not None
    legacy_entry = finance_models.FinancialEntry(
        company_id=company.id,
        category_id=legacy_category.id,
        supplier_id=supplier.id,
        entry_type="historical_purchase_return",
        status="open",
        title="Recebivel antigo",
        description="Recebivel gerado automaticamente ao aprovar devolucao de compra",
        counterparty_name=supplier.name,
        document_number="NF-200",
        issue_date=date(2026, 4, 15),
        competence_date=date(2026, 4, 15),
        due_date=date(2026, 4, 15),
        principal_amount=Decimal("180.50"),
        total_amount=Decimal("180.50"),
        paid_amount=Decimal("0.00"),
        source_system="purchase_return_workflow",
        source_reference=purchase_return.id,
        is_deleted=False,
    )
    db_session.add(legacy_entry)
    db_session.flush()
    purchase_return.refund_entry_id = legacy_entry.id
    db_session.flush()

    update_purchase_return(
        db_session,
        company,
        created.id,
        PurchaseReturnUpdate(
            supplier_id=supplier.id,
            return_date=date(2026, 4, 1),
            amount=Decimal("180.50"),
            invoice_number="NF-200",
            status="refunded",
            notes="Recebivel antigo preservado",
        ),
        user,
    )
    db_session.flush()
    db_session.refresh(legacy_entry)
    assert legacy_entry.entry_type == "historical_purchase_return"
    assert legacy_entry.category_id == legacy_category.id
    assert legacy_entry.is_deleted is False

    delete_purchase_return(db_session, company, created.id, user)
    db_session.flush()
    db_session.refresh(legacy_entry)
    assert legacy_entry.is_deleted is False


def test_purchase_return_refunded_status_does_not_generate_refund_entry(
    db_session: Session,
) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Reembolsado")

    created = create_purchase_return(
        db_session,
        company,
        PurchaseReturnCreate(
            supplier_id=supplier.id,
            return_date=date(2026, 4, 1),
            amount=Decimal("180.50"),
            invoice_number="NF-201",
            status="refunded",
            notes="Reembolso ja recebido fora do fluxo",
        ),
        user,
    )
    db_session.flush()

    purchase_return = db_session.get(purchasing_models.PurchaseReturn, created.id)
    assert purchase_return is not None
    assert purchase_return.refund_entry_id is None
    refund_entries = list(
        db_session.scalars(
            select(finance_models.FinancialEntry).where(
                finance_models.FinancialEntry.company_id == company.id,
                finance_models.FinancialEntry.source_system == "purchase_return_workflow",
                finance_models.FinancialEntry.is_deleted.is_(False),
            )
        )
    )
    assert refund_entries == []


def test_delete_purchase_plan_removes_unlinked_plan(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Livre")
    plan = create_purchase_plan(
        db_session,
        company,
        build_payload(supplier_ids=[supplier.id], title="Compra Livre"),
        user,
    )
    db_session.commit()

    delete_purchase_plan(db_session, company, plan.id, user)
    db_session.commit()

    deleted = db_session.get(purchasing_models.PurchasePlan, plan.id)
    assert deleted is None


def test_delete_purchase_plan_rejects_plan_with_linked_invoice(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor NF")
    plan = create_purchase_plan(
        db_session,
        company,
        build_payload(supplier_ids=[supplier.id], title="Compra com NF"),
        user,
    )
    db_session.flush()

    invoice = purchasing_models.PurchaseInvoice(
        company_id=company.id,
        supplier_id=supplier.id,
        purchase_plan_id=plan.id,
        total_amount=Decimal("500.00"),
        source_type="text",
        status="open",
    )
    db_session.add(invoice)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_purchase_plan(db_session, company, plan.id, user)

    assert exc_info.value.status_code == 409
    assert "notas ou entregas vinculadas" in str(exc_info.value.detail)
    db_session.rollback()


def test_list_purchase_plans_includes_received_and_outstanding_amounts(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Totais")
    collection = create_collection(db_session, company, "Inverno 2026")
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Totais",
            order_date=date(2026, 7, 5),
            expected_delivery_date=date(2026, 7, 10),
            purchased_amount=Decimal("1000.00"),
            payment_term="3x",
            status="planned",
        ),
        user,
    )
    db_session.flush()
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=collection.id,
            purchase_plan_id=plan.id,
            create_plan=False,
            invoice_number="7001",
            series="1",
            issue_date=date(2026, 7, 15),
            entry_date=date(2026, 7, 15),
            total_amount=Decimal("320.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 8, 15),
                    amount=Decimal("320.00"),
                ),
            ],
        ),
        user,
    )
    db_session.commit()

    listed_plan = list_purchase_plans(db_session, company, limit=10)[0]

    assert listed_plan.received_amount == Decimal("320.00")
    assert listed_plan.amount_to_receive == Decimal("680.00")


def test_update_purchase_plan_with_invoice_in_same_collection_keeps_totals(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Atualizacao")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 31),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Fornecedor Atualizacao / Inverno 2026",
            order_date=date(2026, 2, 1),
            expected_delivery_date=date(2026, 2, 1),
            purchased_amount=Decimal("300.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=collection.id,
            create_plan=False,
            invoice_number="7002",
            series="1",
            issue_date=date(2026, 2, 10),
            entry_date=date(2026, 2, 10),
            total_amount=Decimal("120.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 3, 10),
                    amount=Decimal("120.00"),
                ),
            ],
        ),
        user,
    )
    db_session.commit()

    updated_plan = update_purchase_plan(
        db_session,
        company,
        plan.id,
        PurchasePlanUpdate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Fornecedor Atualizacao / Inverno 2026",
            order_date=date(2026, 2, 1),
            expected_delivery_date=date(2026, 2, 1),
            purchased_amount=Decimal("450.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )

    assert updated_plan.purchased_amount == Decimal("450.00")
    assert updated_plan.received_amount == Decimal("120.00")
    assert updated_plan.amount_to_receive == Decimal("330.00")


def test_update_purchase_plan_with_purchase_return_does_not_reduce_current_or_future_collection(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 3, 31))
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Devolucao")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 31),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Fornecedor Devolucao / Inverno 2026",
            order_date=date(2026, 2, 1),
            expected_delivery_date=date(2026, 2, 1),
            purchased_amount=Decimal("450.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=collection.id,
            purchase_plan_id=plan.id,
            create_plan=False,
            invoice_number="7003",
            series="1",
            issue_date=date(2026, 2, 10),
            entry_date=date(2026, 2, 10),
            total_amount=Decimal("120.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 3, 10),
                    amount=Decimal("120.00"),
                ),
            ],
        ),
        user,
    )
    create_purchase_return(
        db_session,
        company,
        PurchaseReturnCreate(
            supplier_id=supplier.id,
            return_date=date(2026, 2, 20),
            amount=Decimal("20.00"),
        ),
        user,
    )
    db_session.commit()

    updated_plan = update_purchase_plan(
        db_session,
        company,
        plan.id,
        PurchasePlanUpdate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Fornecedor Devolucao / Inverno 2026",
            order_date=date(2026, 2, 1),
            expected_delivery_date=date(2026, 2, 1),
            purchased_amount=Decimal("450.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )

    assert updated_plan.received_amount == Decimal("120.00")
    assert updated_plan.amount_to_receive == Decimal("330.00")


def test_update_purchase_plan_with_purchase_return_reduces_past_collection(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 8, 10))
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Devolucao Passada")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 31),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Fornecedor Devolucao Passada / Inverno 2026",
            order_date=date(2026, 2, 1),
            expected_delivery_date=date(2026, 2, 1),
            purchased_amount=Decimal("450.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=collection.id,
            purchase_plan_id=plan.id,
            create_plan=False,
            invoice_number="7004",
            series="1",
            issue_date=date(2026, 2, 10),
            entry_date=date(2026, 2, 10),
            total_amount=Decimal("120.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 3, 10),
                    amount=Decimal("120.00"),
                ),
            ],
        ),
        user,
    )
    create_purchase_return(
        db_session,
        company,
        PurchaseReturnCreate(
            supplier_id=supplier.id,
            return_date=date(2026, 2, 20),
            amount=Decimal("20.00"),
        ),
        user,
    )
    db_session.commit()

    updated_plan = update_purchase_plan(
        db_session,
        company,
        plan.id,
        PurchasePlanUpdate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Fornecedor Devolucao Passada / Inverno 2026",
            order_date=date(2026, 2, 1),
            expected_delivery_date=date(2026, 2, 1),
            purchased_amount=Decimal("450.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )

    assert updated_plan.received_amount == Decimal("120.00")
    assert updated_plan.amount_to_receive == Decimal("330.00")


def test_overview_cashflow_uses_purchase_entries_to_reduce_amount_to_receive(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Fluxo")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 5, 31),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Fluxo",
            order_date=date(2026, 3, 24),
            expected_delivery_date=date(2026, 4, 10),
            purchased_amount=Decimal("900.00"),
            payment_term="3x",
            status="planned",
        ),
        user,
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=collection.id,
            purchase_plan_id=plan.id,
            create_plan=False,
            invoice_number="7101",
            series="1",
            issue_date=date(2026, 3, 28),
            entry_date=date(2026, 3, 28),
            total_amount=Decimal("300.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 4, 28),
                    amount=Decimal("300.00"),
                ),
            ],
        ),
        user,
    )
    purchase_category = create_purchase_category(db_session, company)
    db_session.add(
        finance_models.FinancialEntry(
            company_id=company.id,
            category_id=purchase_category.id,
            supplier_id=supplier.id,
            collection_id=collection.id,
            entry_type="expense",
            status="planned",
            title="Lancamento avulso de compras",
            counterparty_name=supplier.name,
            issue_date=date(2026, 4, 2),
            competence_date=date(2026, 4, 2),
            due_date=date(2026, 4, 20),
            total_amount=Decimal("900.00"),
            paid_amount=Decimal("0.00"),
            is_deleted=False,
        )
    )
    db_session.commit()
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 3, 24))

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())
    plan_overview = next(item for item in overview.plans if item.id == plan.id)
    monthly_projection = {
        item.reference: (item.planned_outflows, item.open_balance)
        for item in overview.monthly_projection
    }

    assert plan_overview.received_amount == Decimal("1200.00")
    assert plan_overview.amount_to_receive == Decimal("0.00")
    assert overview.summary.outstanding_payable_total == Decimal("0.00")
    assert monthly_projection == {
        "2026-04": (Decimal("100.00"), Decimal("100.00")),
        "2026-05": (Decimal("200.00"), Decimal("200.00")),
        "2026-06": (Decimal("300.00"), Decimal("300.00")),
        "2026-07": (Decimal("200.00"), Decimal("200.00")),
        "2026-08": (Decimal("100.00"), Decimal("100.00")),
    }


def test_overview_cashflow_subtracts_brand_linked_purchase_entries_from_amount_to_receive(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 3, 24))
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Fluxo Entrada")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 5, 31),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Fluxo Entrada",
            order_date=date(2026, 3, 24),
            expected_delivery_date=date(2026, 4, 10),
            purchased_amount=Decimal("900.00"),
            payment_term="3x",
            status="planned",
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=910001,
        supplier_name=supplier.name,
        collection_name="Colecao Errada",
    )
    create_linx_purchase_movement(
        db_session,
        company,
        linx_transaction=910001,
        product_code=910001,
        document_number="9100",
        movement_type="purchase",
        total_amount=Decimal("320.00"),
        launch_date=date(2026, 3, 28),
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())
    plan_overview = next(item for item in overview.plans if item.id == plan.id)
    monthly_projection = {item.reference: item.planned_outflows for item in overview.monthly_projection}

    assert plan_overview.received_amount == Decimal("0.00")
    assert plan_overview.amount_to_receive == Decimal("900.00")
    assert sum(monthly_projection.values(), Decimal("0.00")) == Decimal("580.00")
    assert monthly_projection == {
        "2026-04": Decimal("64.44"),
        "2026-05": Decimal("128.88"),
        "2026-06": Decimal("193.34"),
        "2026-07": Decimal("128.90"),
        "2026-08": Decimal("64.44"),
    }


def test_overview_cashflow_ignores_purchase_returns_in_projected_flow(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 3, 24))
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Fluxo Devolucao")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 5, 31),
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Fluxo Devolucao",
            order_date=date(2026, 3, 24),
            expected_delivery_date=date(2026, 4, 10),
            purchased_amount=Decimal("900.00"),
            payment_term="3x",
            status="planned",
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=910101,
        supplier_name=supplier.name,
        collection_name="Colecao Errada",
    )
    create_linx_purchase_movement(
        db_session,
        company,
        linx_transaction=910101,
        product_code=910101,
        document_number="9101",
        movement_type="purchase",
        total_amount=Decimal("300.00"),
        launch_date=date(2026, 3, 28),
    )
    create_linx_purchase_movement(
        db_session,
        company,
        linx_transaction=910102,
        product_code=910101,
        document_number="9102",
        movement_type="purchase_return",
        total_amount=Decimal("120.00"),
        launch_date=date(2026, 4, 5),
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())
    monthly_projection = {item.reference: item.planned_outflows for item in overview.monthly_projection}

    assert sum(monthly_projection.values(), Decimal("0.00")) == Decimal("600.00")
    assert monthly_projection == {
        "2026-04": Decimal("66.67"),
        "2026-05": Decimal("133.34"),
        "2026-06": Decimal("200.00"),
        "2026-07": Decimal("133.33"),
        "2026-08": Decimal("66.66"),
    }


def test_overview_cashflow_ignores_past_collections(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 3, 24))
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Passado")
    past_collection = create_collection(
        db_session,
        company,
        "Verao 2025",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 31),
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=past_collection.id,
            title="Compra Passada",
            order_date=date(2025, 2, 10),
            expected_delivery_date=date(2025, 2, 20),
            purchased_amount=Decimal("900.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=past_collection.id,
            create_plan=False,
            invoice_number="7102",
            series="1",
            issue_date=date(2025, 2, 15),
            entry_date=date(2025, 2, 15),
            total_amount=Decimal("300.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2025, 3, 10),
                    amount=Decimal("300.00"),
                ),
            ],
        ),
        user,
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())

    assert overview.monthly_projection == []


def test_list_purchase_invoice_suppliers_returns_only_suppliers_with_purchase_invoices(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier_with_invoice = create_supplier(db_session, company.id, "Fornecedor Com Nota")
    supplier_without_invoice = create_supplier(db_session, company.id, "Fornecedor Sem Nota")
    collection = create_collection(db_session, company, "Inverno 2026")

    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier_with_invoice.id,
            supplier_name=supplier_with_invoice.name,
            collection_id=collection.id,
            create_plan=False,
            invoice_number="8001",
            series="1",
            issue_date=date(2026, 2, 10),
            entry_date=date(2026, 2, 11),
            total_amount=Decimal("150.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 3, 10),
                    amount=Decimal("150.00"),
                ),
            ],
        ),
        user,
    )
    db_session.commit()

    listed_suppliers = list_purchase_invoice_suppliers(db_session, company)

    db_session.refresh(supplier_with_invoice)
    db_session.refresh(supplier_without_invoice)

    assert [supplier.name for supplier in listed_suppliers] == ["Fornecedor Com Nota"]
    assert supplier_with_invoice.has_purchase_invoices is True
    assert supplier_without_invoice.has_purchase_invoices is False


def test_create_purchase_invoice_marks_new_supplier_with_purchase_invoice_flag(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    collection = create_collection(db_session, company, "Inverno 2026")

    invoice = create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_name="Fornecedor Novo Com Nota",
            collection_id=collection.id,
            create_plan=False,
            invoice_number="8002",
            series="1",
            issue_date=date(2026, 2, 12),
            entry_date=date(2026, 2, 13),
            total_amount=Decimal("250.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 3, 12),
                    amount=Decimal("250.00"),
                ),
            ],
        ),
        user,
    )
    db_session.commit()

    supplier = db_session.get(Supplier, invoice.supplier_id)

    assert supplier is not None
    assert supplier.has_purchase_invoices is True


def test_list_purchase_invoice_suppliers_includes_historical_purchase_entries(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier_from_history = create_supplier(db_session, company.id, "Fornecedor Historico Compras")
    create_supplier(db_session, company.id, "Fornecedor Fora Compras")
    purchase_category = create_purchase_category(db_session, company)

    create_entry(
        db_session,
        company,
        FinancialEntryCreate(
            category_id=purchase_category.id,
            supplier_id=supplier_from_history.id,
            entry_type="expense",
            status="planned",
            title="Historico compras",
            issue_date=date(2024, 5, 10),
            due_date=date(2024, 5, 20),
            principal_amount=Decimal("180.00"),
            total_amount=Decimal("180.00"),
        ),
        user,
    )
    db_session.commit()

    listed_suppliers = list_purchase_invoice_suppliers(db_session, company)
    db_session.refresh(supplier_from_history)

    assert [supplier.name for supplier in listed_suppliers] == ["Fornecedor Historico Compras"]
    assert supplier_from_history.has_purchase_invoices is True


def test_list_purchase_invoice_suppliers_excludes_ignored_suppliers(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Ignorado")
    collection = create_collection(db_session, company, "Inverno 2026")

    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=collection.id,
            create_plan=False,
            invoice_number="9001",
            series="1",
            issue_date=date(2026, 2, 10),
            entry_date=date(2026, 2, 11),
            total_amount=Decimal("150.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 3, 10),
                    amount=Decimal("150.00"),
                ),
            ],
        ),
        user,
    )
    db_session.flush()
    supplier.ignore_in_purchase_planning = True
    db_session.commit()

    listed_suppliers = list_purchase_invoice_suppliers(db_session, company)

    assert listed_suppliers == []


def test_planning_overview_keeps_supplier_ids_for_sem_marca_rows(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Sem Marca")
    purchase_category = create_purchase_category(db_session, company)

    create_entry(
        db_session,
        company,
        FinancialEntryCreate(
            category_id=purchase_category.id,
            supplier_id=supplier.id,
            entry_type="expense",
            status="planned",
            title="Compra sem marca",
            issue_date=date(2026, 7, 12),
            due_date=date(2026, 7, 30),
            principal_amount=Decimal("220.00"),
            total_amount=Decimal("220.00"),
        ),
        user,
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())
    sem_marca_row = next(row for row in overview.rows if row.brand_name == "Não classificados")

    assert sem_marca_row.supplier_ids == [supplier.id]
    assert sem_marca_row.supplier_names == ["Fornecedor Sem Marca"]


def test_planning_overview_ignores_non_purchase_entries_in_sem_marca(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    purchase_supplier = create_supplier(db_session, company.id, "Fornecedor Compra")
    generic_supplier = create_supplier(db_session, company.id, "Fornecedor Operacional")
    purchase_category = create_purchase_category(db_session, company)
    generic_category = create_generic_expense_category(db_session, company)

    create_entry(
        db_session,
        company,
        FinancialEntryCreate(
            category_id=purchase_category.id,
            supplier_id=purchase_supplier.id,
            entry_type="expense",
            status="planned",
            title="Compra sem marca",
            issue_date=date(2026, 7, 12),
            due_date=date(2026, 7, 30),
            principal_amount=Decimal("220.00"),
            total_amount=Decimal("220.00"),
        ),
        user,
    )
    create_entry(
        db_session,
        company,
        FinancialEntryCreate(
            category_id=generic_category.id,
            supplier_id=generic_supplier.id,
            entry_type="expense",
            status="planned",
            title="Despesa sem marca",
            issue_date=date(2026, 7, 13),
            due_date=date(2026, 7, 31),
            principal_amount=Decimal("180.00"),
            total_amount=Decimal("180.00"),
        ),
        user,
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())
    sem_marca_row = next(row for row in overview.rows if row.brand_name == "Não classificados")

    assert sem_marca_row.supplier_ids == [purchase_supplier.id]
    assert sem_marca_row.supplier_names == ["Fornecedor Compra"]


def test_create_purchase_invoice_generates_financial_entries_and_updates_plan_totals(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "1413 FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 7, 31),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="FORNECEDOR MODELO / Inverno 2026",
            order_date=date(2026, 3, 25),
            expected_delivery_date=date(2026, 3, 25),
            purchased_amount=Decimal("8849.00"),
            payment_term="4x",
            status="planned",
        ),
        user,
    )
    db_session.flush()

    invoice = create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=collection.id,
            purchase_plan_id=plan.id,
            create_plan=False,
            invoice_number="65843",
            series="1",
            issue_date=date(2026, 3, 25),
            entry_date=date(2026, 3, 25),
            total_amount=Decimal("8849.00"),
            payment_term="4x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="56628",
                    due_date=date(2026, 4, 24),
                    amount=Decimal("2212.00"),
                ),
                PurchaseInstallmentDraft(
                    installment_number=2,
                    installment_label="56629",
                    due_date=date(2026, 5, 24),
                    amount=Decimal("2212.00"),
                ),
                PurchaseInstallmentDraft(
                    installment_number=3,
                    installment_label="56630",
                    due_date=date(2026, 6, 23),
                    amount=Decimal("2212.00"),
                ),
                PurchaseInstallmentDraft(
                    installment_number=4,
                    installment_label="56631",
                    due_date=date(2026, 7, 23),
                    amount=Decimal("2213.00"),
                ),
            ],
        ),
        user,
    )
    db_session.commit()

    installments = (
        db_session.query(purchasing_models.PurchaseInstallment)
        .filter(purchasing_models.PurchaseInstallment.purchase_invoice_id == invoice.id)
        .order_by(purchasing_models.PurchaseInstallment.installment_number.asc())
        .all()
    )
    financial_entries = (
        db_session.query(finance_models.FinancialEntry)
        .filter(finance_models.FinancialEntry.purchase_invoice_id == invoice.id)
        .order_by(finance_models.FinancialEntry.due_date.asc())
        .all()
    )

    assert len(installments) == 4
    assert len(financial_entries) == 4
    assert sum((entry.total_amount for entry in financial_entries), Decimal("0.00")) == Decimal("8849.00")
    assert [entry.total_amount for entry in financial_entries] == [
        Decimal("2212.00"),
        Decimal("2212.00"),
        Decimal("2212.00"),
        Decimal("2213.00"),
    ]
    assert [entry.due_date for entry in financial_entries] == [
        date(2026, 4, 24),
        date(2026, 5, 24),
        date(2026, 6, 23),
        date(2026, 7, 23),
    ]
    assert all(entry.status == "open" for entry in financial_entries)
    assert all(entry.supplier_id == supplier.id for entry in financial_entries)
    assert all(entry.collection_id == collection.id for entry in financial_entries)
    assert all(entry.category_id for entry in financial_entries)
    assert all(entry.issue_date == date(2026, 3, 25) for entry in financial_entries)
    assert all(entry.purchase_installment_id for entry in financial_entries)
    assert sorted(entry.purchase_installment_id for entry in financial_entries) == sorted(
        installment.id for installment in installments
    )
    assert all(installment.financial_entry_id for installment in installments)
    purchase_category = db_session.get(finance_models.Category, financial_entries[0].category_id)
    assert purchase_category is not None
    assert purchase_category.name == "Compras"

    listed_plan = next(item for item in list_purchase_plans(db_session, company, limit=10) if item.id == plan.id)
    assert listed_plan.received_amount == Decimal("8849.00")
    assert listed_plan.amount_to_receive == Decimal("0.00")

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())
    overview_plan = next(item for item in overview.plans if item.id == plan.id)
    assert overview_plan.received_amount == Decimal("8849.00")
    assert overview.summary.launched_financial_total == Decimal("8849.00")
    assert len(overview.open_installments) == 4


def test_parse_purchase_invoice_text_uses_total_from_note_table_or_installments() -> None:
    raw_text = """
Contato Exemplo
Rua Exemplo,123 CIDADE MODELO SC
contato@example.invalid (48)99999-0000

Documento Interno
(Cópia de Nota Fiscal)

Destinatário/Remetente
1310 FORNECEDOR EXEMPLO LTDA

Dados Complementares
Nota Fiscal: 12345
Série: 0
Data de emissão: 09/03/2026- 09:40
Data de entrada/saída: 28/03/2026 - Hora: 09:40:00
Forma de Pagamento: 187 - 1 - 14DD AV - 150,00

Observações:
Número da Fatura    Vencimento    Valor
00001   23/03/26    150,00

Totalização da Nota
Base Cálc. ICMS  Valor do ICMS  Base ICMS-ST  Valor ICMS-ST  V. Total Produtos
0,00  0,00  0,00  0,00  160,00
Valor do Frete  Valor do Seguro  Outras Despesas  Valor Total do IPI  V.Total da Nota
0,00  0,00  0,00  0,00  150,00
"""

    draft = parse_purchase_invoice_text(raw_text)

    assert draft.invoice_number == "12345"
    assert draft.supplier_name == "FORNECEDOR EXEMPLO LTDA"
    assert draft.total_amount == Decimal("150.00")
    assert len(draft.installments) == 1
    assert draft.installments[0].installment_label == "00001"
    assert draft.installments[0].amount == Decimal("150.00")


def test_create_purchase_invoice_reuses_existing_supplier_and_plan_when_name_has_numeric_prefix(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 15),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="FORNECEDOR MODELO / Inverno 2026",
            order_date=date(2026, 3, 25),
            expected_delivery_date=date(2026, 3, 27),
            purchased_amount=Decimal("90988.00"),
            payment_term="3x",
            status="confirmed",
        ),
        user,
    )
    db_session.flush()

    invoice = create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_name="1413 FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA",
            collection_id=collection.id,
            invoice_number="65843",
            series="1",
            issue_date=date(2026, 3, 25),
            entry_date=date(2026, 3, 27),
            total_amount=Decimal("8849.00"),
            payment_term="4x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="56628",
                    due_date=date(2026, 4, 24),
                    amount=Decimal("2212.00"),
                )
            ],
        ),
        user,
    )
    db_session.commit()

    suppliers = db_session.query(purchasing_models.Supplier).all()
    plans = db_session.query(purchasing_models.PurchasePlan).all()

    assert len(suppliers) == 1
    assert len(plans) == 1
    assert invoice.supplier_id == supplier.id
    assert invoice.purchase_plan_id == plan.id


def test_create_supplier_normalizes_numeric_prefix_and_blocks_duplicate(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    canonical_supplier = create_supplier_service(
        db_session,
        company,
        SupplierCreate(
            name="1413 FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA",
            default_payment_term="1x",
            notes=None,
            is_active=True,
        ),
        user,
    )
    db_session.commit()

    assert canonical_supplier.name == "FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA"

    with pytest.raises(HTTPException) as exc_info:
        create_supplier_service(
            db_session,
            company,
            SupplierCreate(
                name="FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA",
                default_payment_term="1x",
                notes=None,
                is_active=True,
            ),
            user,
        )

    assert exc_info.value.status_code == 409
    assert "FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA" in str(exc_info.value.detail)


def test_update_supplier_normalizes_numeric_prefix_and_blocks_duplicate(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    canonical_supplier = create_supplier(db_session, company.id, "FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA")
    duplicate_supplier = create_supplier(db_session, company.id, "Fornecedor Temporario")
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        update_supplier_service(
            db_session,
            company,
            duplicate_supplier.id,
            SupplierUpdate(
                name="1413 FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA",
                default_payment_term="1x",
                notes=None,
                is_active=True,
            ),
            user,
        )

    assert exc_info.value.status_code == 409
    db_session.rollback()

    updated_supplier = update_supplier_service(
        db_session,
        company,
        canonical_supplier.id,
        SupplierUpdate(
            name="1413 FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA",
            default_payment_term="2x",
            notes="ajustado",
            is_active=True,
        ),
        user,
    )

    assert updated_supplier.name == "FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA"
    assert updated_supplier.default_payment_term == "2x"


def test_backfill_purchase_installment_entries_repairs_existing_invoice_without_financial_entries(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Reparado")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 7, 31),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra sem lancamentos",
            order_date=date(2026, 3, 25),
            expected_delivery_date=date(2026, 3, 25),
            purchased_amount=Decimal("1000.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )
    db_session.flush()

    invoice = purchasing_models.PurchaseInvoice(
        company_id=company.id,
        supplier_id=supplier.id,
        collection_id=collection.id,
        purchase_plan_id=plan.id,
        invoice_number="90001",
        issue_date=date(2026, 3, 25),
        entry_date=date(2026, 3, 25),
        total_amount=Decimal("1000.00"),
        payment_term="2x",
        source_type="text",
        status="open",
    )
    db_session.add(invoice)
    db_session.flush()
    db_session.add_all(
        [
            purchasing_models.PurchaseInstallment(
                company_id=company.id,
                purchase_invoice_id=invoice.id,
                installment_number=1,
                installment_label="1/2",
                due_date=date(2026, 4, 24),
                amount=Decimal("500.00"),
                status="planned",
            ),
            purchasing_models.PurchaseInstallment(
                company_id=company.id,
                purchase_invoice_id=invoice.id,
                installment_number=2,
                installment_label="2/2",
                due_date=date(2026, 5, 24),
                amount=Decimal("500.00"),
                status="planned",
            ),
        ]
    )
    db_session.commit()

    repaired_count = ensure_purchase_installment_financial_entries(db_session, company_id=company.id)
    db_session.commit()

    financial_entries = (
        db_session.query(finance_models.FinancialEntry)
        .filter(finance_models.FinancialEntry.purchase_invoice_id == invoice.id)
        .order_by(finance_models.FinancialEntry.due_date.asc())
        .all()
    )
    installments = (
        db_session.query(purchasing_models.PurchaseInstallment)
        .filter(purchasing_models.PurchaseInstallment.purchase_invoice_id == invoice.id)
        .order_by(purchasing_models.PurchaseInstallment.installment_number.asc())
        .all()
    )

    assert repaired_count == 2
    assert len(financial_entries) == 2
    assert [entry.total_amount for entry in financial_entries] == [Decimal("500.00"), Decimal("500.00")]
    assert all(entry.category_id for entry in financial_entries)
    assert sorted(entry.purchase_installment_id for entry in financial_entries) == sorted(
        installment.id for installment in installments
    )
    assert all(installment.financial_entry_id for installment in installments)
    purchase_category = db_session.get(finance_models.Category, financial_entries[0].category_id)
    assert purchase_category is not None
    assert purchase_category.name == "Compras"

    listed_plan = next(item for item in list_purchase_plans(db_session, company, limit=10) if item.id == plan.id)
    assert listed_plan.received_amount == Decimal("1000.00")
    assert listed_plan.amount_to_receive == Decimal("0.00")


def test_backfill_purchase_installment_entries_assigns_category_to_existing_purchase_entries(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Sem Categoria")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 7, 31),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra sem categoria",
            order_date=date(2026, 3, 25),
            expected_delivery_date=date(2026, 3, 25),
            purchased_amount=Decimal("500.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )
    db_session.flush()

    invoice = purchasing_models.PurchaseInvoice(
        company_id=company.id,
        supplier_id=supplier.id,
        collection_id=collection.id,
        purchase_plan_id=plan.id,
        invoice_number="90002",
        issue_date=date(2026, 3, 25),
        entry_date=date(2026, 3, 25),
        total_amount=Decimal("500.00"),
        payment_term="1x",
        source_type="text",
        status="open",
    )
    db_session.add(invoice)
    db_session.flush()
    installment = purchasing_models.PurchaseInstallment(
        company_id=company.id,
        purchase_invoice_id=invoice.id,
        installment_number=1,
        installment_label="1/1",
        due_date=date(2026, 4, 24),
        amount=Decimal("500.00"),
        status="planned",
    )
    db_session.add(installment)
    db_session.flush()
    entry = finance_models.FinancialEntry(
        company_id=company.id,
        supplier_id=supplier.id,
        collection_id=collection.id,
        purchase_invoice_id=invoice.id,
        purchase_installment_id=installment.id,
        entry_type="expense",
        status="planned",
        title="Fornecedor Sem Categoria - NF 90002 - Parcela 1/1",
        counterparty_name=supplier.name,
        issue_date=date(2026, 3, 25),
        competence_date=date(2026, 3, 25),
        due_date=date(2026, 4, 24),
        principal_amount=Decimal("500.00"),
        total_amount=Decimal("500.00"),
        paid_amount=Decimal("0.00"),
        source_system="purchase_invoice",
        is_deleted=False,
    )
    db_session.add(entry)
    db_session.commit()

    repaired_count = ensure_purchase_installment_financial_entries(db_session, company_id=company.id)
    db_session.commit()
    db_session.refresh(entry)

    assert repaired_count == 1
    assert entry.category_id is not None
    purchase_category = db_session.get(finance_models.Category, entry.category_id)
    assert purchase_category is not None
    assert purchase_category.name == "Compras"


def test_reconcile_purchase_invoice_links_moves_duplicate_supplier_invoice_to_existing_plan(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    canonical_supplier = create_supplier(db_session, company.id, "FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA")
    duplicate_supplier = create_supplier(db_session, company.id, "1413 FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 15),
    )
    canonical_plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[canonical_supplier.id],
            collection_id=collection.id,
            title="FORNECEDOR MODELO / Inverno 2026",
            order_date=date(2026, 3, 25),
            expected_delivery_date=date(2026, 3, 27),
            purchased_amount=Decimal("90988.00"),
            payment_term="3x",
            status="confirmed",
        ),
        user,
    )
    db_session.flush()
    imported_plan = purchasing_models.PurchasePlan(
        company_id=company.id,
        supplier_id=duplicate_supplier.id,
        collection_id=collection.id,
        title="1413 FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA - NF 12346",
        order_date=date(2026, 3, 25),
        expected_delivery_date=date(2026, 3, 27),
        purchased_amount=Decimal("8849.00"),
        payment_term="4x",
        status="imported",
    )
    db_session.add(imported_plan)
    db_session.flush()
    invoice = purchasing_models.PurchaseInvoice(
        company_id=company.id,
        supplier_id=duplicate_supplier.id,
        collection_id=collection.id,
        purchase_plan_id=imported_plan.id,
        invoice_number="65843",
        issue_date=date(2026, 3, 25),
        entry_date=date(2026, 3, 27),
        total_amount=Decimal("8849.00"),
        payment_term="4x",
        source_type="text",
        status="open",
    )
    db_session.add(invoice)
    db_session.flush()
    installment = purchasing_models.PurchaseInstallment(
        company_id=company.id,
        purchase_invoice_id=invoice.id,
        installment_number=1,
        installment_label="56628",
        due_date=date(2026, 4, 24),
        amount=Decimal("2212.00"),
        status="planned",
    )
    db_session.add(installment)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseDelivery(
            company_id=company.id,
            supplier_id=duplicate_supplier.id,
            collection_id=collection.id,
            purchase_plan_id=imported_plan.id,
            purchase_invoice_id=invoice.id,
            delivery_date=date(2026, 3, 27),
            amount=Decimal("8849.00"),
            source_type="text",
        )
    )
    entry = finance_models.FinancialEntry(
        company_id=company.id,
        supplier_id=duplicate_supplier.id,
        collection_id=collection.id,
        purchase_invoice_id=invoice.id,
        purchase_installment_id=installment.id,
        entry_type="expense",
        status="planned",
        title="1413 FORNECEDOR MODELO INDUSTRIA E COMERCIO LTDA - NF 12346 - Parcela 00002",
        counterparty_name=duplicate_supplier.name,
        document_number="65843",
        issue_date=date(2026, 3, 25),
        competence_date=date(2026, 3, 25),
        due_date=date(2026, 4, 24),
        principal_amount=Decimal("2212.00"),
        total_amount=Decimal("2212.00"),
        paid_amount=Decimal("0.00"),
        source_system="purchase_invoice",
        is_deleted=False,
    )
    db_session.add(entry)
    db_session.commit()

    repaired_count = reconcile_purchase_invoice_links(db_session, company_id=company.id)
    db_session.commit()
    db_session.refresh(invoice)
    db_session.refresh(entry)

    assert repaired_count >= 2
    assert invoice.supplier_id == canonical_supplier.id
    assert invoice.purchase_plan_id == canonical_plan.id
    assert entry.supplier_id == canonical_supplier.id
    assert db_session.get(purchasing_models.PurchasePlan, imported_plan.id) is None
    listed_plan = next(item for item in list_purchase_plans(db_session, company, limit=10) if item.id == canonical_plan.id)
    assert listed_plan.received_amount == Decimal("8849.00")


def test_backfill_purchase_installment_entries_replaces_wrong_purchase_category(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Categoria Errada")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 7, 31),
    )
    wrong_category = finance_models.Category(
        company_id=company.id,
        code="HX.4",
        name="Compra a Vista",
        entry_kind="expense",
        report_group="Compras Pagas",
        report_subgroup="Compras Pagas",
        is_active=True,
    )
    db_session.add(wrong_category)
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra categoria errada",
            order_date=date(2026, 3, 25),
            expected_delivery_date=date(2026, 3, 25),
            purchased_amount=Decimal("500.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )
    db_session.flush()

    invoice = purchasing_models.PurchaseInvoice(
        company_id=company.id,
        supplier_id=supplier.id,
        collection_id=collection.id,
        purchase_plan_id=plan.id,
        invoice_number="90003",
        issue_date=date(2026, 3, 25),
        entry_date=date(2026, 3, 25),
        total_amount=Decimal("500.00"),
        payment_term="1x",
        source_type="text",
        status="open",
    )
    db_session.add(invoice)
    db_session.flush()
    installment = purchasing_models.PurchaseInstallment(
        company_id=company.id,
        purchase_invoice_id=invoice.id,
        installment_number=1,
        installment_label="1/1",
        due_date=date(2026, 4, 24),
        amount=Decimal("500.00"),
        status="planned",
    )
    db_session.add(installment)
    db_session.flush()
    entry = finance_models.FinancialEntry(
        company_id=company.id,
        category_id=wrong_category.id,
        supplier_id=supplier.id,
        collection_id=collection.id,
        purchase_invoice_id=invoice.id,
        purchase_installment_id=installment.id,
        entry_type="expense",
        status="planned",
        title="Fornecedor Categoria Errada - NF 90003 - Parcela 1/1",
        counterparty_name=supplier.name,
        issue_date=date(2026, 3, 25),
        competence_date=date(2026, 3, 25),
        due_date=date(2026, 4, 24),
        principal_amount=Decimal("500.00"),
        total_amount=Decimal("500.00"),
        paid_amount=Decimal("0.00"),
        source_system="purchase_invoice",
        is_deleted=False,
    )
    db_session.add(entry)
    db_session.commit()

    repaired_count = ensure_purchase_installment_financial_entries(db_session, company_id=company.id)
    db_session.commit()
    db_session.refresh(entry)

    assert repaired_count == 2
    purchase_category = db_session.get(finance_models.Category, entry.category_id)
    assert purchase_category is not None
    assert purchase_category.name == "Compras"


def test_run_company_data_maintenance_keeps_only_compras_active_for_purchase_categories(db_session: Session) -> None:
    company, _user = create_company_context(db_session)
    legacy_cash_category = finance_models.Category(
        company_id=company.id,
        code="HX.4",
        name="Compra a Vista",
        entry_kind="expense",
        report_group="Compras Pagas",
        report_subgroup="Compras Historicas",
        is_active=True,
    )
    legacy_term_category = finance_models.Category(
        company_id=company.id,
        code="HX.3",
        name="Compra a Prazo Paga",
        entry_kind="expense",
        report_group="Compras Pagas",
        report_subgroup="Compras Historicas",
        is_active=True,
    )
    db_session.add_all([legacy_cash_category, legacy_term_category])
    db_session.commit()

    run_company_data_maintenance(db_session, company.id)
    db_session.commit()

    compras_category = db_session.query(finance_models.Category).filter(
        finance_models.Category.company_id == company.id,
        finance_models.Category.name == "Compras",
        finance_models.Category.entry_kind == "expense",
        finance_models.Category.is_active.is_(True),
    ).one()
    legacy_cash_category = db_session.get(finance_models.Category, legacy_cash_category.id)
    legacy_term_category = db_session.get(finance_models.Category, legacy_term_category.id)

    assert compras_category.code == "HX.3"
    assert compras_category.report_group == "Compras Pagas"
    assert legacy_cash_category is not None
    assert legacy_term_category is not None
    assert legacy_cash_category.is_active is False
    assert legacy_term_category.id == compras_category.id

    collections = list(
        db_session.query(purchasing_models.CollectionSeason)
        .filter(purchasing_models.CollectionSeason.company_id == company.id)
        .order_by(purchasing_models.CollectionSeason.season_year.asc(), purchasing_models.CollectionSeason.season_type.asc())
    )
    assert len(collections) >= 14
    winter_2020 = next(
        collection
        for collection in collections
        if collection.season_year == 2020 and collection.season_type == "winter"
    )
    summer_2020 = next(
        collection
        for collection in collections
        if collection.season_year == 2020 and collection.season_type == "summer"
    )
    assert winter_2020.start_date == date(2020, 1, 1)
    assert winter_2020.end_date == date(2020, 7, 1)
    assert summer_2020.start_date == date(2020, 7, 1)
    assert summer_2020.end_date == date(2020, 12, 31)


def test_run_company_data_maintenance_assigns_purchase_entries_to_historical_collections(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Historico")
    purchase_category = create_purchase_category(db_session, company)
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=None,
            title="Compra sem colecao",
            order_date=date(2021, 2, 10),
            expected_delivery_date=date(2021, 3, 10),
            purchased_amount=Decimal("500.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )
    invoice = create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=None,
            season_phase="main",
            invoice_number="123",
            series="1",
            issue_date=date(2021, 8, 10),
            entry_date=date(2021, 8, 12),
            total_amount=Decimal("200.00"),
            payment_description="1x",
            payment_term="1x",
            notes=None,
            raw_text="NF historica",
            raw_xml=None,
            installments=[],
            create_plan=False,
        ),
        user,
        source_type="text",
    )
    entry = finance_models.FinancialEntry(
        company_id=company.id,
        category_id=purchase_category.id,
        supplier_id=supplier.id,
        collection_id=None,
        entry_type="expense",
        status="planned",
        title="Compra historica avulsa",
        counterparty_name=supplier.name,
        competence_date=date(2021, 6, 15),
        total_amount=Decimal("120.00"),
        paid_amount=Decimal("0.00"),
        is_deleted=False,
    )
    db_session.add(entry)
    db_session.commit()

    run_company_data_maintenance(db_session, company.id)
    db_session.commit()

    db_session.refresh(entry)
    refreshed_plan = db_session.get(purchasing_models.PurchasePlan, plan.id)
    refreshed_invoice = db_session.get(purchasing_models.PurchaseInvoice, invoice.id)
    assert refreshed_plan is not None
    assert refreshed_invoice is not None
    assert refreshed_plan.collection is not None
    assert refreshed_plan.collection.name == "Inverno 2021"
    assert refreshed_invoice.collection is not None
    assert refreshed_invoice.collection.name == "Verao 2021"
    assert entry.collection is not None
    assert entry.collection.name == "Inverno 2021"


def test_list_purchase_plans_ignores_ungrouped_names_without_registered_supplier(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Casado")
    collection = create_collection(db_session, company, "Verao 2026")
    purchase_category = create_purchase_category(db_session, company)
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Verao",
            order_date=date(2026, 7, 5),
            expected_delivery_date=date(2026, 7, 10),
            purchased_amount=Decimal("500.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )
    db_session.flush()
    db_session.add(
        finance_models.FinancialEntry(
            company_id=company.id,
            category_id=purchase_category.id,
            supplier_id=None,
            collection_id=None,
            entry_type="expense",
            status="planned",
            title="Compra fornecedor avulso",
            counterparty_name="Fornecedor Fora Grupo",
            due_date=date(2026, 7, 20),
            total_amount=Decimal("210.00"),
            paid_amount=Decimal("0.00"),
            is_deleted=False,
        )
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())

    assert overview.ungrouped_suppliers == []


def test_list_purchase_plans_reports_only_registered_ungrouped_suppliers(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Casado")
    registered_ungrouped = create_supplier(db_session, company.id, "Fornecedor Fora Grupo")
    collection = create_collection(db_session, company, "Verao 2026")
    purchase_category = create_purchase_category(db_session, company)
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Verao",
            order_date=date(2026, 7, 5),
            expected_delivery_date=date(2026, 7, 10),
            purchased_amount=Decimal("500.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )
    db_session.flush()
    db_session.add(
        finance_models.FinancialEntry(
            company_id=company.id,
            category_id=purchase_category.id,
            supplier_id=registered_ungrouped.id,
            collection_id=None,
            entry_type="expense",
            status="planned",
            title="Compra fornecedor avulso",
            counterparty_name="Fornecedor Fora Grupo",
            due_date=date(2026, 7, 20),
            total_amount=Decimal("210.00"),
            paid_amount=Decimal("0.00"),
            is_deleted=False,
        )
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())

    assert len(overview.ungrouped_suppliers) == 1
    assert overview.ungrouped_suppliers[0].supplier_label == "Fornecedor Fora Grupo"
    assert overview.ungrouped_suppliers[0].collection_name == "Verao 2026"
    assert overview.ungrouped_suppliers[0].entry_count == 1
    assert overview.ungrouped_suppliers[0].total_amount == Decimal("210.00")


def test_ungrouped_suppliers_use_issue_date_for_collection_period(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Casado")
    registered_ungrouped = create_supplier(db_session, company.id, "NEWCO CONFECCOES LTDA")
    collection = create_collection(db_session, company, "Inverno 2026")
    purchase_category = create_purchase_category(db_session, company)
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Inverno",
            order_date=date(2026, 7, 5),
            expected_delivery_date=date(2026, 7, 10),
            purchased_amount=Decimal("500.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )
    db_session.flush()
    db_session.add(
        finance_models.FinancialEntry(
            company_id=company.id,
            category_id=purchase_category.id,
            supplier_id=registered_ungrouped.id,
            collection_id=None,
            entry_type="expense",
            status="planned",
            title="Compra fora por emissao",
            counterparty_name="NEWCO CONFECCOES LTDA",
            issue_date=date(2026, 8, 1),
            due_date=date(2026, 7, 10),
            total_amount=Decimal("100.00"),
            paid_amount=Decimal("0.00"),
            is_deleted=False,
        )
    )
    db_session.add(
        finance_models.FinancialEntry(
            company_id=company.id,
            category_id=purchase_category.id,
            supplier_id=registered_ungrouped.id,
            collection_id=None,
            entry_type="expense",
            status="planned",
            title="Compra dentro por emissao",
            counterparty_name="NEWCO CONFECCOES LTDA",
            issue_date=date(2026, 7, 20),
            due_date=date(2026, 8, 10),
            total_amount=Decimal("210.00"),
            paid_amount=Decimal("0.00"),
            is_deleted=False,
        )
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())

    assert len(overview.ungrouped_suppliers) == 1
    assert overview.ungrouped_suppliers[0].supplier_label == "NEWCO CONFECCOES LTDA"
    assert overview.ungrouped_suppliers[0].entry_count == 1
    assert overview.ungrouped_suppliers[0].total_amount == Decimal("210.00")


def test_ungrouped_suppliers_ignore_registered_supplier_without_purchase_entry(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Casado")
    registered_ungrouped = create_supplier(db_session, company.id, "Fornecedor Operacional")
    collection = create_collection(db_session, company, "Verao 2026")
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Verao",
            order_date=date(2026, 7, 5),
            expected_delivery_date=date(2026, 7, 10),
            purchased_amount=Decimal("500.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )
    db_session.flush()
    db_session.add(
        finance_models.FinancialEntry(
            company_id=company.id,
            supplier_id=registered_ungrouped.id,
            collection_id=None,
            entry_type="expense",
            status="planned",
            title="Servico fornecedor operacional",
            counterparty_name="Fornecedor Operacional",
            issue_date=date(2026, 7, 20),
            total_amount=Decimal("210.00"),
            paid_amount=Decimal("0.00"),
            is_deleted=False,
        )
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())

    assert overview.ungrouped_suppliers == []


def test_ungrouped_suppliers_exclude_supplier_already_linked_to_brand(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Casado")
    brand_linked_supplier = create_supplier(db_session, company.id, "Fornecedor Sem Plano")
    collection = create_collection(db_session, company, "Inverno 2026")
    purchase_category = create_purchase_category(db_session, company)
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Inverno",
            order_date=date(2026, 7, 5),
            expected_delivery_date=date(2026, 7, 10),
            purchased_amount=Decimal("500.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )
    db_session.flush()
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="Marca Teste",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=brand_linked_supplier.id,
        )
    )
    db_session.add(
        finance_models.FinancialEntry(
            company_id=company.id,
            category_id=purchase_category.id,
            supplier_id=brand_linked_supplier.id,
            collection_id=None,
            entry_type="expense",
            status="planned",
            title="Compra fornecedor ja vinculado",
            counterparty_name="Fornecedor Sem Plano",
            issue_date=date(2026, 7, 20),
            total_amount=Decimal("210.00"),
            paid_amount=Decimal("0.00"),
            is_deleted=False,
        )
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())

    assert overview.ungrouped_suppliers == []


def test_overview_projects_amount_to_receive_by_remaining_months_and_payment_term(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Projecao")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 5, 31),
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Compra Projetada",
            order_date=date(2026, 3, 24),
            expected_delivery_date=date(2026, 4, 10),
            purchased_amount=Decimal("3000.00"),
            payment_term="3x",
            status="planned",
        ),
        user,
    )
    db_session.commit()
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 3, 24))

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())
    monthly_projection = {item.reference: item.planned_outflows for item in overview.monthly_projection}

    assert overview.summary.outstanding_payable_total == Decimal("3000.00")
    assert monthly_projection == {
        "2026-04": Decimal("333.33"),
        "2026-05": Decimal("666.66"),
        "2026-06": Decimal("1000.00"),
        "2026-07": Decimal("666.67"),
        "2026-08": Decimal("333.34"),
    }


def test_overview_cashflow_ignores_imported_and_duplicate_unbranded_plans(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user = create_company_context(db_session)
    linked_supplier = create_supplier(db_session, company.id, "Fornecedor Marca")
    imported_supplier = create_supplier(db_session, company.id, "Fornecedor Importado")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 7, 31),
    )
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="Marca Fluxo",
        default_payment_term="1x",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=linked_supplier.id,
        )
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            brand_id=brand.id,
            supplier_ids=[linked_supplier.id],
            collection_id=collection.id,
            title="Plano da marca",
            order_date=date(2026, 3, 24),
            expected_delivery_date=date(2026, 4, 10),
            purchased_amount=Decimal("1000.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[linked_supplier.id],
            collection_id=collection.id,
            title="Plano legado sem marca",
            order_date=date(2026, 3, 24),
            expected_delivery_date=date(2026, 4, 10),
            purchased_amount=Decimal("400.00"),
            payment_term="1x",
            status="planned",
        ),
        user,
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[imported_supplier.id],
            collection_id=collection.id,
            title="Plano importado",
            order_date=date(2026, 3, 24),
            expected_delivery_date=date(2026, 4, 10),
            purchased_amount=Decimal("300.00"),
            payment_term="1x",
            status="imported",
        ),
        user,
    )
    db_session.commit()
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 3, 24))

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters())

    assert sum((item.planned_outflows for item in overview.monthly_projection), Decimal("0.00")) == Decimal("1000.00")


def test_plan_season_metrics_use_previous_year_same_season_as_reference(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Historico")
    previous_collection = create_collection(
        db_session,
        company,
        "Verao 2025",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 31),
    )
    current_collection = create_collection(
        db_session,
        company,
        "Verao 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    other_collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 8, 31),
    )

    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=previous_collection.id,
            season_phase="main",
            title="Base Verao 2025",
            order_date=date(2025, 1, 10),
            expected_delivery_date=date(2025, 2, 10),
            purchased_amount=Decimal("1000.00"),
            payment_term="2x",
            status="confirmed",
        ),
        user,
    )
    current_plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=current_collection.id,
            season_phase="high",
            title="Compra Verao 2026",
            order_date=date(2026, 1, 12),
            expected_delivery_date=date(2026, 2, 12),
            purchased_amount=Decimal("400.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=other_collection.id,
            season_phase="main",
            title="Compra Inverno 2026",
            order_date=date(2026, 6, 10),
            expected_delivery_date=date(2026, 7, 10),
            purchased_amount=Decimal("250.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )

    plans = list_purchase_plans(db_session, company, limit=20)
    listed_plan = next(plan for plan in plans if plan.id == current_plan.id)

    assert listed_plan.collection_name == "Verao 2026"
    assert listed_plan.season_phase == "high"
    assert listed_plan.prior_year_same_season_amount == Decimal("1000.00")
    assert listed_plan.current_year_same_season_amount == Decimal("400.00")
    assert listed_plan.current_year_other_seasons_amount == Decimal("250.00")
    assert listed_plan.suggested_remaining_amount == Decimal("600.00")


def test_build_purchase_planning_overview_planning_mode_omits_summary_heavy_sections(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Planejamento")
    collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 1),
    )
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=collection.id,
            title="Marca Planejamento",
            order_date=date(2026, 2, 10),
            expected_delivery_date=date(2026, 3, 10),
            purchased_amount=Decimal("900.00"),
            payment_term="3x",
            status="planned",
        ),
        user,
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=collection.id,
            purchase_plan_id=plan.id,
            create_plan=False,
            invoice_number="9001",
            series="1",
            issue_date=date(2026, 2, 11),
            entry_date=date(2026, 2, 12),
            total_amount=Decimal("450.00"),
            payment_term="2x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/2",
                    due_date=date(2026, 3, 10),
                    amount=Decimal("225.00"),
                ),
                PurchaseInstallmentDraft(
                    installment_number=2,
                    installment_label="2/2",
                    due_date=date(2026, 4, 10),
                    amount=Decimal("225.00"),
                ),
            ],
        ),
        user,
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters(), mode="planning")

    assert len(overview.plans) == 1
    assert overview.invoices == []
    assert overview.open_installments == []
    assert overview.monthly_projection
    assert sum((item.planned_outflows for item in overview.monthly_projection), Decimal("0.00")) == Decimal("900.00")
    assert overview.rows[0].received_total == Decimal("450.00")


def test_purchase_planning_collection_filter_uses_collection_year_even_when_request_year_conflicts(
    db_session: Session,
) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Inverno 2025")
    historical_collection = create_collection(
        db_session,
        company,
        "Inverno 2025",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 7, 1),
    )
    create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=historical_collection.id,
            title="Compra Inverno 2025",
            order_date=date(2025, 3, 10),
            expected_delivery_date=date(2025, 4, 20),
            purchased_amount=Decimal("1500.00"),
            payment_term="3x",
            status="planned",
        ),
        user,
    )
    db_session.commit()

    conflicting_filters = PurchasePlanningFilters(year=2026, collection_id=historical_collection.id)

    overview = build_purchase_planning_overview(db_session, company, conflicting_filters)
    assert len(overview.rows) == 1
    assert overview.rows[0].collection_name == "Inverno 2025"
    assert overview.summary.purchased_total == Decimal("1500.00")


def test_ensure_company_catalog_does_not_run_historical_backfill_automatically(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Sem Backfill")
    plan = create_purchase_plan(
        db_session,
        company,
        PurchasePlanCreate(
            supplier_ids=[supplier.id],
            collection_id=None,
            title="Compra sem colecao",
            order_date=date(2026, 3, 10),
            expected_delivery_date=date(2026, 3, 20),
            purchased_amount=Decimal("750.00"),
            payment_term="2x",
            status="planned",
        ),
        user,
    )
    db_session.commit()

    ensure_company_catalog(db_session, company.id)
    db_session.commit()

    refreshed_plan = db_session.get(purchasing_models.PurchasePlan, plan.id)
    collections = list(
        db_session.query(purchasing_models.CollectionSeason).filter(
            purchasing_models.CollectionSeason.company_id == company.id
        )
    )

    assert refreshed_plan is not None
    assert refreshed_plan.collection_id is None
    assert collections == []


def test_overview_uses_invoice_issue_date_to_match_brand_collection_received_total(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Marca")
    winter_collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 1),
    )
    summer_collection = create_collection(
        db_session,
        company,
        "Verao 2026",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
    )
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="Marca Exemplo",
        default_payment_term="1x",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=supplier.id,
        )
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=summer_collection.id,
            create_plan=False,
            invoice_number="7001",
            series="1",
            issue_date=date(2026, 3, 15),
            entry_date=date(2026, 3, 16),
            total_amount=Decimal("500.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 4, 10),
                    amount=Decimal("500.00"),
                ),
            ],
        ),
        user,
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters(), mode="planning")

    row_by_collection = {row.collection_name: row for row in overview.rows if row.brand_name == "Marca Exemplo"}
    assert row_by_collection["Inverno 2026"].received_total == Decimal("500.00")
    assert "Verao 2026" not in row_by_collection


def test_overview_received_total_uses_supplier_entries_issue_date_within_collection_period(db_session: Session) -> None:
    company, _user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Fatura")
    winter_collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 1),
    )
    create_collection(
        db_session,
        company,
        "Verao 2026",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
    )
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="Marca Fatura",
        default_payment_term="1x",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=supplier.id,
        )
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=None,
            create_plan=False,
            invoice_number="7301",
            series="1",
            issue_date=date(2026, 3, 10),
            entry_date=date(2026, 3, 10),
            total_amount=Decimal("320.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 4, 10),
                    amount=Decimal("320.00"),
                ),
            ],
        ),
        _user,
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters(), mode="planning")

    row_by_collection = {row.collection_name: row for row in overview.rows if row.brand_name == "Marca Fatura"}
    assert row_by_collection["Inverno 2026"].received_total == Decimal("320.00")
    assert "Verao 2026" not in row_by_collection


def test_overview_assigns_sales_to_collection_by_movement_date_instead_of_linx_collection(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Venda")
    create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
    )
    create_collection(
        db_session,
        company,
        "Verao 2026",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
    )
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="Marca Venda",
        default_payment_term="1x",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=supplier.id,
        )
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=None,
            create_plan=False,
            invoice_number="7401",
            series="1",
            issue_date=date(2026, 3, 10),
            entry_date=date(2026, 3, 10),
            total_amount=Decimal("320.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 4, 10),
                    amount=Decimal("320.00"),
                ),
            ],
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=7401001,
        supplier_name=supplier.name,
        collection_name="Verao 2026",
        brand_name="Marca Venda",
    )
    create_linx_sale_movement(
        db_session,
        company,
        linx_transaction=7401001,
        product_code=7401001,
        document_number="7401",
        launch_date=date(2026, 3, 20),
        net_amount=Decimal("500.00"),
        quantity=Decimal("1.00"),
        cost_price=Decimal("200.00"),
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters(), mode="planning")

    row_by_collection = {row.collection_name: row for row in overview.rows if row.brand_name == "Marca Venda"}
    assert row_by_collection["Inverno 2026"].sold_total == Decimal("500.00")
    assert row_by_collection["Inverno 2026"].profit_margin == Decimal("56.25")
    assert "Verao 2026" not in row_by_collection


def test_overview_assigns_sales_to_brand_by_supplier_link_when_linx_brand_differs(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Sao Paulo")
    create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
    )
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="São Paulo",
        default_payment_term="1x",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=supplier.id,
        )
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=None,
            create_plan=False,
            invoice_number="7501",
            series="1",
            issue_date=date(2026, 3, 10),
            entry_date=date(2026, 3, 10),
            total_amount=Decimal("300.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 4, 10),
                    amount=Decimal("300.00"),
                ),
            ],
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=7501001,
        supplier_name="123 FORNECEDOR SAO PAULO",
        collection_name="Outra Colecao",
        brand_name="Marca Errada",
    )
    create_linx_sale_movement(
        db_session,
        company,
        linx_transaction=7501001,
        product_code=7501001,
        document_number="7501",
        launch_date=date(2026, 3, 20),
        net_amount=Decimal("510.00"),
        quantity=Decimal("1.00"),
        cost_price=Decimal("200.00"),
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters(), mode="planning")

    row_by_collection = {row.collection_name: row for row in overview.rows if row.brand_name == "São Paulo"}
    assert row_by_collection["Inverno 2026"].sold_total == Decimal("510.00")
    assert row_by_collection["Inverno 2026"].profit_margin == Decimal("70.00")


def test_overview_ignores_linx_brand_name_when_supplier_is_not_linked_to_brand(db_session: Session) -> None:
    company, user = create_company_context(db_session)
    linked_supplier = create_supplier(db_session, company.id, "Fornecedor Marca")
    unrelated_supplier = create_supplier(db_session, company.id, "Fornecedor Solto")
    create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
    )
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="Marca Fornecedor",
        default_payment_term="1x",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=linked_supplier.id,
        )
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=linked_supplier.id,
            supplier_name=linked_supplier.name,
            collection_id=None,
            create_plan=False,
            invoice_number="7601",
            series="1",
            issue_date=date(2026, 3, 10),
            entry_date=date(2026, 3, 10),
            total_amount=Decimal("300.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 4, 10),
                    amount=Decimal("300.00"),
                ),
            ],
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=7601001,
        supplier_name=unrelated_supplier.name,
        collection_name="Outra Colecao",
        brand_name="Marca Fornecedor",
    )
    create_linx_sale_movement(
        db_session,
        company,
        linx_transaction=7601001,
        product_code=7601001,
        document_number="7601",
        launch_date=date(2026, 3, 20),
        net_amount=Decimal("450.00"),
        quantity=Decimal("1.00"),
        cost_price=Decimal("150.00"),
    )
    db_session.commit()

    overview = build_purchase_planning_overview(
        db_session,
        company,
        PurchasePlanningFilters(),
        mode="planning",
    )

    row_by_collection = {
        row.collection_name: row
        for row in overview.rows
        if row.brand_name == "Marca Fornecedor"
    }
    assert row_by_collection["Inverno 2026"].sold_total == Decimal("0.00")


def test_overview_assigns_purchase_returns_to_current_collection_without_changing_received_total(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 3, 31))
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Retorno")
    winter_collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 1),
    )
    create_collection(
        db_session,
        company,
        "Verao 2026",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
    )
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="Marca Retorno",
        default_payment_term="1x",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=supplier.id,
        )
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=None,
            create_plan=False,
            invoice_number="7302",
            series="1",
            issue_date=date(2026, 3, 10),
            entry_date=date(2026, 3, 10),
            total_amount=Decimal("320.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 4, 10),
                    amount=Decimal("320.00"),
                ),
            ],
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=7302001,
        supplier_name=supplier.name,
        collection_name="Verao 2026",
    )
    create_linx_purchase_movement(
        db_session,
        company,
        linx_transaction=7302001,
        product_code=7302001,
        document_number="7302",
        movement_type="purchase_return",
        total_amount=Decimal("120.00"),
        launch_date=date(2026, 3, 20),
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters(), mode="planning")

    row_by_collection = {row.collection_name: row for row in overview.rows if row.brand_name == "Marca Retorno"}
    assert row_by_collection["Inverno 2026"].received_total == Decimal("320.00")
    assert row_by_collection["Inverno 2026"].returns_total == Decimal("120.00")
    assert overview.cost_totals[0].supplier_name == supplier.name
    assert overview.cost_totals[0].collection_name == "Inverno 2026"
    assert "Verao 2026" not in row_by_collection


def test_overview_assigns_purchase_returns_to_past_collection_without_changing_received_total(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 8, 10))
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor Retorno Passado")
    winter_collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 1),
    )
    create_collection(
        db_session,
        company,
        "Verao 2026",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
    )
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="Marca Retorno Passado",
        default_payment_term="1x",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=supplier.id,
        )
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=None,
            create_plan=False,
            invoice_number="7303",
            series="1",
            issue_date=date(2026, 3, 10),
            entry_date=date(2026, 3, 10),
            total_amount=Decimal("320.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 4, 10),
                    amount=Decimal("320.00"),
                ),
            ],
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=7303001,
        supplier_name=supplier.name,
        collection_name="Verao 2026",
    )
    create_linx_purchase_movement(
        db_session,
        company,
        linx_transaction=7303001,
        product_code=7303001,
        document_number="7303",
        movement_type="purchase_return",
        total_amount=Decimal("120.00"),
        launch_date=date(2026, 3, 20),
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters(), mode="planning")

    row_by_collection = {row.collection_name: row for row in overview.rows if row.brand_name == "Marca Retorno Passado"}
    assert row_by_collection["Inverno 2026"].received_total == Decimal("320.00")
    assert row_by_collection["Inverno 2026"].returns_total == Decimal("120.00")
    assert any(
        cost_total.collection_name == "Inverno 2026"
        and cost_total.supplier_name == supplier.name
        and cost_total.purchase_return_cost_total == Decimal("120.00")
        for cost_total in overview.cost_totals
    )
    assert "Verao 2026" not in row_by_collection


def test_overview_keeps_purchase_return_visible_for_inactive_brand_in_past_collection(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(purchase_planning_service, "_today", lambda: date(2026, 8, 10))
    company, user = create_company_context(db_session)
    supplier = create_supplier(db_session, company.id, "Fornecedor LP")
    winter_collection = create_collection(
        db_session,
        company,
        "Inverno 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 1),
    )
    brand = purchasing_models.PurchaseBrand(
        company_id=company.id,
        name="LP",
        default_payment_term="1x",
        is_active=False,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.add(
        purchasing_models.PurchaseBrandSupplier(
            company_id=company.id,
            brand_id=brand.id,
            supplier_id=supplier.id,
        )
    )
    create_purchase_invoice(
        db_session,
        company,
        PurchaseInvoiceCreate(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            collection_id=None,
            create_plan=False,
            invoice_number="7304",
            series="1",
            issue_date=date(2026, 3, 10),
            entry_date=date(2026, 3, 10),
            total_amount=Decimal("320.00"),
            payment_term="1x",
            installments=[
                PurchaseInstallmentDraft(
                    installment_number=1,
                    installment_label="1/1",
                    due_date=date(2026, 4, 10),
                    amount=Decimal("320.00"),
                ),
            ],
        ),
        user,
    )
    create_linx_product(
        db_session,
        company,
        linx_code=7304001,
        supplier_name=supplier.name,
        collection_name="Verao 2026",
    )
    create_linx_purchase_movement(
        db_session,
        company,
        linx_transaction=7304001,
        product_code=7304001,
        document_number="7304",
        movement_type="purchase_return",
        total_amount=Decimal("120.00"),
        launch_date=date(2026, 3, 20),
    )
    db_session.commit()

    overview = build_purchase_planning_overview(db_session, company, PurchasePlanningFilters(), mode="planning")

    row_by_collection = {row.collection_name: row for row in overview.rows if row.brand_name == "LP"}
    assert row_by_collection["Inverno 2026"].received_total == Decimal("320.00")
    assert row_by_collection["Inverno 2026"].returns_total == Decimal("120.00")
