from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.banking import BankTransaction
from app.db.models.finance import Account
from app.db.models.imports import ImportBatch
from app.db.models.security import Company
from app.services.imports import import_ofx


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _build_company_and_account(
    session: Session,
    *,
    import_ofx_enabled: bool = True,
) -> tuple[Company, Account]:
    company = Company(
        legal_name="Empresa Teste Ltda",
        trade_name="Empresa Teste",
        default_currency="BRL",
    )
    session.add(company)
    session.flush()

    account = Account(
        company_id=company.id,
        name="Inter Conta Principal",
        account_type="checking",
        bank_code="077",
        branch_number="0001",
        account_number="12345678",
        opening_balance=Decimal("0.00"),
        is_active=True,
        import_ofx_enabled=import_ofx_enabled,
    )
    session.add(account)
    session.commit()
    return company, account


def _build_ofx(
    *,
    fit_id: str = "FIT-0001",
    amount: str = "-150.25",
    posted_at: str = "20260315",
    trn_type: str = "DEBIT",
    memo: str = "Pagamento fornecedor",
    name: str = "Fornecedor XPTO",
) -> bytes:
    return f"""
OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
  <SIGNONMSGSRSV1>
    <SONRS>
      <STATUS>
        <CODE>0
        <SEVERITY>INFO
      </STATUS>
      <DTSERVER>20260315120000[-3:BRT]
      <LANGUAGE>POR
      <FI>
        <ORG>Banco Inter
        <FID>077
      </FI>
    </SONRS>
  </SIGNONMSGSRSV1>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <TRNUID>1
      <STATUS>
        <CODE>0
        <SEVERITY>INFO
      </STATUS>
      <STMTRS>
        <CURDEF>BRL
        <BANKACCTFROM>
          <BANKID>077
          <BRANCHID>0001
          <ACCTID>12345678
          <ACCTTYPE>CHECKING
        </BANKACCTFROM>
        <BANKTRANLIST>
          <DTSTART>{posted_at}
          <DTEND>{posted_at}
          <STMTTRN>
            <TRNTYPE>{trn_type}
            <DTPOSTED>{posted_at}
            <TRNAMT>{amount}
            <FITID>{fit_id}
            <CHECKNUM>123
            <REFNUM>REF-{fit_id}
            <NAME>{name}
            <MEMO>{memo}
          </STMTTRN>
        </BANKTRANLIST>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>
""".strip().encode("latin1")


def test_import_ofx_persists_transactions_for_enabled_account() -> None:
    session = _build_session()
    try:
        company, account = _build_company_and_account(session)

        result = import_ofx(
            session,
            company,
            account.id,
            "extrato.ofx",
            _build_ofx(),
        )

        transaction = session.scalar(select(BankTransaction))
        assert transaction is not None
        assert transaction.account_id == account.id
        assert transaction.bank_name == "Banco Inter"
        assert transaction.bank_code == "077"
        assert transaction.fit_id == "FIT-0001"
        assert transaction.amount == Decimal("-150.25")
        assert transaction.memo == "Pagamento fornecedor"
        assert result.message == "OFX importado com sucesso."

        batch = session.get(ImportBatch, result.batch.id)
        assert batch is not None
        assert batch.source_type == f"ofx:{account.id}"
        assert batch.records_total == 1
        assert batch.records_valid == 1
        assert batch.records_invalid == 0
    finally:
        session.close()


def test_import_ofx_reuses_processed_batch_for_same_file() -> None:
    session = _build_session()
    try:
        company, account = _build_company_and_account(session)
        content = _build_ofx()

        first_result = import_ofx(session, company, account.id, "extrato.ofx", content)
        second_result = import_ofx(session, company, account.id, "extrato.ofx", content)

        assert first_result.batch.id == second_result.batch.id
        assert second_result.message == "Arquivo OFX ja importado anteriormente para esta conta."
        assert session.query(BankTransaction).count() == 1
        assert session.query(ImportBatch).count() == 1
    finally:
        session.close()


def test_import_ofx_marks_existing_fitid_as_duplicate_in_new_batch() -> None:
    session = _build_session()
    try:
        company, account = _build_company_and_account(session)

        import_ofx(session, company, account.id, "extrato-marco.ofx", _build_ofx(fit_id="FIT-REPETIDO"))
        second_result = import_ofx(
            session,
            company,
            account.id,
            "extrato-abril.ofx",
            _build_ofx(
                fit_id="FIT-REPETIDO",
                amount="-210.40",
                posted_at="20260410",
                memo="Mesmo FITID em arquivo novo",
            ),
        )

        assert session.query(BankTransaction).count() == 1
        batch = session.get(ImportBatch, second_result.batch.id)
        assert batch is not None
        assert batch.records_total == 1
        assert batch.records_valid == 0
        assert batch.records_invalid == 1
        assert batch.error_summary == "1 lancamentos ja existiam para esta conta."
    finally:
        session.close()


def test_import_ofx_rejects_disabled_account() -> None:
    session = _build_session()
    try:
        company, account = _build_company_and_account(session, import_ofx_enabled=False)

        with pytest.raises(ValueError, match="OFX nao esta habilitada"):
            import_ofx(session, company, account.id, "extrato.ofx", _build_ofx())

        assert session.query(BankTransaction).count() == 0
        assert session.query(ImportBatch).count() == 0
    finally:
        session.close()
