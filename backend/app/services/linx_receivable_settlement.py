from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html import escape
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models.linx import LinxOpenReceivable
from app.db.models.security import Company
from app.schemas.boletos import BoletoMatchItem, BoletoReceivableRead
from app.services.audit import write_audit_log
from app.services.boletos import build_boleto_dashboard
from app.services.linx import _load_linx_settings, _login_and_get_report_root, _require_playwright
from app.services.security_alerts import ensure_email_transport_configured, send_email

LINX_RECEIVABLE_SETTLEMENT_PATH = "financeiro/baixa_faturas.asp?tipolanc=receber"
LINX_RECEIVABLE_SETTLEMENT_MENU_SELECTOR = "a[data-endereco='financeiro/baixa_faturas.asp?tipolanc=receber']"
LINX_RECEIVABLE_SETTLEMENT_FRAME_NAME = "main"
LINX_RECEIVABLE_SETTLEMENT_PERMISSION_FRAME_SUFFIX = "mensagem-permissao.asp"
LINX_SETTLEMENT_INVOICE_SELECTORS = (
    "input[name='numero_fatura']",
    "input[name='fatura']",
    "input[name='numeroFatura']",
    "input[id='numero_fatura']",
    "input[id='fatura']",
    "input[id*='fatura']",
    "input[name*='fatura']",
)
LINX_SETTLEMENT_PROCEED_SELECTORS = (
    "button:has-text('Prosseguir')",
    "input[type='submit'][value*='Prosseguir']",
    "a:has-text('Prosseguir')",
)
LINX_SETTLEMENT_AMOUNT_SELECTORS = (
    "input[name='f_valor_pago']",
    "input[id='f_valor_pago']",
    "input[name='valor_pago']",
    "input[name='valorPago']",
    "input[id='valor_pago']",
    "input[id='valorPago']",
    "input[id*='valor_pago']",
    "input[name*='valor_pago']",
    "input[id*='valorPago']",
    "input[name*='valorPago']",
    "span:has-text('Valor Pago')",
    "label:has-text('Valor Pago')",
)
LINX_SETTLEMENT_INVOICE_AMOUNT_SELECTORS = (
    "input[name='f_valorfatura']",
    "input[id='f_valorfatura']",
    "input[name*='valorfatura']",
    "input[id*='valorfatura']",
    "span:has-text('Valor da Fatura')",
    "label:has-text('Valor da Fatura')",
)
LINX_SETTLEMENT_INTEREST_SELECTORS = (
    "input[name='f_juros']",
    "input[id='f_juros']",
    "input[name*='juros']",
    "input[id*='juros']",
)
LINX_SETTLEMENT_PENALTY_SELECTORS = (
    "input[name='f_multa']",
    "input[id='f_multa']",
    "input[name*='multa']",
    "input[id*='multa']",
)
LINX_SETTLEMENT_CLIENT_SELECTORS = (
    "input[name='cliente']",
    "input[name='cliente_fornecedor']",
    "input[name='clienteFornecedor']",
    "input[id='cliente']",
    "input[id='cliente_fornecedor']",
    "input[id='clienteFornecedor']",
    "input[id*='cliente']",
    "input[name*='cliente']",
    "span:has-text('Cliente')",
    "label:has-text('Cliente')",
    "span:has-text('Cliente/Fornecedor')",
    "label:has-text('Cliente/Fornecedor')",
)
LINX_SETTLEMENT_DUE_DATE_SELECTORS = (
    "input[name='data_vencimento']",
    "input[name='dataVencimento']",
    "input[id='data_vencimento']",
    "input[id='dataVencimento']",
    "input[id*='venc']",
    "input[name*='venc']",
    "span:has-text('Vencimento')",
    "label:has-text('Vencimento')",
)
LINX_SETTLEMENT_CONFIRM_SELECTORS = (
    "button:has-text('Confirmar baixa')",
    "input[type='submit'][value*='Confirmar baixa']",
    "input[type='submit'][value*='Confirma Baixa']",
    "a:has-text('Confirmar baixa')",
)
LINX_SETTLEMENT_RATEIO_SELECTORS = (
    "input[type='button'][value*='Confirmar baixa e rateio']",
    "input[type='button'][value*='Confirmar rateio']",
    "button:has-text('Confirmar baixa e rateio')",
    "button:has-text('Confirmar rateio')",
    "input[type='submit'][value*='Confirmar baixa e rateio']",
    "input[type='submit'][value*='Confirmar rateio']",
)
LINX_SETTLEMENT_SUCCESS_KEYWORDS = (
    "FOI BAIXADA COM SUCESSO",
    "JA FOI BAIXADA",
    "JA ESTA BAIXADA",
)
LINX_SETTLEMENT_PREVIOUS_OPEN_WARNING = "EXISTE(M) FATURA(S) EM ABERTO DESTE CLIENTE COM VENCIMENTO ANTERIOR A ESTA"


@dataclass(frozen=True)
class LinxSettlementCandidate:
    client_name: str
    boleto_amount: Decimal
    boleto_due_dates: tuple[date, ...]
    payment_dates: tuple[date, ...]
    invoice_numbers: tuple[str, ...]
    charge_codes: tuple[str, ...]
    receivables: tuple[BoletoReceivableRead, ...]


@dataclass(frozen=True)
class LinxSettlementInvoiceResult:
    client_name: str
    boleto_amount: Decimal
    boleto_due_dates: tuple[date, ...]
    payment_dates: tuple[date, ...]
    invoice_number: str
    due_date: date | None
    amount: Decimal
    success: bool
    message: str
    group_token: str = ""


@dataclass(frozen=True)
class LinxSettlementSummary:
    attempted_invoice_count: int
    settled_invoice_count: int
    failed_invoice_count: int
    client_count: int
    validate_only: bool = False
    email_error: str | None = None
    failure_messages: tuple[str, ...] = ()
    empty_scope_phrase: str = "do Inter"

    @property
    def message(self) -> str:
        if self.attempted_invoice_count == 0:
            return f"Nenhuma fatura paga sem baixa {self.empty_scope_phrase} encontrada para baixar no Linx."
        if self.validate_only:
            return (
                "Validacao automatica no Linx concluida. "
                f"{self.settled_invoice_count} fatura(s) validada(s) de {self.client_count} cliente(s)."
            )
        message = (
            "Baixa automatica no Linx concluida. "
            f"{self.settled_invoice_count} fatura(s) baixada(s) de {self.client_count} cliente(s)."
        )
        if self.failed_invoice_count:
            message += f" {self.failed_invoice_count} fatura(s) falharam na baixa."
        if self.email_error:
            message += " O resumo por email nao foi enviado."
        return message


def settle_paid_pending_inter_receivables(
    db: Session,
    company: Company,
    *,
    filter_charge_codes: set[str] | None = None,
    filter_banks: set[str] | None = None,
    validate_only: bool = False,
) -> LinxSettlementSummary:
    normalized_filter_banks = _normalize_bank_filters(filter_banks)
    empty_scope_phrase = _build_empty_scope_phrase(normalized_filter_banks)
    dashboard = build_boleto_dashboard(db, company, include_all_monthly_missing=True)
    candidates, precheck_failures = _build_settlement_candidates(
        dashboard.paid_pending,
        filter_charge_codes=filter_charge_codes,
        filter_banks=normalized_filter_banks,
    )
    if not candidates and not precheck_failures:
        return LinxSettlementSummary(
            attempted_invoice_count=0,
            settled_invoice_count=0,
            failed_invoice_count=0,
            client_count=0,
            validate_only=validate_only,
            empty_scope_phrase=empty_scope_phrase,
        )

    results = [*precheck_failures]
    if candidates:
        results.extend(_settle_candidates_in_portal(company, candidates, validate_only=validate_only))
    settled_results = [item for item in results if item.success]
    failed_results = [item for item in results if not item.success]

    settled_client_names = {item.client_name for item in settled_results}
    if not validate_only:
        for result in settled_results:
            _remove_open_receivable_from_local_dashboard(db, company_id=company.id, invoice_number=result.invoice_number)

    email_error: str | None = None
    if results and not validate_only:
        subject, body, html_body = _build_success_email(company, results)
        try:
            ensure_email_transport_configured()
            send_email(
                subject,
                body,
                recipients=_split_recipients(company.linx_auto_sync_alert_email),
                html_body=html_body,
            )
        except Exception as error:  # pragma: no cover
            email_error = str(error)

    write_audit_log(
        db,
        action="linx_receivable_auto_settlement",
        entity_name="company",
        entity_id=company.id,
        company_id=company.id,
        after_state={
            "validate_only": validate_only,
            "attempted_invoice_count": len(results),
            "settled_invoice_count": len(settled_results),
            "failed_invoice_count": len(failed_results),
            "client_count": len(settled_client_names),
            "email_error": email_error,
            "failures": [item.message for item in failed_results],
        },
    )
    db.flush()

    return LinxSettlementSummary(
        attempted_invoice_count=len(results),
        settled_invoice_count=len(settled_results),
        failed_invoice_count=len(failed_results),
        client_count=len(settled_client_names),
        validate_only=validate_only,
        email_error=email_error,
        failure_messages=tuple(item.message for item in failed_results),
        empty_scope_phrase=empty_scope_phrase,
    )


def _build_settlement_candidates(
    items: list[BoletoMatchItem],
    *,
    filter_charge_codes: set[str] | None,
    filter_banks: set[str] | None,
) -> tuple[list[LinxSettlementCandidate], list[LinxSettlementInvoiceResult]]:
    normalized_filter_codes = {item.strip() for item in (filter_charge_codes or set()) if item and item.strip()}
    candidates: list[LinxSettlementCandidate] = []
    failures: list[LinxSettlementInvoiceResult] = []
    for item in items:
        bank = (item.bank or "").strip().upper()
        if not bank:
            continue
        if filter_banks and bank not in filter_banks:
            continue
        charge_codes = ()
        if bank == "INTER":
            charge_codes = tuple(
                code
                for code in {
                    (boleto.inter_codigo_solicitacao or "").strip()
                    for boleto in item.boletos
                }
                if code
            )
        if normalized_filter_codes and (bank != "INTER" or not (set(charge_codes) & normalized_filter_codes)):
            continue
        receivables = tuple(sorted(item.receivables, key=_receivable_sort_key))
        if not receivables:
            continue
        duplicate_amounts = _find_duplicate_receivable_amounts(receivables)
        boleto_due_dates = tuple(sorted({boleto.due_date for boleto in item.boletos if boleto.due_date is not None}))
        payment_dates = tuple(sorted({boleto.payment_date for boleto in item.boletos if boleto.payment_date is not None}))
        boleto_amount = sum(
            (
                Decimal(boleto.paid_amount or 0) if Decimal(boleto.paid_amount or 0) > 0 else Decimal(boleto.amount or 0)
                for boleto in item.boletos
            ),
            Decimal("0"),
        )
        if duplicate_amounts:
            duplicate_labels = ", ".join(_format_brl(amount) for amount in duplicate_amounts)
            invoices = ", ".join(receivable.invoice_number for receivable in receivables)
            message = (
                "Validacao de seguranca bloqueou a baixa automatica: "
                f"o cliente possui mais de uma fatura com o mesmo valor ({duplicate_labels}) "
                f"no mesmo pagamento ({invoices})."
            )
            for receivable in receivables:
                failures.append(
                    LinxSettlementInvoiceResult(
                        client_name=item.client_name,
                        boleto_amount=boleto_amount.quantize(Decimal("0.01")),
                        boleto_due_dates=boleto_due_dates,
                        payment_dates=payment_dates,
                        invoice_number=receivable.invoice_number,
                        due_date=receivable.due_date,
                        amount=Decimal(receivable.amount or 0).quantize(Decimal("0.01")),
                        success=False,
                        message=message,
                        group_token="|".join([*charge_codes, *(current.invoice_number for current in receivables)]),
                    )
                )
            continue
        candidates.append(
            LinxSettlementCandidate(
                client_name=item.client_name,
                boleto_amount=boleto_amount.quantize(Decimal("0.01")),
                boleto_due_dates=boleto_due_dates,
                payment_dates=payment_dates,
                invoice_numbers=tuple(receivable.invoice_number for receivable in receivables),
                charge_codes=charge_codes,
                receivables=receivables,
            )
        )
    candidates.sort(key=_candidate_sort_key)
    return candidates, failures


def _normalize_bank_filters(filter_banks: set[str] | None) -> set[str]:
    normalized = {(item or "").strip().upper() for item in (filter_banks or {"INTER"})}
    normalized.discard("")
    return normalized or {"INTER"}


def _build_empty_scope_phrase(filter_banks: set[str]) -> str:
    if filter_banks == {"INTER"}:
        return "do Inter"
    if filter_banks == {"C6"}:
        return "do C6"
    return "dos boletos selecionados"


def _settle_candidates_in_portal(
    company: Company,
    candidates: list[LinxSettlementCandidate],
    *,
    validate_only: bool = False,
) -> list[LinxSettlementInvoiceResult]:
    settings = _load_linx_settings(company)
    sync_playwright, timeout_error_cls = _require_playwright()
    results: list[LinxSettlementInvoiceResult] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        context = browser.new_context()
        page = context.new_page()
        _install_dialog_auto_accept(page)
        page.set_default_timeout(settings.timeout_ms)
        try:
            root_url = _login_and_get_report_root(page, settings, timeout_error_cls)
            for candidate in candidates:
                group_token = "|".join([*candidate.charge_codes, *candidate.invoice_numbers])
                for receivable in candidate.receivables:
                    amount = Decimal(receivable.amount or 0).quantize(Decimal("0.01"))
                    try:
                        confirmation = _settle_receivable_in_portal(
                            page,
                            root_url=root_url,
                            invoice_number=receivable.invoice_number,
                            expected_client_name=candidate.client_name,
                            expected_due_date=receivable.due_date,
                            expected_amount=amount,
                            validate_only=validate_only,
                        )
                    except Exception as error:
                        results.append(
                            LinxSettlementInvoiceResult(
                                client_name=candidate.client_name,
                                boleto_amount=candidate.boleto_amount,
                                boleto_due_dates=candidate.boleto_due_dates,
                                payment_dates=candidate.payment_dates,
                                group_token=group_token,
                                invoice_number=receivable.invoice_number,
                                due_date=receivable.due_date,
                                amount=amount,
                                success=False,
                                message=str(error),
                            )
                        )
                        continue

                    results.append(
                        LinxSettlementInvoiceResult(
                            client_name=candidate.client_name,
                            boleto_amount=candidate.boleto_amount,
                            boleto_due_dates=candidate.boleto_due_dates,
                            payment_dates=candidate.payment_dates,
                            group_token=group_token,
                            invoice_number=receivable.invoice_number,
                            due_date=receivable.due_date,
                            amount=amount,
                            success=True,
                            message=confirmation,
                        )
                    )
        finally:
            context.close()
            browser.close()
    return results


def _settle_receivable_in_portal(
    page: Any,
    *,
    root_url: str,
    invoice_number: str,
    expected_client_name: str,
    expected_due_date: date | None,
    expected_amount: Decimal,
    validate_only: bool = False,
) -> str:
    lookup_invoice = _build_lookup_invoice_number(invoice_number)
    target = _open_receivable_settlement_target(page, root_url=root_url)
    target = _prepare_receivable_lookup_target(
        page,
        root_url=root_url,
        target=target,
        lookup_invoice=lookup_invoice,
    )
    _click_first_matching_locator(target, LINX_SETTLEMENT_PROCEED_SELECTORS)
    _wait_for_page_idle(target)
    _wait_for_transition(page)
    target = _current_receivable_settlement_target(page, fallback=target)

    _validate_receivable_confirmation_context(
        target,
        invoice_number=lookup_invoice,
        expected_client_name=expected_client_name,
        expected_due_date=expected_due_date,
        expected_amount=expected_amount,
    )

    _normalize_confirmation_amount_fields(target)

    # Revalida o valor imediatamente antes da confirmacao para evitar baixa com tela alterada.
    paid_amount = _extract_paid_amount(target)
    if paid_amount is None:
        raise ValueError(f"Nao foi possivel ler o 'Valor Pago (R$)' da fatura {lookup_invoice} no Linx.")
    if paid_amount != expected_amount.quantize(Decimal("0.01")):
        raise ValueError(
            f"Valor pago divergente para a fatura {lookup_invoice}: esperado { _format_brl(expected_amount) }, "
            f"mas o Linx exibiu { _format_brl(paid_amount) }."
        )
    if validate_only:
        return (
            f"Double-check validado para a fatura {lookup_invoice} "
            f"sem confirmar a baixa no Linx."
        )

    _click_first_matching_locator(target, LINX_SETTLEMENT_CONFIRM_SELECTORS)
    _wait_for_page_idle(target)
    _wait_for_transition(page)
    target = _current_receivable_settlement_target(page, fallback=target)
    _click_first_matching_locator(target, LINX_SETTLEMENT_RATEIO_SELECTORS, required=False)
    _wait_for_page_idle(target)
    _wait_for_transition(page)
    target = _current_receivable_settlement_target(page, fallback=target)

    success_message = _extract_success_message(target, lookup_invoice)
    if not success_message:
        raise ValueError(f"O Linx nao confirmou a baixa da fatura {lookup_invoice}.")
    return success_message


def _prepare_receivable_lookup_target(
    page: Any,
    *,
    root_url: str,
    target: Any,
    lookup_invoice: str,
) -> Any:
    try:
        _fill_first_matching_locator(target, LINX_SETTLEMENT_INVOICE_SELECTORS, lookup_invoice)
        return target
    except ValueError as error:
        if "Numero da fatura" not in str(error):
            raise
    try:
        page.wait_for_timeout(800)
    except Exception:
        pass
    retried_target = _open_receivable_settlement_target(page, root_url=root_url)
    _fill_first_matching_locator(retried_target, LINX_SETTLEMENT_INVOICE_SELECTORS, lookup_invoice)
    return retried_target


def _open_receivable_settlement_target(page: Any, *, root_url: str) -> Any:
    direct_url = f"{root_url}/gestor_web/{LINX_RECEIVABLE_SETTLEMENT_PATH}"
    try:
        page.goto(direct_url, wait_until="domcontentloaded")
    except Exception:
        pass
    else:
        try:
            page.wait_for_timeout(1_000)
        except Exception:
            pass
        _wait_for_page_idle(page)
        _raise_if_permission_denied(page)
        if _find_first_locator(page, LINX_SETTLEMENT_INVOICE_SELECTORS) is not None:
            return page

    try:
        page.goto(f"{root_url}/v4/home/index.asp", wait_until="domcontentloaded")
    except Exception:
        pass
    menu_locator = page.locator(LINX_RECEIVABLE_SETTLEMENT_MENU_SELECTOR).first
    try:
        menu_locator.evaluate("el => el.click()")
    except Exception as error:
        raise ValueError("Nao foi possivel abrir o menu 'Baixa de Faturas' no Linx.") from error
    try:
        page.wait_for_timeout(2_000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle")
    except Exception:
        pass
    frame = _current_receivable_settlement_target(page)
    if frame is None:
        raise ValueError("O Linx nao abriu o iframe principal da tela de baixa de faturas.")
    _wait_for_page_idle(frame)
    _raise_if_permission_denied(frame)
    return frame


def _current_receivable_settlement_target(page: Any, *, fallback: Any | None = None) -> Any | None:
    frame = page.frame(name=LINX_RECEIVABLE_SETTLEMENT_FRAME_NAME)
    return frame if frame is not None else fallback


def _raise_if_permission_denied(target: Any) -> None:
    target_url = ""
    try:
        target_url = str(target.url or "")
    except Exception:
        target_url = ""
    if target_url.endswith(LINX_RECEIVABLE_SETTLEMENT_PERMISSION_FRAME_SUFFIX):
        raise ValueError("O usuario configurado no Linx nao possui permissao para 'Baixa de faturas'.")

    permission_payload = _read_first_matching_locator_value(target, "#objetoRetorno")
    if (
        "POSSUIPERMISSAO\":FALSE" in permission_payload.upper()
        or "\"POSSUIPERMISSAO\":FALSE" in permission_payload.upper()
    ):
        raise ValueError("O usuario configurado no Linx nao possui permissao para 'Baixa de faturas'.")


def _validate_receivable_confirmation_context(
    page: Any,
    *,
    invoice_number: str,
    expected_client_name: str,
    expected_due_date: date | None,
    expected_amount: Decimal,
) -> None:
    body_text = _read_body_text(page)
    normalized_body = _normalize_text(body_text)

    if not _page_mentions_invoice(page, invoice_number=invoice_number, normalized_body=normalized_body):
        raise ValueError(
            f"Double-check falhou para a fatura {invoice_number}: o numero da fatura nao apareceu de forma confiavel na tela do Linx."
        )

    invoice_amount = _extract_invoice_amount(page)
    if invoice_amount is None:
        raise ValueError(
            f"Double-check falhou para a fatura {invoice_number}: nao foi possivel ler o valor da fatura na tela do Linx."
        )
    normalized_expected_amount = expected_amount.quantize(Decimal("0.01"))
    if invoice_amount != normalized_expected_amount:
        raise ValueError(
            f"Double-check falhou para a fatura {invoice_number}: valor esperado { _format_brl(normalized_expected_amount) }, "
            f"mas o Linx exibiu { _format_brl(invoice_amount) }."
        )

    if not _page_matches_client_name(page, expected_client_name=expected_client_name, normalized_body=normalized_body):
        raise ValueError(
            f"Double-check falhou para a fatura {invoice_number}: o cliente exibido no Linx nao confere com '{expected_client_name}'."
        )

    if expected_due_date is not None and not _page_matches_due_date(
        page,
        expected_due_date=expected_due_date,
        normalized_body=normalized_body,
    ):
        raise ValueError(
            f"Double-check falhou para a fatura {invoice_number}: o vencimento exibido no Linx nao confere com {expected_due_date.strftime('%d/%m/%Y')}."
        )


def _fill_first_matching_locator(page: Any, selectors: tuple[str, ...], value: str) -> None:
    locator = _find_first_locator(page, selectors)
    if locator is None:
        raise ValueError("Nao foi possivel localizar o campo 'Numero da fatura' no Linx.")
    locator.fill(value)


def _click_first_matching_locator(page: Any, selectors: tuple[str, ...], *, required: bool = True) -> bool:
    locator = _find_first_locator(page, selectors)
    if locator is None:
        if required:
            raise ValueError("Nao foi possivel localizar a acao esperada no Linx.")
        return False
    locator.click()
    return True


def _find_first_locator(page: Any, selectors: tuple[str, ...]) -> Any | None:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:
            count = 0
        if count:
            first = getattr(locator, "first", None)
            return first if first is not None else locator
    return None


def _wait_for_page_idle(page: Any) -> None:
    try:
        page.wait_for_load_state("networkidle")
    except Exception:
        return


def _wait_for_transition(page: Any) -> None:
    try:
        page.wait_for_timeout(1_000)
    except Exception:
        return


def _extract_paid_amount(page: Any) -> Decimal | None:
    for selector in LINX_SETTLEMENT_AMOUNT_SELECTORS:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:
            count = 0
        if not count:
            continue
        target = getattr(locator, "first", None) or locator
        raw_value = ""
        for reader in ("input_value", "inner_text", "text_content"):
            if not hasattr(target, reader):
                continue
            try:
                raw_value = getattr(target, reader)() or ""
            except Exception:
                raw_value = ""
            if raw_value:
                break
        amount = _parse_brl_amount(raw_value)
        if amount is not None:
            return amount

    body_text = _read_body_text(page)
    amount = _parse_brl_amount(_extract_value_paid_snippet(body_text))
    if amount is not None:
        return amount
    return None


def _extract_invoice_amount(page: Any) -> Decimal | None:
    for selector in LINX_SETTLEMENT_INVOICE_AMOUNT_SELECTORS:
        value = _read_first_matching_locator_value(page, selector)
        amount = _parse_brl_amount(value)
        if amount is not None:
            return amount

    body_text = _read_body_text(page)
    amount = _parse_brl_amount(_extract_invoice_amount_snippet(body_text))
    if amount is not None:
        return amount
    return None


def _normalize_confirmation_amount_fields(page: Any) -> None:
    _overwrite_first_matching_amount(page, LINX_SETTLEMENT_INTEREST_SELECTORS, Decimal("0.00"))
    _overwrite_first_matching_amount(page, LINX_SETTLEMENT_PENALTY_SELECTORS, Decimal("0.00"))


def _overwrite_first_matching_amount(page: Any, selectors: tuple[str, ...], amount: Decimal) -> bool:
    locator = _find_first_locator(page, selectors)
    if locator is None:
        return False
    formatted_amount = _format_decimal_for_linx(amount)
    try:
        locator.fill(formatted_amount)
    except Exception:
        return False
    try:
        locator.blur()
    except Exception:
        pass
    try:
        page.wait_for_timeout(300)
    except Exception:
        pass
    _wait_for_page_idle(page)
    return True


def _page_mentions_invoice(page: Any, *, invoice_number: str, normalized_body: str) -> bool:
    if invoice_number and invoice_number in normalized_body:
        return True
    for selector in LINX_SETTLEMENT_INVOICE_SELECTORS:
        value = _read_first_matching_locator_value(page, selector)
        if not value:
            continue
        if _build_lookup_invoice_number(value) == invoice_number:
            return True
    invoice_patterns = (
        rf"NUMERO\s+DA\s+FATURA\s*:?\s*{re.escape(invoice_number)}",
        rf"NUMERO\s+DA\s+FATURA\s*/\s*EMPRESA\s*:?\s*{re.escape(invoice_number)}(?:\s*/\s*\d+)?",
        rf"NUMERO\s+DA\s+FATURA/EMPRESA\s*:?\s*{re.escape(invoice_number)}(?:\s*/\s*\d+)?",
        rf"FATURA\s*:?\s*{re.escape(invoice_number)}",
    )
    return any(re.search(pattern, normalized_body, flags=re.IGNORECASE) for pattern in invoice_patterns)


def _install_dialog_auto_accept(page: Any) -> None:
    if not hasattr(page, "on"):
        return

    def _handle_dialog(dialog: Any) -> None:
        try:
            dialog.accept()
        except Exception:
            return

    try:
        page.on("dialog", _handle_dialog)
    except Exception:
        return


def _page_matches_client_name(page: Any, *, expected_client_name: str, normalized_body: str) -> bool:
    normalized_expected = _normalize_text(expected_client_name)
    if not normalized_expected:
        return False
    if normalized_expected in normalized_body:
        return True
    for selector in LINX_SETTLEMENT_CLIENT_SELECTORS:
        value = _read_first_matching_locator_value(page, selector)
        if not value:
            continue
        if _normalize_text(value) == normalized_expected:
            return True
    extracted = _extract_client_snippet(normalized_body)
    if extracted and _client_names_match(normalized_expected, extracted):
        return True
    return False


def _page_matches_due_date(page: Any, *, expected_due_date: date, normalized_body: str) -> bool:
    expected_display = expected_due_date.strftime("%d/%m/%Y")
    if expected_display in normalized_body:
        return True
    for selector in LINX_SETTLEMENT_DUE_DATE_SELECTORS:
        value = _read_first_matching_locator_value(page, selector)
        if not value:
            continue
        parsed = _parse_br_date_from_text(value)
        if parsed == expected_due_date:
            return True
    extracted = _extract_due_date_snippet(normalized_body)
    if extracted == expected_due_date:
        return True
    return False


def _read_first_matching_locator_value(page: Any, selector: str) -> str:
    locator = page.locator(selector)
    try:
        count = locator.count()
    except Exception:
        return ""
    if not count:
        return ""
    target = getattr(locator, "first", None) or locator
    for reader in ("input_value", "inner_text", "text_content"):
        if not hasattr(target, reader):
            continue
        try:
            value = getattr(target, reader)() or ""
        except Exception:
            value = ""
        if value:
            return value
    return ""


def _extract_client_snippet(normalized_body: str) -> str:
    match = re.search(
        r"(?:CLIENTE|CLIENTE/FORNECEDOR)\s*:?\s*([A-Z0-9\s]+?)(?:VALOR\s+PAGO|VENCIMENTO|DATA\s+DE\s+VENCIMENTO|$)",
        normalized_body,
        flags=re.IGNORECASE,
    )
    if match is None:
        return ""
    return " ".join(match.group(1).split())


def _extract_due_date_snippet(normalized_body: str) -> date | None:
    match = re.search(
        r"(?:VENCIMENTO|DATA\s+DE\s+VENCIMENTO)\s*:?\s*(\d{2}/\d{2}/\d{4})",
        normalized_body,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return _parse_br_date_from_text(match.group(1))


def _parse_br_date_from_text(value: str | None) -> date | None:
    text = (value or "").strip()
    match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    if match is None:
        return None
    try:
        return date.fromisoformat(
            f"{match.group(1)[6:10]}-{match.group(1)[3:5]}-{match.group(1)[0:2]}"
        )
    except ValueError:
        return None


def _client_names_match(expected: str, actual: str) -> bool:
    expected_tokens = {token for token in expected.split() if len(token) >= 3}
    actual_tokens = {token for token in actual.split() if len(token) >= 3}
    if not expected_tokens or not actual_tokens:
        return False
    common_tokens = expected_tokens & actual_tokens
    return expected_tokens.issubset(actual_tokens) or len(common_tokens) >= min(3, len(expected_tokens))


def _extract_success_message(page: Any, invoice_number: str) -> str | None:
    body_text = _read_body_text(page)
    normalized_body = _normalize_text(body_text)
    if not any(keyword in normalized_body for keyword in LINX_SETTLEMENT_SUCCESS_KEYWORDS):
        return None
    invoice_pattern = re.escape(invoice_number)
    message_match = re.search(
        rf"(A\s+FATURA\s+{invoice_pattern}.*?(?:FOI BAIXADA COM SUCESSO|JA FOI BAIXADA|JA ESTA BAIXADA)\.?)",
        normalized_body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if message_match:
        return " ".join(message_match.group(1).split())
    return f"A fatura {invoice_number} foi baixada com sucesso."


def _read_body_text(page: Any) -> str:
    try:
        return page.locator("body").inner_text()
    except Exception:
        return ""


def _extract_value_paid_snippet(body_text: str) -> str:
    match = re.search(
        r"VALOR\s+PAGO\s*\(R\$\)\s*:?\s*([0-9\.\,]+)",
        _normalize_text(body_text),
        flags=re.IGNORECASE,
    )
    if match is None:
        return ""
    return match.group(1)


def _extract_invoice_amount_snippet(body_text: str) -> str:
    match = re.search(
        r"VALOR\s+DA\s+FATURA\s*:?\s*(?:R\$\s*)?([0-9\.\,]+)",
        _normalize_text(body_text),
        flags=re.IGNORECASE,
    )
    if match is None:
        return ""
    return match.group(1)


def _parse_brl_amount(raw_value: str | None) -> Decimal | None:
    text = (raw_value or "").strip()
    if not text:
        return None
    match = re.search(r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}|\d+\.\d{1,2}|\d+)", text)
    normalized = match.group(1) if match else text
    normalized = normalized.replace("R$", "").replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", normalized):
        normalized = normalized.replace(".", "")
    try:
        return Decimal(normalized).quantize(Decimal("0.01"))
    except Exception:
        return None


def _format_decimal_for_linx(value: Decimal) -> str:
    normalized = Decimal(value or 0).quantize(Decimal("0.01"))
    return f"{normalized:.2f}".replace(".", ",")


def _candidate_sort_key(candidate: LinxSettlementCandidate) -> tuple[str, date, str]:
    return (
        _normalize_text(candidate.client_name),
        min((receivable.due_date or date.max) for receivable in candidate.receivables),
        candidate.invoice_numbers[0] if candidate.invoice_numbers else "",
    )


def _receivable_sort_key(receivable: BoletoReceivableRead) -> tuple[date, str]:
    return (
        receivable.due_date or date.max,
        _build_lookup_invoice_number(receivable.invoice_number),
    )


def _build_lookup_invoice_number(invoice_number: str) -> str:
    raw_value = (invoice_number or "").strip()
    if not raw_value:
        return raw_value
    first_segment = raw_value.split("/", 1)[0].strip()
    digits = re.sub(r"\D+", "", first_segment)
    if digits:
        return digits
    return first_segment or raw_value


def _remove_open_receivable_from_local_dashboard(db: Session, *, company_id: str, invoice_number: str) -> None:
    lookup_invoice = _build_lookup_invoice_number(invoice_number)
    if not lookup_invoice.isdigit():
        return
    db.execute(
        delete(LinxOpenReceivable).where(
            LinxOpenReceivable.company_id == company_id,
            LinxOpenReceivable.linx_code == int(lookup_invoice),
        )
    )


def _format_dates_for_email(values: tuple[date, ...]) -> str:
    if not values:
        return "-"
    return ", ".join(item.strftime("%d/%m/%Y") for item in values)


def _find_duplicate_receivable_amounts(receivables: tuple[BoletoReceivableRead, ...]) -> tuple[Decimal, ...]:
    counts: dict[Decimal, int] = {}
    for receivable in receivables:
        amount = Decimal(receivable.amount or 0).quantize(Decimal("0.01"))
        counts[amount] = counts.get(amount, 0) + 1
    return tuple(sorted((amount for amount, count in counts.items() if count > 1), key=lambda item: (item,)))


def _build_success_email(
    company: Company,
    results: list[LinxSettlementInvoiceResult],
) -> tuple[str, str, str]:
    settled_results = [item for item in results if item.success]
    company_name = company.trade_name or company.legal_name or company.id
    subject = f"[Linx] Baixa automatica de faturas - {company_name}"

    grouped: dict[tuple[str, str, str, str, str], list[LinxSettlementInvoiceResult]] = {}
    for result in settled_results:
        grouped.setdefault(
            (
                result.client_name,
                _format_brl(result.boleto_amount),
                _format_dates_for_email(result.boleto_due_dates),
                _format_dates_for_email(result.payment_dates),
                result.group_token,
            ),
            [],
        ).append(result)

    lines: list[str] = []
    html_sections: list[str] = []
    total_settled = 0
    total_settled_amount = Decimal("0.00")
    client_totals: dict[str, tuple[int, Decimal]] = {}
    for (client_name, boleto_amount, boleto_due_dates, payment_dates, _group_token), client_results in grouped.items():
        invoice_numbers = ", ".join(result.invoice_number for result in client_results)
        client_total_amount = sum((Decimal(result.amount or 0) for result in client_results), Decimal("0.00"))
        total_settled += len(client_results)
        total_settled_amount += client_total_amount
        current_count, current_amount = client_totals.get(client_name, (0, Decimal("0.00")))
        client_totals[client_name] = (
            current_count + len(client_results),
            current_amount + client_total_amount,
        )

        lines.append(
            f"{client_name} pagou boleto no valor {boleto_amount} referente a faturas {invoice_numbers}"
        )
        lines.append(f"Vencimento do boleto: {boleto_due_dates}")
        lines.append(f"Data do pagamento: {payment_dates}")
        lines.append("Faturas baixadas automaticamente no Linx:")
        lines.append("Fatura | Vencimento | Valor")
        for result in client_results:
            due_date = result.due_date.strftime("%d/%m/%Y") if result.due_date else "-"
            lines.append(
                f"{result.invoice_number} | {due_date} | {_format_brl(result.amount)}"
            )
        lines.append("")
        lines.append(
            f"Total do cliente {client_name}: {len(client_results)} fatura(s) | {_format_brl(client_total_amount)}"
        )
        lines.append("")

        html_rows = "".join(
            (
                "<tr>"
                f"<td style='padding:5px 7px;border:1px solid #d1d5db'>{escape(result.invoice_number)}</td>"
                f"<td style='padding:5px 7px;border:1px solid #d1d5db'>{escape(result.due_date.strftime('%d/%m/%Y') if result.due_date else '-')}</td>"
                f"<td style='padding:5px 7px;border:1px solid #d1d5db;text-align:right'>{escape(_format_brl(result.amount))}</td>"
                "</tr>"
            )
            for result in client_results
        )
        html_sections.append(
            "".join(
                [
                    f"<h3 style='margin:14px 0 6px;font-size:14px;color:#1f2937'>{escape(client_name)}</h3>",
                    (
                        f"<p style='margin:0 0 6px;color:#4b5563;font-size:12px;line-height:1.35'>"
                        f"Pagou boleto no valor <strong>{escape(boleto_amount)}</strong> "
                        f"referente a faturas {escape(invoice_numbers)}."
                        "</p>"
                    ),
                    (
                        f"<p style='margin:0 0 4px;color:#4b5563;font-size:12px;line-height:1.35'>"
                        f"<strong>Vencimento do boleto:</strong> {escape(boleto_due_dates)}"
                        "</p>"
                    ),
                    (
                        f"<p style='margin:0 0 6px;color:#4b5563;font-size:12px;line-height:1.35'>"
                        f"<strong>Data do pagamento:</strong> {escape(payment_dates)}"
                        "</p>"
                    ),
                    _build_email_table(
                        headers=("Fatura", "Vencimento", "Valor"),
                        rows=html_rows,
                    ),
                    (
                        f"<p style='margin:6px 0 0;color:#111827;font-size:12px;line-height:1.35'>"
                        f"<strong>Total do cliente:</strong> {len(client_results)} fatura(s) | "
                        f"{escape(_format_brl(client_total_amount))}"
                        "</p>"
                    ),
                ]
            )
        )

    failed_results = [item for item in results if not item.success]
    if failed_results:
        lines.append("falhas encontradas:")
        for result in failed_results:
            lines.append(f"{result.client_name} / fatura {result.invoice_number}: {result.message}")
        lines.append("")

        failure_rows = "".join(
            (
                "<tr>"
                f"<td style='padding:5px 7px;border:1px solid #d1d5db'>{escape(result.client_name)}</td>"
                f"<td style='padding:5px 7px;border:1px solid #d1d5db'>{escape(result.invoice_number)}</td>"
                f"<td style='padding:5px 7px;border:1px solid #d1d5db'>{escape(result.message)}</td>"
                "</tr>"
            )
            for result in failed_results
        )
        html_sections.append(
            "".join(
                [
                    "<h3 style='margin:18px 0 6px;font-size:14px;color:#991b1b'>Falhas encontradas</h3>",
                    _build_email_table(
                        headers=("Cliente", "Fatura", "Detalhe"),
                        rows=failure_rows,
                    ),
                ]
            )
        )

    lines.append(
        f"Total de faturas baixadas: {total_settled} fatura(s) | {_format_brl(total_settled_amount)}"
    )

    summary_rows = "".join(
        (
            "<tr>"
            f"<td style='padding:5px 7px;border:1px solid #d1d5db'>{escape(client_name)}</td>"
            f"<td style='padding:5px 7px;border:1px solid #d1d5db;text-align:center'>{count}</td>"
            f"<td style='padding:5px 7px;border:1px solid #d1d5db;text-align:right'>{escape(_format_brl(amount))}</td>"
            "</tr>"
        )
        for client_name, (count, amount) in sorted(client_totals.items())
    )
    html_body = "".join(
        [
            "<html><body style='font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#111827;line-height:1.35'>",
            f"<div style='max-width:720px'>",
            f"<h2 style='margin:0 0 10px;font-size:18px;line-height:1.25'>{escape(subject)}</h2>",
            (
                f"<p style='margin:0 0 10px;font-size:12px;line-height:1.35'>"
                f"<strong>Total de faturas baixadas:</strong> {total_settled} fatura(s) | "
                f"{escape(_format_brl(total_settled_amount))}"
                "</p>"
            ),
            (
                _build_email_table(
                    headers=("Cliente", "Quantidade", "Valor total"),
                    rows=summary_rows,
                )
                if client_totals
                else ""
            ),
            "".join(html_sections),
            "</div></body></html>",
        ]
    )
    return subject, "\n".join(lines), html_body


def _build_email_table(*, headers: tuple[str, ...], rows: str) -> str:
    header_html = "".join(
        f"<th style='padding:5px 7px;border:1px solid #d1d5db;background:#f3f4f6;text-align:left;font-size:12px;line-height:1.25'>{escape(header)}</th>"
        for header in headers
    )
    return (
        "<table style='border-collapse:collapse;width:auto;max-width:100%;margin:6px 0 8px;font-size:12px;line-height:1.25'>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _format_brl(value: Decimal) -> str:
    normalized = Decimal(value or 0).quantize(Decimal("0.01"))
    integer_part, decimal_part = f"{normalized:.2f}".split(".")
    groups: list[str] = []
    while integer_part:
        groups.append(integer_part[-3:])
        integer_part = integer_part[:-3]
    return f"R$ {'.'.join(reversed(groups))},{decimal_part}"


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(ascii_only.upper().split())


def _split_recipients(raw_value: str | None) -> list[str]:
    return [item.strip() for item in (raw_value or "").split(",") if item.strip()]
