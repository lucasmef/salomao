from __future__ import annotations

import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi import HTTPException

from app.db.base import Base
from app.db.models.banking import BankTransaction
from app.db.models.finance import Account, Category, FinancialEntry
from app.db.models.linx import LinxMovement, SalesSnapshot
from app.db.models.purchasing import CollectionSeason, PurchasePlan, Supplier
from app.db.models.security import Company, User
from app.schemas.reconciliation import BankTransactionActionCreate, ReconciliationCreate
from app.schemas.transfer import TransferCreate
from app.services.bootstrap import ensure_company_catalog
from app.services.cashflow import build_cashflow_overview
from app.services.finance_ops import create_transfer, settle_entry
from app.services.import_parsers import ParsedSalesRow
from app.services.imports import import_linx_sales
from app.services.reconciliation import create_entry_from_bank_transaction, create_reconciliation
from app.services.reports import build_reports_overview
from app.schemas.financial_entry import EntrySettlementRequest
from app.services.category_catalog import ensure_category_catalog


class FinancialCalculationsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp_db = NamedTemporaryFile(
            prefix="financial_calculations_",
            suffix=".db",
            delete=False,
            dir=Path.cwd(),
        )
        temp_db.close()
        self.db_path = Path(temp_db.name)
        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self.db: Session = self.SessionLocal()

        self.company = Company(
            legal_name="Empresa Teste Ltda",
            trade_name="Empresa Teste",
            document="12345678000199",
        )
        self.user = User(
            company=self.company,
            full_name="Teste",
            email=f"teste-{self.db_path.stem}@example.com",
            password_hash="hash",
            role="admin",
        )
        self.db.add_all([self.company, self.user])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()
        if self.db_path.exists():
            os.remove(self.db_path)

    def _add_account(
        self,
        name: str,
        opening_balance: str,
        *,
        account_type: str = "checking",
    ) -> Account:
        account = Account(
            company_id=self.company.id,
            name=name,
            account_type=account_type,
            opening_balance=Decimal(opening_balance),
            is_active=True,
        )
        self.db.add(account)
        self.db.commit()
        return account

    def _add_category(
        self,
        *,
        name: str = "Despesa Teste",
        code: str = "4.1.2.1",
        entry_kind: str = "expense",
        report_group: str = "Despesas Operacionais",
        report_subgroup: str = "Despesas Gerais",
    ) -> Category:
        category = Category(
            company_id=self.company.id,
            code=code,
            name=name,
            entry_kind=entry_kind,
            report_group=report_group,
            report_subgroup=report_subgroup,
            is_active=True,
        )
        self.db.add(category)
        self.db.commit()
        return category

    def _add_entry(
        self,
        *,
        account: Account | None,
        entry_type: str,
        status: str,
        total_amount: str,
        paid_amount: str = "0.00",
        due_date: date | None = None,
        title: str | None = None,
        category: Category | None = None,
        source_system: str = "manual",
    ) -> FinancialEntry:
        entry_date = due_date or date(2026, 3, 23)
        total = Decimal(total_amount)
        paid = Decimal(paid_amount)
        entry = FinancialEntry(
            company_id=self.company.id,
            account_id=account.id if account else None,
            category_id=category.id if category else None,
            entry_type=entry_type,
            status=status,
            title=title or f"{entry_type}-{status}",
            issue_date=entry_date,
            competence_date=entry_date,
            due_date=entry_date,
            settled_at=None,
            principal_amount=total,
            total_amount=total,
            paid_amount=paid,
            source_system=source_system,
            is_deleted=False,
        )
        self.db.add(entry)
        self.db.commit()
        return entry

    def _add_bank_transaction(
        self,
        *,
        account: Account,
        posted_at: date,
        amount: str,
        fit_id: str,
    ) -> BankTransaction:
        transaction = BankTransaction(
            company_id=self.company.id,
            account_id=account.id,
            bank_name="Banco Teste",
            bank_code="001",
            posted_at=posted_at,
            trn_type="credit",
            amount=Decimal(amount),
            fit_id=fit_id,
            memo="Importado OFX",
        )
        self.db.add(transaction)
        self.db.commit()
        return transaction

    def _add_sales_snapshot(
        self,
        *,
        snapshot_date: date,
        gross_revenue: str,
        markup: str = "100.00",
        discount_or_surcharge: str = "0.00",
    ) -> SalesSnapshot:
        snapshot = SalesSnapshot(
            company_id=self.company.id,
            snapshot_date=snapshot_date,
            gross_revenue=Decimal(gross_revenue),
            cash_revenue=Decimal("0.00"),
            check_sight_revenue=Decimal("0.00"),
            check_term_revenue=Decimal("0.00"),
            inhouse_credit_revenue=Decimal("0.00"),
            card_revenue=Decimal("0.00"),
            convenio_revenue=Decimal("0.00"),
            pix_revenue=Decimal("0.00"),
            financing_revenue=Decimal("0.00"),
            markup=Decimal(markup),
            discount_or_surcharge=Decimal(discount_or_surcharge),
        )
        self.db.add(snapshot)
        self.db.commit()
        return snapshot

    def _add_linx_movement(
        self,
        *,
        movement_date: date,
        movement_type: str,
        total_amount: str,
        quantity: str = "1.00",
        cost_price: str = "0.00",
    ) -> LinxMovement:
        movement = LinxMovement(
            company_id=self.company.id,
            linx_transaction=int(datetime.combine(movement_date, datetime.min.time()).timestamp()),
            movement_group="sale",
            movement_type=movement_type,
            launch_date=datetime.combine(movement_date, datetime.min.time()),
            issue_date=datetime.combine(movement_date, datetime.min.time()),
            quantity=Decimal(quantity),
            cost_price=Decimal(cost_price),
            total_amount=Decimal(total_amount),
            net_amount=Decimal(total_amount),
        )
        self.db.add(movement)
        self.db.commit()
        return movement

    def test_current_balance_uses_partial_expense_paid_amount(self) -> None:
        account = self._add_account("Caixa", "1000.00")
        self._add_entry(
            account=account,
            entry_type="expense",
            status="partial",
            total_amount="100.00",
            paid_amount="40.00",
            title="Conta parcial",
        )

        overview = build_cashflow_overview(self.db, self.company)

        self.assertEqual(overview.current_balance, Decimal("960.00"))
        self.assertEqual(overview.account_balances[0].current_balance, Decimal("960.00"))

    def test_company_catalog_does_not_overwrite_manual_category_hierarchy(self) -> None:
        category = self._add_category(
            name="Despesa Salarios",
            code="4.1.2.1.1",
            report_group="Despesa com Pessoal",
            report_subgroup="",
        )

        ensure_company_catalog(self.db, self.company.id)
        self.db.refresh(category)

        self.assertEqual(category.report_group, "Despesa com Pessoal")
        self.assertEqual(category.report_subgroup, "")

    def test_category_catalog_does_not_reactivate_or_reclassify_existing_category(self) -> None:
        category = Category(
            company_id=self.company.id,
            code="4.1.3.5",
            name="Juros Pagos",
            entry_kind="expense",
            report_group="Financeiro Manual",
            report_subgroup=None,
            is_financial_expense=False,
            is_active=False,
        )
        self.db.add(category)
        self.db.commit()

        ensure_category_catalog(self.db, self.company.id)
        self.db.refresh(category)

        self.assertEqual(category.report_group, "Financeiro Manual")
        self.assertIsNone(category.report_subgroup)
        self.assertFalse(category.is_active)
        self.assertFalse(category.is_financial_expense)

    def test_current_balance_uses_partial_income_paid_amount(self) -> None:
        account = self._add_account("Banco", "1000.00")
        self._add_entry(
            account=account,
            entry_type="income",
            status="partial",
            total_amount="100.00",
            paid_amount="40.00",
            title="Recebimento parcial",
        )

        overview = build_cashflow_overview(self.db, self.company)

        self.assertEqual(overview.current_balance, Decimal("1040.00"))
        self.assertEqual(overview.account_balances[0].current_balance, Decimal("1040.00"))

    def test_current_balance_ignores_imported_bank_transactions(self) -> None:
        account = self._add_account("Conta Corrente", "1000.00")
        self._add_bank_transaction(
            account=account,
            posted_at=date(2026, 3, 23),
            amount="200.00",
            fit_id="ofx-001",
        )
        self._add_entry(
            account=account,
            entry_type="expense",
            status="settled",
            total_amount="100.00",
            paid_amount="100.00",
            title="Despesa paga",
        )

        overview = build_cashflow_overview(self.db, self.company)

        self.assertEqual(overview.current_balance, Decimal("900.00"))

    def test_company_balance_remains_constant_for_settled_internal_transfer(self) -> None:
        source_account = self._add_account("Caixa Loja", "1000.00")
        destination_account = self._add_account("Aplicacoes", "200.00")

        transfer = create_transfer(
            self.db,
            self.company,
            TransferCreate(
                source_account_id=source_account.id,
                destination_account_id=destination_account.id,
                transfer_date=date(2026, 3, 23),
                amount=Decimal("50.00"),
                status="settled",
                description="Aporte interno",
            ),
            self.user,
        )
        self.db.commit()

        overview = build_cashflow_overview(self.db, self.company)
        balances = {item.account_name: item.current_balance for item in overview.account_balances}

        self.assertIsNotNone(transfer.source_entry_id)
        self.assertIsNotNone(transfer.destination_entry_id)
        self.assertEqual(overview.current_balance, Decimal("1200.00"))
        self.assertEqual(balances["Caixa Loja"], Decimal("950.00"))
        self.assertEqual(balances["Aplicacoes"], Decimal("250.00"))

    def test_dro_uses_partial_expense_paid_amount(self) -> None:
        account = self._add_account("Banco", "0.00")
        expense_category = self._add_category()
        self._add_entry(
            account=account,
            category=expense_category,
            entry_type="expense",
            status="partial",
            total_amount="100.00",
            paid_amount="40.00",
            due_date=date(2026, 3, 23),
            title="Despesa parcial DRO",
        )

        overview = build_reports_overview(
            self.db,
            self.company,
            start=date(2026, 3, 1),
            end=date(2026, 3, 31),
        )

        self.assertEqual(overview.dro.operating_expenses, Decimal("40.00"))

    def test_dre_ignores_operating_receipts_and_keeps_them_only_in_dro(self) -> None:
        account = self._add_account("Banco", "0.00")
        income_category = self._add_category(
            name="Receitas",
            code="3.1.1.1",
            entry_kind="income",
            report_group="Receitas",
            report_subgroup="Receitas",
        )
        self._add_linx_movement(
            movement_date=date(2026, 3, 23),
            movement_type="sale",
            total_amount="1000.00",
            quantity="2.00",
            cost_price="250.00",
        )
        self._add_entry(
            account=account,
            category=income_category,
            entry_type="income",
            status="settled",
            total_amount="200.00",
            paid_amount="200.00",
            due_date=date(2026, 3, 23),
            title="Recebimento Vendas",
        )

        overview = build_reports_overview(
            self.db,
            self.company,
            start=date(2026, 3, 1),
            end=date(2026, 3, 31),
        )

        self.assertEqual(overview.dre.gross_revenue, Decimal("1000.00"))
        self.assertEqual(overview.dre.net_revenue, Decimal("1000.00"))
        self.assertEqual(overview.dre.other_operating_income, Decimal("0.00"))
        self.assertEqual(overview.dro.bank_revenue, Decimal("200.00"))

    def test_linx_sales_import_persists_snapshots_without_creating_entries(self) -> None:
        rows = [
            ParsedSalesRow(
                snapshot_date=date(2026, 3, 23),
                gross_revenue=Decimal("1000.00"),
                cash_revenue=Decimal("100.00"),
                check_sight_revenue=Decimal("0.00"),
                check_term_revenue=Decimal("0.00"),
                inhouse_credit_revenue=Decimal("0.00"),
                card_revenue=Decimal("700.00"),
                convenio_revenue=Decimal("0.00"),
                pix_revenue=Decimal("200.00"),
                financing_revenue=Decimal("0.00"),
                markup=Decimal("100.00"),
                discount_or_surcharge=Decimal("0.00"),
            )
        ]

        with patch("app.services.imports.parse_sales_rows", return_value=rows):
            result = import_linx_sales(self.db, self.company, "faturamento.html", b"conteudo")

        self.assertEqual(result.batch.records_total, 1)
        self.assertEqual(self.db.query(SalesSnapshot).count(), 1)
        self.assertEqual(self.db.query(FinancialEntry).count(), 0)

    def test_ensure_company_catalog_cleans_open_linx_sales_entries(self) -> None:
        control_account = self._add_account(
            "Recebiveis Cartao, Debito e Pix",
            "0.00",
            account_type="receivables_control",
        )
        open_entry = self._add_entry(
            account=control_account,
            entry_type="income",
            status="planned",
            total_amount="150.00",
            title="Cartao e Debito a Receber 2026-03-23",
            source_system="linx_sales_control",
        )
        partial_entry = self._add_entry(
            account=control_account,
            entry_type="income",
            status="partial",
            total_amount="200.00",
            paid_amount="50.00",
            title="Pix a Receber 2026-03-24",
            source_system="linx_sales_control",
        )
        settled_entry = self._add_entry(
            account=control_account,
            entry_type="income",
            status="settled",
            total_amount="100.00",
            paid_amount="100.00",
            title="Cartao e Debito a Receber 2026-03-22",
            source_system="linx_sales_control",
        )

        ensure_company_catalog(self.db, self.company.id)
        self.db.refresh(control_account)
        self.db.refresh(open_entry)
        self.db.refresh(partial_entry)
        self.db.refresh(settled_entry)

        self.assertFalse(control_account.is_active)
        self.assertTrue(open_entry.is_deleted)
        self.assertEqual(open_entry.status, "cancelled")
        self.assertTrue(partial_entry.is_deleted)
        self.assertEqual(partial_entry.status, "cancelled")
        self.assertFalse(settled_entry.is_deleted)
        self.assertEqual(settled_entry.status, "settled")

    def test_account_projection_includes_planned_transfer(self) -> None:
        source_account = self._add_account("Caixa Loja", "1000.00")
        destination_account = self._add_account("Reserva", "0.00")

        create_transfer(
            self.db,
            self.company,
            TransferCreate(
                source_account_id=source_account.id,
                destination_account_id=destination_account.id,
                transfer_date=date(2026, 3, 25),
                amount=Decimal("100.00"),
                status="planned",
                description="Reserva semanal",
            ),
            self.user,
        )
        self.db.commit()

        source_overview = build_cashflow_overview(
            self.db,
            self.company,
            start_date=date(2026, 3, 24),
            end_date=date(2026, 3, 26),
            account_id=source_account.id,
        )
        destination_overview = build_cashflow_overview(
            self.db,
            self.company,
            start_date=date(2026, 3, 24),
            end_date=date(2026, 3, 26),
            account_id=destination_account.id,
        )

        self.assertEqual(source_overview.projected_outflows, Decimal("100.00"))
        self.assertEqual(source_overview.projected_ending_balance, Decimal("900.00"))
        self.assertEqual(destination_overview.projected_inflows, Decimal("100.00"))
        self.assertEqual(destination_overview.projected_ending_balance, Decimal("100.00"))

    def test_cashflow_ignores_deleted_open_entries(self) -> None:
        account = self._add_account("Inter", "2825.00")
        expense_category = self._add_category()
        deleted_entry = self._add_entry(
            account=account,
            category=expense_category,
            entry_type="expense",
            status="planned",
            total_amount="30000.00",
            due_date=date(2026, 3, 10),
            title="Parcela excluida",
        )
        deleted_entry.is_deleted = True
        deleted_entry.status = "cancelled"
        self.db.commit()

        overview = build_cashflow_overview(
            self.db,
            self.company,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            include_crediario_receivables=False,
            include_purchase_planning=False,
        )

        self.assertEqual(overview.projected_outflows, Decimal("0.00"))
        self.assertEqual(overview.projected_ending_balance, Decimal("2825.00"))

    def test_reconciliation_assigns_bank_account_to_generated_settlement_adjustments(self) -> None:
        account = self._add_account("Inter", "0.00")
        category = self._add_category(name="Financeiro", code="6.1.1.1")
        transaction = self._add_bank_transaction(
            account=account,
            posted_at=date(2026, 3, 3),
            amount="-4984.52",
            fit_id="ofx-ajuste-001",
        )
        entry = self._add_entry(
            account=None,
            category=category,
            entry_type="expense",
            status="planned",
            total_amount="2083.33",
            due_date=date(2026, 3, 3),
            title="BANCO BRADESCO S.A",
        )

        create_reconciliation(
            self.db,
            self.company,
            ReconciliationCreate(
                bank_transaction_ids=[transaction.id],
                financial_entry_ids=[entry.id],
                principal_amount=Decimal("2083.33"),
                interest_amount=Decimal("2901.19"),
            ),
            self.user,
        )
        self.db.commit()
        self.db.refresh(entry)

        adjustment = self.db.query(FinancialEntry).filter(
            FinancialEntry.source_system == "settlement_adjustment",
            FinancialEntry.source_reference == f"settlement-adjustment:{entry.id}:interest",
            FinancialEntry.is_deleted.is_(False),
        ).one()

        self.assertEqual(entry.account_id, account.id)
        self.assertEqual(adjustment.account_id, account.id)
        self.assertEqual(adjustment.total_amount, Decimal("2901.19"))

    def test_discount_adjustment_increases_account_balance_after_reconciliation(self) -> None:
        account = self._add_account("Inter", "1000.00")
        category = self._add_category(name="Financeiro", code="6.1.1.1")
        transaction = self._add_bank_transaction(
            account=account,
            posted_at=date(2026, 1, 8),
            amount="-998.44",
            fit_id="ofx-desconto-001",
        )
        entry = self._add_entry(
            account=account,
            category=category,
            entry_type="expense",
            status="planned",
            total_amount="1536.00",
            due_date=date(2026, 1, 8),
            title="VESTE S.A. ESTILO",
        )

        create_reconciliation(
            self.db,
            self.company,
            ReconciliationCreate(
                bank_transaction_ids=[transaction.id],
                financial_entry_ids=[entry.id],
                principal_amount=Decimal("1536.00"),
                discount_amount=Decimal("537.56"),
            ),
            self.user,
        )
        self.db.commit()

        discount_entry = self.db.query(FinancialEntry).filter(
            FinancialEntry.source_system == "settlement_adjustment",
            FinancialEntry.source_reference == f"settlement-adjustment:{entry.id}:discount",
            FinancialEntry.is_deleted.is_(False),
        ).one()
        overview = build_cashflow_overview(self.db, self.company, account_id=account.id)

        self.assertEqual(discount_entry.entry_type, "income")
        self.assertEqual(overview.current_balance, Decimal("1.56"))

    def test_reconciliation_generates_purchase_return_credit_entry(self) -> None:
        account = self._add_account("Inter", "0.00")
        purchase_category = self._add_category(
            name="Compras",
            code="3.3.1",
            report_group="Compras",
            report_subgroup="Compras",
        )
        supplier = Supplier(
            company_id=self.company.id,
            name="Fornecedor X",
            default_payment_term="1x",
            payment_basis="delivery",
            has_purchase_invoices=False,
            is_active=True,
        )
        self.db.add(supplier)
        self.db.commit()

        transaction = self._add_bank_transaction(
            account=account,
            posted_at=date(2026, 4, 20),
            amount="-1000.00",
            fit_id="ofx-devolucao-001",
        )
        entry = self._add_entry(
            account=account,
            category=purchase_category,
            entry_type="expense",
            status="planned",
            total_amount="1500.00",
            due_date=date(2026, 4, 20),
            title="NF fornecedor",
        )
        entry.supplier_id = supplier.id
        entry.counterparty_name = supplier.name
        entry.document_number = "NF-500"
        self.db.commit()

        create_reconciliation(
            self.db,
            self.company,
            ReconciliationCreate(
                bank_transaction_ids=[transaction.id],
                financial_entry_ids=[entry.id],
                principal_amount=Decimal("1500.00"),
                penalty_amount=Decimal("500.00"),
            ),
            self.user,
        )
        self.db.commit()
        self.db.refresh(entry)

        purchase_return_category = ensure_category_catalog(self.db, self.company.id)["Devolucoes de Compra"]
        credit_entry = self.db.query(FinancialEntry).filter(
            FinancialEntry.source_system == "settlement_adjustment",
            FinancialEntry.source_reference == f"settlement-adjustment:{entry.id}:return_credit",
            FinancialEntry.is_deleted.is_(False),
        ).one()

        self.assertEqual(entry.status, "settled")
        self.assertEqual(entry.paid_amount, Decimal("1500.00"))
        self.assertEqual(entry.total_amount, Decimal("1500.00"))
        self.assertEqual(credit_entry.entry_type, "income")
        self.assertEqual(credit_entry.status, "planned")
        self.assertEqual(credit_entry.category_id, purchase_return_category.id)
        self.assertEqual(credit_entry.supplier_id, supplier.id)
        self.assertEqual(credit_entry.document_number, "NF-500")
        self.assertEqual(credit_entry.total_amount, Decimal("500.00"))
        self.assertEqual(credit_entry.paid_amount, Decimal("0.00"))
        self.assertIsNone(credit_entry.account_id)

    def test_settle_entry_requires_due_date(self) -> None:
        account = self._add_account("Caixa Loja", "0.00")
        category = self._add_category()
        entry = self._add_entry(
            account=account,
            category=category,
            entry_type="expense",
            status="planned",
            total_amount="100.00",
            due_date=None,
            title="Sem vencimento",
        )
        entry.due_date = None
        entry.competence_date = None
        entry.issue_date = None
        self.db.commit()

        with self.assertRaises(HTTPException) as context:
            settle_entry(
                self.db,
                self.company,
                entry.id,
                EntrySettlementRequest(account_id=account.id),
                self.user,
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Data de vencimento obrigatoria", context.exception.detail)

    def test_reconciliation_requires_due_date(self) -> None:
        account = self._add_account("Inter", "0.00")
        category = self._add_category(name="Financeiro", code="6.1.1.1")
        transaction = self._add_bank_transaction(
            account=account,
            posted_at=date(2026, 3, 3),
            amount="-100.00",
            fit_id="ofx-sem-vencimento-001",
        )
        entry = self._add_entry(
            account=account,
            category=category,
            entry_type="expense",
            status="planned",
            total_amount="100.00",
            due_date=None,
            title="Despesa sem vencimento",
        )
        entry.due_date = None
        entry.competence_date = None
        entry.issue_date = None
        self.db.commit()

        with self.assertRaises(ValueError) as context:
            create_reconciliation(
                self.db,
                self.company,
                ReconciliationCreate(
                    bank_transaction_ids=[transaction.id],
                    financial_entry_ids=[entry.id],
                ),
                self.user,
            )

        self.assertIn("Data de vencimento obrigatoria", str(context.exception))

    def test_grouped_bank_entry_uses_signed_net_amount_for_mixed_movements(self) -> None:
        account = self._add_account("Inter", "0.00")
        category = self._add_category(name="Operacional", code="6.1.1.1", entry_kind="expense")
        outgoing = self._add_bank_transaction(
            account=account,
            posted_at=date(2026, 4, 8),
            amount="-10000.00",
            fit_id="ofx-mix-001",
        )
        incoming_one = self._add_bank_transaction(
            account=account,
            posted_at=date(2026, 4, 9),
            amount="1000.00",
            fit_id="ofx-mix-002",
        )
        incoming_two = self._add_bank_transaction(
            account=account,
            posted_at=date(2026, 4, 9),
            amount="1000.00",
            fit_id="ofx-mix-003",
        )

        result = create_entry_from_bank_transaction(
            self.db,
            self.company,
            BankTransactionActionCreate(
                bank_transaction_ids=[incoming_one.id, incoming_two.id, outgoing.id],
                action_type="create_entry",
                category_id=category.id,
            ),
            self.user,
        )
        self.db.commit()

        entry = self.db.get(FinancialEntry, result["financial_entry_id"])
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.entry_type, "expense")
        self.assertEqual(entry.total_amount, Decimal("8000.00"))
        self.assertEqual(entry.principal_amount, Decimal("8000.00"))
        self.assertEqual(entry.title, "Pagamento agrupado (3 movimentos)")

    def test_cashflow_uses_purchase_planning_monthly_simulation(self) -> None:
        supplier = Supplier(
            company_id=self.company.id,
            name="Fornecedor Fluxo",
            default_payment_term="3x",
            payment_basis="delivery",
            is_active=True,
        )
        collection = CollectionSeason(
            company_id=self.company.id,
            name="Inverno 2026",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 5, 31),
            is_active=True,
        )
        self.db.add_all([supplier, collection])
        self.db.flush()
        self.db.add(
            PurchasePlan(
                company_id=self.company.id,
                supplier_id=supplier.id,
                collection_id=collection.id,
                title="Compra Projetada",
                order_date=date(2026, 3, 24),
                expected_delivery_date=date(2026, 4, 10),
                purchased_amount=Decimal("3000.00"),
                payment_term="3x",
                status="planned",
            )
        )
        self.db.commit()

        with patch("app.services.purchase_planning._today", return_value=date(2026, 3, 24)):
            overview = build_cashflow_overview(
                self.db,
                self.company,
                start_date=date(2026, 4, 1),
                end_date=date(2026, 8, 31),
            )

        projected_by_month = {item.reference: item.planned_purchase_outflows for item in overview.monthly_projection}

        self.assertEqual(overview.planned_purchase_outflows, Decimal("3000.00"))
        self.assertEqual(overview.projected_outflows, Decimal("3000.00"))
        self.assertEqual(projected_by_month["2026-04"], Decimal("333.33"))
        self.assertEqual(projected_by_month["2026-05"], Decimal("666.66"))
        self.assertEqual(projected_by_month["2026-06"], Decimal("1000.00"))
        self.assertEqual(projected_by_month["2026-07"], Decimal("666.67"))
        self.assertEqual(projected_by_month["2026-08"], Decimal("333.34"))


if __name__ == "__main__":
    unittest.main()
