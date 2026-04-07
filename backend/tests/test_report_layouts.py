from __future__ import annotations

import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models.finance import Account, Category, FinancialEntry
from app.db.models.linx import LinxMovement, SalesSnapshot
from app.db.models.reporting import ReportLayoutLine
from app.db.models.security import Company, User
from app.schemas.reports import ReportConfigLine, ReportConfigUpdate, ReportGroupSelection
from app.services.dashboard import build_dashboard_overview
from app.services.report_layouts import get_or_create_report_config, update_report_config
from app.services.reports import build_reports_overview


class ReportLayoutTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp_db = NamedTemporaryFile(prefix="report_layouts_", suffix=".db", delete=False, dir=Path.cwd())
        temp_db.close()
        self.db_path = Path(temp_db.name)
        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self.db: Session = self.SessionLocal()

        self.company = Company(legal_name="Empresa Teste Ltda", trade_name="Empresa Teste", document="12345678000199")
        self.user = User(
            company=self.company,
            full_name="Teste",
            email=f"layout-{self.db_path.stem}@example.com",
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

    def _add_account(self, name: str) -> Account:
        account = Account(company_id=self.company.id, name=name, account_type="checking", opening_balance=Decimal("0.00"), is_active=True)
        self.db.add(account)
        self.db.commit()
        return account

    def _add_category(self, *, name: str, code: str, entry_kind: str, report_group: str, report_subgroup: str | None = None) -> Category:
        category = Category(
            company_id=self.company.id,
            name=name,
            code=code,
            entry_kind=entry_kind,
            report_group=report_group,
            report_subgroup=report_subgroup,
            is_active=True,
        )
        self.db.add(category)
        self.db.commit()
        return category

    def _add_entry(self, *, account: Account, category: Category, entry_type: str, total_amount: str, paid_amount: str | None = None) -> FinancialEntry:
        entry = FinancialEntry(
            company_id=self.company.id,
            account_id=account.id,
            category_id=category.id,
            entry_type=entry_type,
            status="settled",
            title=f"{entry_type}-{category.name}",
            issue_date=date(2026, 3, 10),
            competence_date=date(2026, 3, 10),
            due_date=date(2026, 3, 10),
            principal_amount=Decimal(total_amount),
            total_amount=Decimal(total_amount),
            paid_amount=Decimal(paid_amount or total_amount),
            is_deleted=False,
            source_system="manual",
        )
        self.db.add(entry)
        self.db.commit()
        return entry

    def _group_selection(self, group_name: str, operation: str = "add") -> ReportGroupSelection:
        return ReportGroupSelection(group_name=group_name, operation=operation)

    def _add_entry_custom_dates(
        self,
        *,
        account: Account,
        category: Category,
        entry_type: str,
        total_amount: str,
        issue_date: date,
        competence_date: date | None,
        due_date: date | None,
        status: str = "planned",
    ) -> FinancialEntry:
        entry = FinancialEntry(
            company_id=self.company.id,
            account_id=account.id,
            category_id=category.id,
            entry_type=entry_type,
            status=status,
            title=f"{entry_type}-{category.name}",
            issue_date=issue_date,
            competence_date=competence_date,
            due_date=due_date,
            principal_amount=Decimal(total_amount),
            total_amount=Decimal(total_amount),
            paid_amount=Decimal("0.00"),
            is_deleted=False,
            source_system="manual",
        )
        self.db.add(entry)
        self.db.commit()
        return entry

    def _add_snapshot(self, *, gross_revenue: str, markup: str = "100.00", discount_or_surcharge: str = "0.00") -> SalesSnapshot:
        snapshot = SalesSnapshot(
            company_id=self.company.id,
            snapshot_date=date(2026, 3, 10),
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

    def _add_movement(
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

    def test_get_or_create_report_config_seeds_default_layout(self) -> None:
        config = get_or_create_report_config(self.db, self.company, "dre")

        self.assertEqual(config.kind, "dre")
        self.assertGreater(len(config.lines), 5)
        self.assertIn("gross_revenue", {line.summary_binding for line in config.lines if line.summary_binding})
        self.assertEqual([option.value for option in config.special_source_options], ["faturamento_bruto", "deducoes_faturamento", "cmv_faturamento"])
        self.assertTrue(any(line.show_on_dashboard for line in config.lines))

    def test_update_report_config_rejects_duplicate_group_in_same_report(self) -> None:
        config = get_or_create_report_config(self.db, self.company, "dro")
        lines = [line.model_copy(deep=True) for line in config.lines]
        lines[0] = lines[0].model_copy(
            update={"special_source": None, "category_groups": [self._group_selection("group:Receitas de Vendas")]}
        )
        lines[1] = lines[1].model_copy(
            update={"special_source": None, "category_groups": [self._group_selection("group:Receitas de Vendas")]}
        )

        with self.assertRaises(HTTPException) as raised:
            update_report_config(self.db, self.company, "dro", ReportConfigUpdate(lines=lines))

        self.assertIn("grupo", raised.exception.detail.lower())

    def test_update_report_config_rejects_totalizer_depending_on_future_line(self) -> None:
        config = get_or_create_report_config(self.db, self.company, "dre")
        lines = [line.model_copy(deep=True) for line in config.lines]
        first_totalizer_index = next(index for index, line in enumerate(lines) if line.line_type == "totalizer")
        lines[first_totalizer_index] = ReportConfigLine.model_validate(
            lines[first_totalizer_index].model_dump()
            | {"formula": [{"referenced_line_id": lines[-1].id, "operation": "add"}]},
        )

        with self.assertRaises(HTTPException) as raised:
            update_report_config(self.db, self.company, "dre", ReportConfigUpdate(lines=lines))

        self.assertIn("linhas anteriores", raised.exception.detail.lower())

    def test_update_report_config_allows_totalizer_using_another_totalizer(self) -> None:
        config = get_or_create_report_config(self.db, self.company, "dre")
        lines = [line.model_copy(deep=True) for line in config.lines]
        totalizer_indexes = [index for index, line in enumerate(lines) if line.line_type == "totalizer"]
        lines[totalizer_indexes[1]] = ReportConfigLine.model_validate(
            lines[totalizer_indexes[1]].model_dump()
            | {"formula": [{"referenced_line_id": lines[totalizer_indexes[0]].id, "operation": "add"}]}
        )

        updated = update_report_config(self.db, self.company, "dre", ReportConfigUpdate(lines=lines))

        updated_line = next(line for line in updated.lines if line.id == lines[totalizer_indexes[1]].id)
        self.assertEqual(updated_line.formula[0].referenced_line_id, lines[totalizer_indexes[0]].id)

    def test_update_report_config_allows_special_source_combined_with_groups(self) -> None:
        config = get_or_create_report_config(self.db, self.company, "dre")
        lines = [line.model_copy(deep=True) for line in config.lines]
        lines[1] = lines[1].model_copy(
            update={
                "special_source": "deducoes_faturamento",
                "category_groups": [self._group_selection("subgroup:Impostos e Taxas")],
            }
        )

        updated = update_report_config(self.db, self.company, "dre", ReportConfigUpdate(lines=lines))

        self.assertEqual(updated.lines[1].special_source, "deducoes_faturamento")
        self.assertIn("subgroup:Impostos e Taxas", {group.group_name for group in updated.lines[1].category_groups})

    def test_existing_legacy_special_source_is_migrated_to_category_groups(self) -> None:
        config = get_or_create_report_config(self.db, self.company, "dro")
        revenue_line = next(line for line in config.lines if line.summary_binding == "bank_revenue")

        db_line = self.db.get(ReportLayoutLine, revenue_line.id)
        self.assertIsNotNone(db_line)
        db_line.special_source = "receitas_operacionais_dro"
        self.db.commit()

        migrated = get_or_create_report_config(self.db, self.company, "dro")
        migrated_line = next(line for line in migrated.lines if line.summary_binding == "bank_revenue")

        self.assertIsNone(migrated_line.special_source)
        self.assertIn("group:Receitas", {group.group_name for group in migrated_line.category_groups})

    def test_existing_totalizer_formula_is_preserved(self) -> None:
        config = get_or_create_report_config(self.db, self.company, "dre")
        net_line = next(line for line in config.lines if line.summary_binding == "net_revenue")
        gross_profit_line = next(line for line in config.lines if line.summary_binding == "gross_profit")

        db_line = self.db.get(ReportLayoutLine, gross_profit_line.id)
        self.assertIsNotNone(db_line)
        formula_line = next(item for item in db_line.formula_items if item.position == 1)
        formula_line.referenced_line_id = net_line.id
        self.db.commit()

        migrated = get_or_create_report_config(self.db, self.company, "dre")
        migrated_gross_profit = next(line for line in migrated.lines if line.summary_binding == "gross_profit")

        self.assertTrue(any(item.referenced_line_id == net_line.id for item in migrated_gross_profit.formula))

    def test_dre_uses_linx_movements_special_sources_from_default_layout(self) -> None:
        self._add_movement(movement_date=date(2026, 3, 10), movement_type="sale", total_amount="1000.00", quantity="2.00", cost_price="250.00")
        self._add_movement(movement_date=date(2026, 3, 11), movement_type="sale_return", total_amount="100.00")

        overview = build_reports_overview(self.db, self.company, start=date(2026, 3, 1), end=date(2026, 3, 31))

        self.assertEqual(overview.dre.gross_revenue, Decimal("1000.00"))
        self.assertEqual(overview.dre.deductions, Decimal("100.00"))
        self.assertEqual(overview.dre.net_revenue, Decimal("900.00"))
        self.assertEqual(overview.dre.cmv, Decimal("500.00"))
        self.assertEqual(overview.dre.net_profit, Decimal("400.00"))
        self.assertEqual(overview.dre.statement[0].percent, Decimal("100.00"))

    def test_dashboard_uses_dre_dashboard_cards_with_configured_names(self) -> None:
        config = get_or_create_report_config(self.db, self.company, "dre")
        lines = [line.model_copy(deep=True) for line in config.lines]
        lines[0] = lines[0].model_copy(update={"name": "RECEITA BRUTA", "show_on_dashboard": True})
        lines[1] = lines[1].model_copy(update={"name": "(-) DEDUCOES", "show_on_dashboard": False})
        lines[2] = lines[2].model_copy(update={"name": "(=) RECEITA LIQUIDA", "show_on_dashboard": True})
        update_report_config(self.db, self.company, "dre", ReportConfigUpdate(lines=lines))

        dashboard = build_dashboard_overview(self.db, self.company, start=date(2026, 3, 1), end=date(2026, 3, 31))

        self.assertEqual([item.label for item in dashboard.dre_chart[:2]], ["RECEITA BRUTA", "(=) RECEITA LIQUIDA"])
        self.assertEqual([item.label for item in dashboard.dre_cards[:2]], ["RECEITA BRUTA", "(=) RECEITA LIQUIDA"])
        self.assertNotIn("(-) DEDUCOES", {item.label for item in dashboard.dre_chart})

    def test_dashboard_groups_revenue_comparison_by_month_for_current_and_previous_year(self) -> None:
        self._add_snapshot(gross_revenue="1000.00")
        previous_year_snapshot = SalesSnapshot(
            company_id=self.company.id,
            snapshot_date=date(2025, 3, 15),
            gross_revenue=Decimal("250.00"),
            cash_revenue=Decimal("0.00"),
            check_sight_revenue=Decimal("0.00"),
            check_term_revenue=Decimal("0.00"),
            inhouse_credit_revenue=Decimal("0.00"),
            card_revenue=Decimal("0.00"),
            convenio_revenue=Decimal("0.00"),
            pix_revenue=Decimal("0.00"),
            financing_revenue=Decimal("0.00"),
            markup=Decimal("100.00"),
            discount_or_surcharge=Decimal("0.00"),
        )
        current_year_extra_snapshot = SalesSnapshot(
            company_id=self.company.id,
            snapshot_date=date(2026, 3, 20),
            gross_revenue=Decimal("300.00"),
            cash_revenue=Decimal("0.00"),
            check_sight_revenue=Decimal("0.00"),
            check_term_revenue=Decimal("0.00"),
            inhouse_credit_revenue=Decimal("0.00"),
            card_revenue=Decimal("0.00"),
            convenio_revenue=Decimal("0.00"),
            pix_revenue=Decimal("0.00"),
            financing_revenue=Decimal("0.00"),
            markup=Decimal("100.00"),
            discount_or_surcharge=Decimal("0.00"),
        )
        self.db.add_all([previous_year_snapshot, current_year_extra_snapshot])
        self.db.commit()

        dashboard = build_dashboard_overview(self.db, self.company, start=date(2026, 3, 1), end=date(2026, 3, 31))

        march_point = next(point for point in dashboard.revenue_comparison.points if point.month == 3)
        april_point = next(point for point in dashboard.revenue_comparison.points if point.month == 4)

        self.assertEqual(dashboard.revenue_comparison.current_year, 2026)
        self.assertEqual(dashboard.revenue_comparison.previous_year, 2025)
        self.assertEqual(march_point.current_year_value, Decimal("1300.00"))
        self.assertEqual(march_point.previous_year_value, Decimal("250.00"))
        self.assertEqual(april_point.current_year_value, Decimal("0.00"))
        self.assertEqual(april_point.previous_year_value, Decimal("0.00"))

    def test_grouped_children_percent_uses_parent_total(self) -> None:
        account = self._add_account("Banco")
        personnel_category = self._add_category(
            name="Salarios",
            code="4.1.2.1",
            entry_kind="expense",
            report_group="Despesas Operacionais",
            report_subgroup="Despesa com Pessoal",
        )
        sales_category = self._add_category(
            name="Comissao",
            code="4.1.1.1",
            entry_kind="expense",
            report_group="Despesas Operacionais",
            report_subgroup="Despesas de Vendas",
        )
        self._add_entry(account=account, category=personnel_category, entry_type="expense", total_amount="50.00")
        self._add_entry(account=account, category=sales_category, entry_type="expense", total_amount="50.00")

        config = get_or_create_report_config(self.db, self.company, "dre")
        lines = [line.model_copy(deep=True) for line in config.lines]
        expenses_index = next(index for index, line in enumerate(lines) if line.summary_binding == "operating_expenses")
        lines[expenses_index] = lines[expenses_index].model_copy(
            update={
                "show_percent": True,
                "percent_mode": "grouped_children",
                "percent_reference_line_id": None,
            }
        )
        update_report_config(self.db, self.company, "dre", ReportConfigUpdate(lines=lines))

        overview = build_reports_overview(self.db, self.company, start=date(2026, 3, 1), end=date(2026, 3, 31))
        expenses_node = next(node for node in overview.dre.statement if node.label == lines[expenses_index].name)

        self.assertEqual(expenses_node.percent, Decimal("100.00"))
        self.assertTrue(all(child.percent == Decimal("50.00") for child in expenses_node.children))

    def test_dro_uses_category_groups_instead_of_special_sources_from_default_layout(self) -> None:
        account = self._add_account("Banco")
        purchase_category = self._add_category(
            name="Compra paga",
            code="3.3.1.1",
            entry_kind="expense",
            report_group="Compras Pagas",
            report_subgroup="Compras Pagas",
        )
        revenue_category = self._add_category(
            name="Receita loja",
            code="3.1.1.1",
            entry_kind="income",
            report_group="Receitas de Vendas",
            report_subgroup="Receitas de Vendas",
        )
        self._add_entry(account=account, category=purchase_category, entry_type="expense", total_amount="120.00")
        self._add_entry(account=account, category=revenue_category, entry_type="income", total_amount="500.00")

        overview = build_reports_overview(self.db, self.company, start=date(2026, 3, 1), end=date(2026, 3, 31))

        self.assertEqual(overview.dro.purchases_paid, Decimal("120.00"))
        self.assertEqual(overview.dro.bank_revenue, Decimal("500.00"))
        self.assertEqual(overview.dro.contribution_margin, Decimal("380.00"))
        config = get_or_create_report_config(self.db, self.company, "dro")
        self.assertEqual(config.special_source_options, [])
        self.assertTrue(any(option.scope == "subgroup" for option in config.available_groups))

    def test_dre_uses_competence_and_dro_uses_due_date(self) -> None:
        account = self._add_account("Banco")
        tax_category = self._add_category(
            name="Simples Nacional",
            code="4.1.4.1.2",
            entry_kind="expense",
            report_group="Imposto de Vendas",
        )
        self._add_movement(movement_date=date(2026, 3, 10), movement_type="sale", total_amount="1000.00", quantity="2.00", cost_price="250.00")
        self._add_movement(movement_date=date(2026, 3, 10), movement_type="sale_return", total_amount="100.00")
        self._add_entry_custom_dates(
            account=account,
            category=tax_category,
            entry_type="expense",
            total_amount="250.00",
            issue_date=date(2026, 3, 20),
            competence_date=date(2026, 3, 20),
            due_date=date(2026, 4, 20),
            status="planned",
        )

        dre_config = get_or_create_report_config(self.db, self.company, "dre")
        lines = [line.model_copy(deep=True) for line in dre_config.lines]
        lines[1] = lines[1].model_copy(
            update={
                "special_source": "deducoes_faturamento",
                "category_groups": [self._group_selection("group:Imposto de Vendas", "subtract")],
            }
        )
        update_report_config(self.db, self.company, "dre", ReportConfigUpdate(lines=lines))

        overview_march = build_reports_overview(self.db, self.company, start=date(2026, 3, 1), end=date(2026, 3, 31))
        deduction_node = next(node for node in overview_march.dre.statement if "Dedu" in node.label)
        deduction_labels = [child.label for child in deduction_node.children]

        self.assertEqual(overview_march.dre.deductions, Decimal("350.00"))
        self.assertIn("Devolucoes de venda da API Linx", deduction_labels)
        self.assertIn("Imposto de Vendas", deduction_labels)
        self.assertNotIn("Faturamento", deduction_labels)
        self.assertEqual(overview_march.dro.sales_taxes, Decimal("0.00"))

        overview_april = build_reports_overview(self.db, self.company, start=date(2026, 4, 1), end=date(2026, 4, 30))
        self.assertEqual(overview_april.dro.sales_taxes, Decimal("250.00"))

    def test_source_line_allows_mixed_signs_per_group_selection(self) -> None:
        account = self._add_account("Banco")
        purchase_category = self._add_category(
            name="Compra paga",
            code="3.3.1.1",
            entry_kind="expense",
            report_group="Compras Pagas",
            report_subgroup="Compras Pagas",
        )
        revenue_category = self._add_category(
            name="Receita loja",
            code="3.1.1.1",
            entry_kind="income",
            report_group="Receitas de Vendas",
            report_subgroup="Receitas de Vendas",
        )
        self._add_entry(account=account, category=purchase_category, entry_type="expense", total_amount="120.00")
        self._add_entry(account=account, category=revenue_category, entry_type="income", total_amount="500.00")

        custom_line = ReportConfigLine.model_validate(
            {
                "id": "linha-mista",
                "name": "Compras x Receitas",
                "order": 1,
                "line_type": "source",
                "operation": "add",
                "special_source": None,
                "category_groups": [
                    {"group_name": "group:Compras Pagas", "operation": "subtract"},
                    {"group_name": "group:Receitas de Vendas", "operation": "add"},
                ],
                "formula": [],
                "show_on_dashboard": False,
                "show_percent": True,
                "percent_mode": "grouped_children",
                "percent_reference_line_id": None,
                "is_active": True,
                "is_hidden": False,
                "summary_binding": "bank_revenue",
            }
        )
        update_report_config(self.db, self.company, "dro", ReportConfigUpdate(lines=[custom_line]))

        overview = build_reports_overview(self.db, self.company, start=date(2026, 3, 1), end=date(2026, 3, 31))
        mixed_node = next(node for node in overview.dro.statement if node.label == "Compras x Receitas")
        child_amounts = {child.label: child.amount for child in mixed_node.children}

        self.assertEqual(overview.dro.bank_revenue, Decimal("380.00"))
        self.assertEqual(mixed_node.amount, Decimal("380.00"))
        self.assertEqual(child_amounts["Compras Pagas"], Decimal("-120.00"))
        self.assertEqual(child_amounts["Receitas de Vendas"], Decimal("500.00"))


if __name__ == "__main__":
    unittest.main()
