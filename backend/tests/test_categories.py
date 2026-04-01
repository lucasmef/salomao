from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.categories import create_category
from app.db.base import Base
from app.db.models.security import Company, User
from app.schemas.category import CategoryCreate


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_create_category_allows_mixed_entry_kinds_in_same_group() -> None:
    session = _build_session()
    try:
        company = Company(
            legal_name="Empresa Teste Ltda",
            trade_name="Empresa Teste",
            default_currency="BRL",
        )
        user = User(
            company=company,
            full_name="Admin Teste",
            email="admin-categorias@example.com",
            password_hash="hash",
            role="admin",
        )
        session.add_all([company, user])
        session.commit()

        expense_category = create_category(
            CategoryCreate(
                name="Compras",
                entry_kind="expense",
                report_group="Movimento Comercial",
                report_subgroup="Compras",
            ),
            db=session,
            current_user=user,
        )
        income_category = create_category(
            CategoryCreate(
                name="Devolucao de compras",
                entry_kind="income",
                report_group="Movimento Comercial",
                report_subgroup="Devolucoes",
            ),
            db=session,
            current_user=user,
        )

        assert expense_category.report_group == "Movimento Comercial"
        assert income_category.report_group == "Movimento Comercial"
        assert expense_category.entry_kind == "expense"
        assert income_category.entry_kind == "income"
    finally:
        session.close()
