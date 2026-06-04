from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models.banking import BankTransaction
from app.db.models.boleto import BoletoCustomerConfig, BoletoRecord, StandaloneBoletoRecord
from app.db.models.finance import Account, Category, FinancialEntry
from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxCustomer, LinxMovement, LinxOpenReceivable, SalesSnapshot
from app.db.models.security import Company
from app.services.bootstrap import ensure_company_catalog

LOCAL_DEMO_SOURCE = "local_demo_seed"
LOCAL_DEMO_BATCH_PREFIX = "local-demo-seed"


def _money(value: str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _today() -> datetime:
    return datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)


def _category(db: Session, company_id: str, name: str) -> Category:
    category = db.scalar(
        select(Category).where(
            Category.company_id == company_id,
            Category.name == name,
        )
    )
    if category is None:
        raise RuntimeError(f"Categoria local nao encontrada: {name}")
    return category


def _ensure_account(
    db: Session,
    company_id: str,
    *,
    name: str,
    account_type: str,
    opening_balance: Decimal,
    bank_code: str | None = None,
    exclude_from_balance: bool = False,
) -> Account:
    account = db.scalar(
        select(Account).where(
            Account.company_id == company_id,
            Account.name == name,
        )
    )
    if account is None:
        account = Account(
            company_id=company_id,
            name=name,
            account_type=account_type,
            bank_code=bank_code,
            opening_balance=opening_balance,
            is_active=True,
            exclude_from_balance=exclude_from_balance,
        )
        db.add(account)
    else:
        account.account_type = account_type
        account.bank_code = bank_code
        account.opening_balance = opening_balance
        account.is_active = True
        account.exclude_from_balance = exclude_from_balance
    db.flush()
    return account


def _create_batch(db: Session, company_id: str, source_type: str, filename: str) -> ImportBatch:
    batch = ImportBatch(
        company_id=company_id,
        source_type=source_type,
        filename=filename,
        fingerprint=f"{LOCAL_DEMO_BATCH_PREFIX}:{source_type}:{filename}",
        status="processed",
        records_total=0,
        records_valid=0,
        records_invalid=0,
    )
    db.add(batch)
    db.flush()
    return batch


def reset_local_demo_data(db: Session, company: Company) -> None:
    batch_ids = list(
        db.scalars(
            select(ImportBatch.id).where(
                ImportBatch.company_id == company.id,
                ImportBatch.fingerprint.like(f"{LOCAL_DEMO_BATCH_PREFIX}:%"),
            )
        )
    )
    if batch_ids:
        db.execute(delete(BoletoRecord).where(BoletoRecord.source_batch_id.in_(batch_ids)))
        db.execute(delete(StandaloneBoletoRecord).where(StandaloneBoletoRecord.source_batch_id.in_(batch_ids)))
        db.execute(delete(LinxOpenReceivable).where(LinxOpenReceivable.source_batch_id.in_(batch_ids)))
        db.execute(delete(LinxMovement).where(LinxMovement.source_batch_id.in_(batch_ids)))
        db.execute(delete(LinxCustomer).where(LinxCustomer.source_batch_id.in_(batch_ids)))
        db.execute(delete(SalesSnapshot).where(SalesSnapshot.source_batch_id.in_(batch_ids)))
        db.execute(delete(BankTransaction).where(BankTransaction.source_batch_id.in_(batch_ids)))
        db.execute(delete(ImportBatch).where(ImportBatch.id.in_(batch_ids)))

    db.execute(
        delete(FinancialEntry).where(
            FinancialEntry.company_id == company.id,
            FinancialEntry.source_system == LOCAL_DEMO_SOURCE,
        )
    )
    db.execute(
        delete(BoletoCustomerConfig).where(
            BoletoCustomerConfig.company_id == company.id,
            BoletoCustomerConfig.client_key.like("DEMO-%"),
        )
    )
    db.flush()


def _seed_financial_entries(
    db: Session,
    company: Company,
    *,
    checking: Account,
    cash: Account,
    card_receivables: Account,
) -> int:
    today = _today().date()
    categories = {
        "sales": _category(db, company.id, "Receitas Diversas Historicas"),
        "purchases": _category(db, company.id, "Compras"),
        "salary": _category(db, company.id, "Despesa Salarios"),
        "rent": _category(db, company.id, "Alugueis e Condominios"),
        "marketing": _category(db, company.id, "Publicidade e Propaganda"),
        "bank": _category(db, company.id, "Despesas Bancarias"),
        "software": _category(db, company.id, "Sistemas e Softwares"),
    }
    rows = [
        (
            "income",
            "settled",
            "Venda balcão - loja centro",
            "Cliente varejo",
            checking,
            categories["sales"],
            -16,
            "12450.00",
            "12450.00",
        ),
        (
            "income",
            "settled",
            "Recebimento PIX - campanha Dia das Maes",
            "Cliente PIX",
            checking,
            categories["sales"],
            -9,
            "8730.00",
            "8730.00",
        ),
        (
            "income",
            "open",
            "Venda a prazo - Cliente Demo 01",
            "Cliente Demo 01",
            card_receivables,
            categories["sales"],
            8,
            "4210.00",
            "0.00",
        ),
        (
            "income",
            "open",
            "Recebivel atrasado - Cliente Demo 02",
            "Cliente Demo 02",
            card_receivables,
            categories["sales"],
            -5,
            "1890.00",
            "0.00",
        ),
        (
            "expense",
            "settled",
            "Compra de mercadorias - Fornecedor Alpha",
            "Fornecedor Alpha",
            checking,
            categories["purchases"],
            -18,
            "6450.00",
            "6450.00",
        ),
        (
            "expense",
            "settled",
            "Tarifas bancarias",
            "Banco Demo",
            checking,
            categories["bank"],
            -4,
            "96.40",
            "96.40",
        ),
        (
            "expense",
            "open",
            "Aluguel loja centro",
            "Imobiliaria Demo",
            checking,
            categories["rent"],
            5,
            "3200.00",
            "0.00",
        ),
        (
            "expense",
            "open",
            "Folha parcial",
            "Equipe Demo",
            checking,
            categories["salary"],
            12,
            "7800.00",
            "0.00",
        ),
        (
            "expense",
            "open",
            "Publicidade digital",
            "Agencia Demo",
            checking,
            categories["marketing"],
            -3,
            "1450.00",
            "0.00",
        ),
        (
            "expense",
            "open",
            "Assinatura sistema de vendas",
            "SaaS Demo",
            cash,
            categories["software"],
            19,
            "620.00",
            "0.00",
        ),
    ]
    for index, row in enumerate(rows, start=1):
        entry_type, status, title, counterparty, account, category, due_offset, total, paid = row
        due_date = today + timedelta(days=due_offset)
        settled_at = (
            datetime.combine(due_date, datetime.min.time()) if status == "settled" else None
        )
        db.add(
            FinancialEntry(
                company_id=company.id,
                account_id=account.id,
                category_id=category.id,
                entry_type=entry_type,
                status=status,
                title=title,
                counterparty_name=counterparty,
                document_number=f"DEMO-FIN-{index:03d}",
                issue_date=due_date - timedelta(days=7),
                competence_date=due_date.replace(day=1),
                due_date=due_date,
                settled_at=settled_at,
                principal_amount=_money(total),
                total_amount=_money(total),
                paid_amount=_money(paid),
                external_source="local_demo",
                source_system=LOCAL_DEMO_SOURCE,
                source_reference=f"local-demo-financial-{index:03d}",
            )
        )
    return len(rows)


def _seed_sales_and_receivables(db: Session, company: Company) -> int:
    today = _today().date()
    sales_batch = _create_batch(db, company.id, "linx_sales", "local-demo-sales.csv")
    receivables_batch = _create_batch(
        db,
        company.id,
        "linx_receivables",
        "local-demo-receivables.csv",
    )
    customer_batch = _create_batch(db, company.id, "linx_customers", "local-demo-customers.csv")
    boleto_batch = _create_batch(db, company.id, "boletos", "local-demo-boletos.csv")

    for offset, gross, card, pix in [
        (-6, "5200.00", "3100.00", "1400.00"),
        (-5, "6100.00", "3500.00", "1700.00"),
        (-4, "4800.00", "2600.00", "1200.00"),
        (-3, "7350.00", "4200.00", "1900.00"),
        (-2, "6900.00", "3900.00", "2100.00"),
        (-1, "8100.00", "4700.00", "2400.00"),
        (0, "5620.00", "3300.00", "1500.00"),
    ]:
        db.add(
            SalesSnapshot(
                company_id=company.id,
                source_batch_id=sales_batch.id,
                snapshot_date=today + timedelta(days=offset),
                gross_revenue=_money(gross),
                cash_revenue=_money("450.00"),
                card_revenue=_money(card),
                pix_revenue=_money(pix),
                inhouse_credit_revenue=_money("350.00"),
                markup=Decimal("2.15"),
            )
        )

    customers = [
        ("DEMO-001", 9001, "Cliente Demo 01", today + timedelta(days=3), "3790.00"),
        ("DEMO-002", 9002, "Cliente Demo 02", today - timedelta(days=6), "1840.00"),
        ("DEMO-003", 9003, "Cliente Demo 03", today + timedelta(days=14), "2560.00"),
    ]
    for index, (client_key, linx_code, name, due_date, amount) in enumerate(customers, start=1):
        birth_date = today.replace(year=today.year - 34) + timedelta(days=index - 1)
        db.add(
            LinxCustomer(
                company_id=company.id,
                source_batch_id=customer_batch.id,
                last_seen_batch_id=customer_batch.id,
                portal=1,
                linx_code=linx_code,
                legal_name=name,
                display_name=name,
                document_number=f"0000000000{index}",
                birth_date=birth_date,
                person_type="F",
                city="Florianopolis",
                state="SC",
                mobile=f"4899999000{index}",
                email=f"cliente.demo.{index}@example.invalid",
            )
        )
        db.add(
            BoletoCustomerConfig(
                company_id=company.id,
                client_key=client_key,
                client_code=str(linx_code),
                client_name=name,
                uses_boleto=True,
                mode="individual",
                boleto_due_day=due_date.day,
                tax_id=f"0000000000{index}",
                city="Florianopolis",
                state="SC",
            )
        )
        db.add(
            LinxOpenReceivable(
                company_id=company.id,
                source_batch_id=receivables_batch.id,
                last_seen_batch_id=receivables_batch.id,
                portal=1,
                company_code=1,
                linx_code=70000 + index,
                customer_code=linx_code,
                customer_name=name,
                issue_date=datetime.combine(due_date - timedelta(days=20), datetime.min.time()),
                due_date=datetime.combine(due_date, datetime.min.time()),
                amount=_money(amount),
                paid_amount=_money("0.00"),
                document_number=f"NF-DEMO-{index:03d}",
                installment_number=1,
                installment_count=1,
                identifier=f"DEMO-REC-{index:03d}",
                payment_method_name="Boleto",
            )
        )
        db.add(
            BoletoRecord(
                company_id=company.id,
                source_batch_id=boleto_batch.id,
                bank="INTER",
                client_key=client_key,
                client_name=name,
                document_id=f"NF-DEMO-{index:03d}",
                issue_date=due_date - timedelta(days=20),
                due_date=due_date,
                payment_date=None,
                amount=_money(amount),
                paid_amount=_money("0.00"),
                status="EM_ABERTO",
                inter_seu_numero=f"DEMO-{index:03d}",
            )
        )

    db.add(
        StandaloneBoletoRecord(
            company_id=company.id,
            source_batch_id=boleto_batch.id,
            bank="INTER",
            client_key="DEMO-AVULSO",
            client_name="Cliente Avulso Demo",
            tax_id="00000000004",
            email="cliente.avulso@example.invalid",
            document_id="AVULSO-DEMO-001",
            issue_date=today,
            due_date=today + timedelta(days=10),
            amount=_money("980.00"),
            paid_amount=_money("0.00"),
            status="EM_ABERTO",
            local_status="open",
            description="Boleto avulso para teste local",
        )
    )

    for idx in range(1, 5):
        db.add(
            LinxMovement(
                company_id=company.id,
                source_batch_id=sales_batch.id,
                last_seen_batch_id=sales_batch.id,
                portal=1,
                company_code=1,
                linx_transaction=880000 + idx,
                document_number=f"VENDA-DEMO-{idx:03d}",
                identifier=f"DEMO-MOV-{idx:03d}",
                movement_group="sale",
                movement_type="sale",
                issue_date=datetime.combine(today - timedelta(days=idx), datetime.min.time()),
                launch_date=datetime.combine(today - timedelta(days=idx), datetime.min.time()),
                customer_code=9000 + idx,
                product_code=1000 + idx,
                quantity=Decimal("1.0000"),
                unit_price=_money("399.90"),
                net_amount=_money("399.90"),
                total_amount=_money("399.90"),
            )
        )

    sales_batch.records_total = 11
    sales_batch.records_valid = 11
    receivables_batch.records_total = 3
    receivables_batch.records_valid = 3
    customer_batch.records_total = 3
    customer_batch.records_valid = 3
    boleto_batch.records_total = 4
    boleto_batch.records_valid = 4
    return 25


def _seed_bank_transactions(db: Session, company: Company, account: Account) -> int:
    today = _today().date()
    batch = _create_batch(db, company.id, "ofx", "local-demo-ofx.ofx")
    rows = [
        (-2, "CREDIT", "Recebimento Stone", "DEMO-FIT-001", "3510.20"),
        (-1, "DEBIT", "Pagamento fornecedor pendente", "DEMO-FIT-002", "-1280.00"),
        (0, "DEBIT", "Tarifa pacote empresarial", "DEMO-FIT-003", "-79.90"),
    ]
    for offset, trn_type, memo, fit_id, amount in rows:
        db.add(
            BankTransaction(
                company_id=company.id,
                source_batch_id=batch.id,
                account_id=account.id,
                bank_name="Banco Demo",
                bank_code="999",
                posted_at=today + timedelta(days=offset),
                trn_type=trn_type,
                amount=_money(amount),
                fit_id=fit_id,
                memo=memo,
                name=memo,
            )
        )
    batch.records_total = len(rows)
    batch.records_valid = len(rows)
    return len(rows)


def seed_local_demo_data(db: Session, company: Company, *, reset: bool = True) -> dict[str, int]:
    if reset:
        reset_local_demo_data(db, company)

    ensure_company_catalog(db, company.id)
    checking = _ensure_account(
        db,
        company.id,
        name="Conta Corrente Demo",
        account_type="checking",
        bank_code="999",
        opening_balance=_money("28500.00"),
    )
    cash = _ensure_account(
        db,
        company.id,
        name="Caixa Loja Demo",
        account_type="cash",
        opening_balance=_money("2400.00"),
    )
    card_receivables = _ensure_account(
        db,
        company.id,
        name="Recebiveis Cartao Demo",
        account_type="receivables_control",
        opening_balance=_money("0.00"),
        exclude_from_balance=True,
    )

    financial_entries = _seed_financial_entries(
        db,
        company,
        checking=checking,
        cash=cash,
        card_receivables=card_receivables,
    )
    commercial_records = _seed_sales_and_receivables(db, company)
    bank_transactions = _seed_bank_transactions(db, company, checking)
    db.flush()

    return {
        "accounts": 3,
        "financial_entries": financial_entries,
        "commercial_records": commercial_records,
        "bank_transactions": bank_transactions,
        "total_financial_entries": db.scalar(
            select(func.count())
            .select_from(FinancialEntry)
            .where(
                FinancialEntry.company_id == company.id,
                FinancialEntry.source_system == LOCAL_DEMO_SOURCE,
            )
        ) or 0,
    }
