from __future__ import annotations

from datetime import date

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_text
from app.db.base import Base
from app.db.models.banking import BankTransaction
from app.db.models.finance import Account
from app.db.models.security import Company
from app.services.inter import sync_inter_statement


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _build_company_and_account(session: Session) -> tuple[Company, Account]:
    company = Company(legal_name="Empresa Teste Ltda", trade_name="Empresa Teste")
    session.add(company)
    session.flush()
    account = Account(
        company_id=company.id,
        name="Inter Matriz",
        account_type="checking",
        bank_code="077",
        account_number="123456",
        inter_api_enabled=True,
        inter_api_key="client-id",
        inter_account_number="123456",
        inter_client_secret_encrypted=encrypt_text("client-secret"),
        inter_certificate_pem_encrypted=encrypt_text("---CERT---"),
        inter_private_key_pem_encrypted=encrypt_text("---KEY---"),
        inter_api_base_url="https://example.test",
    )
    session.add(account)
    session.commit()
    return company, account


def test_sync_inter_statement_imports_scroll_pages_and_deduplicates_reimport() -> None:
    session = _build_session()
    token_calls = 0
    statement_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, statement_calls
        if request.url.path == "/oauth/v2/token":
            token_calls += 1
            return httpx.Response(200, json={"access_token": "token-123"})
        if request.url.path == "/banking/v2/extrato/completo":
            statement_calls += 1
            scroll_id = request.url.params.get("scrollId")
            if scroll_id == "next-1":
                return httpx.Response(
                    200,
                    json={
                        "transacoes": [
                            {
                                "idTransacao": "trx-002",
                                "dataTransacao": "2026-03-16",
                                "tipoTransacao": "TRANSFERENCIA",
                                "tipoOperacao": "CREDITO",
                                "valor": "99.90",
                                "titulo": "Recebimento",
                                "descricao": "Cliente XPTO",
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "transacoes": [
                        {
                            "idTransacao": "trx-001",
                            "dataTransacao": "2026-03-15",
                            "tipoTransacao": "PIX",
                            "tipoOperacao": "DEBITO",
                            "valor": "150.50",
                            "titulo": "Pagamento",
                            "descricao": "Fornecedor ABC",
                        }
                    ],
                    "scrollId": "next-1",
                },
            )
        raise AssertionError(f"Requisicao inesperada: {request.url}")

    try:
        company, account = _build_company_and_account(session)
        transport = httpx.MockTransport(handler)

        first_result = sync_inter_statement(
            session,
            company,
            account_id=account.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            transport=transport,
        )
        second_result = sync_inter_statement(
            session,
            company,
            account_id=account.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            transport=transport,
        )

        transactions = session.query(BankTransaction).order_by(BankTransaction.posted_at.asc()).all()
        assert [item.fit_id for item in transactions] == ["INTER:trx-001", "INTER:trx-002"]
        assert first_result.batch.records_valid == 2
        assert first_result.message == "Extrato do Inter sincronizado com sucesso."
        assert first_result.batch.source_type == "inter_statement"
        assert second_result.batch.records_valid == 0
        assert second_result.batch.records_invalid == 2
        assert "ja existiam" in (second_result.batch.error_summary or "")
        assert token_calls == 2
        assert statement_calls == 4
    finally:
        session.close()
