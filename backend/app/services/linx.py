from __future__ import annotations

import unicodedata
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.crypto import decrypt_text, encrypt_text
from app.db.models.security import Company
from app.schemas.company_settings import LinxSettingsRead, LinxSettingsUpdate

DEFAULT_LINX_BASE_URL = "https://erp.microvix.com.br"
DEFAULT_LINX_SALES_VIEW_NAME = "FATURAMENTO SALOMAO"
DEFAULT_LINX_RECEIVABLES_VIEW_NAME = "CREDIARIO SALOMAO"
DEFAULT_LINX_PAYABLES_VIEW_NAME = "LANCAR NOTAS SALOMAO"
EMPTY_LINX_PURCHASE_PAYABLES_MARKERS = (
    "NENHUM REGISTRO",
    "NENHUMA FATURA",
    "NAO FORAM ENCONTRADOS REGISTROS",
    "NAO HA DADOS",
    "SEM RESULTADOS",
    "QUANTIDADE DE FATURAS",
)


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(ascii_only.upper().split())


def _current_month_range() -> tuple[date, date]:
    today = date.today()
    last_day = monthrange(today.year, today.month)[1]
    return date(today.year, today.month, 1), date(today.year, today.month, last_day)


def _format_linx_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _resolve_period(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    if start_date and end_date:
        return start_date, end_date
    if start_date:
        return start_date, start_date
    if end_date:
        return end_date, end_date
    return _current_month_range()


@dataclass(frozen=True)
class LinxSettings:
    base_url: str
    username: str
    password: str
    timeout_ms: int
    headless: bool
    sales_view_name: str
    receivables_view_name: str
    payables_view_name: str


def serialize_linx_settings(company: Company) -> LinxSettingsRead:
    return LinxSettingsRead(
        base_url=(company.linx_base_url or DEFAULT_LINX_BASE_URL).strip(),
        username=(company.linx_username or "").strip(),
        sales_view_name=(company.linx_sales_view_name or DEFAULT_LINX_SALES_VIEW_NAME).strip(),
        receivables_view_name=(
            company.linx_receivables_view_name or DEFAULT_LINX_RECEIVABLES_VIEW_NAME
        ).strip(),
        payables_view_name=(company.linx_payables_view_name or DEFAULT_LINX_PAYABLES_VIEW_NAME).strip(),
        has_password=bool(company.linx_password_encrypted),
        auto_sync_enabled=bool(company.linx_auto_sync_enabled),
        auto_sync_alert_email=(company.linx_auto_sync_alert_email or "").strip() or None,
        auto_sync_last_run_at=company.linx_auto_sync_last_run_at,
        auto_sync_last_status=(company.linx_auto_sync_last_status or "").strip() or None,
        auto_sync_last_error=(company.linx_auto_sync_last_error or "").strip() or None,
    )


def apply_linx_settings(company: Company, payload: LinxSettingsUpdate) -> None:
    company.linx_base_url = payload.base_url
    company.linx_username = payload.username
    company.linx_sales_view_name = payload.sales_view_name
    company.linx_receivables_view_name = payload.receivables_view_name
    company.linx_payables_view_name = payload.payables_view_name
    company.linx_auto_sync_enabled = payload.auto_sync_enabled
    company.linx_auto_sync_alert_email = payload.auto_sync_alert_email
    if payload.password is not None:
        company.linx_password_encrypted = encrypt_text(payload.password)


def _load_linx_settings(company: Company) -> LinxSettings:
    settings = get_settings()
    configured = serialize_linx_settings(company)
    password = decrypt_text(company.linx_password_encrypted)
    if not configured.username or not password:
        raise ValueError(
            "Configure usuario e senha do Linx nas configuracoes da empresa "
            "para habilitar a sincronizacao."
        )
    return LinxSettings(
        base_url=configured.base_url.rstrip("/"),
        username=configured.username,
        password=password,
        timeout_ms=settings.linx_timeout_ms,
        headless=settings.linx_headless,
        sales_view_name=configured.sales_view_name,
        receivables_view_name=configured.receivables_view_name,
        payables_view_name=configured.payables_view_name,
    )


def _require_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise ValueError(
            "Playwright nao esta instalado no backend. Instale a dependencia e execute "
            "'playwright install chromium' para habilitar a sincronizacao Linx."
        ) from error
    return sync_playwright, PlaywrightTimeoutError


def _login_and_get_report_root(page, settings: LinxSettings, timeout_error_cls) -> str:
    page.goto(settings.base_url, wait_until="networkidle")
    page.locator("#f_login").fill(settings.username)
    page.locator("#f_senha").fill(settings.password)
    page.locator("#lmxta-login-btn-autenticar").click()
    try:
        page.wait_for_url("**/home/index.asp", timeout=settings.timeout_ms)
    except timeout_error_cls as error:
        raise ValueError(
            "Nao foi possivel autenticar no Linx com as credenciais configuradas."
        ) from error
    parsed = urlparse(page.url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _select_view(page, selector: str, expected_view_name: str) -> bool:
    selected_option = page.locator(f"{selector} option:checked")
    if selected_option.count():
        current_label = selected_option.first.inner_text().strip()
        if _normalize_label(current_label) == _normalize_label(expected_view_name):
            return False

    options = page.locator(f"{selector} option")
    for index in range(options.count()):
        option = options.nth(index)
        label = option.inner_text().strip()
        if _normalize_label(label) != _normalize_label(expected_view_name):
            continue
        option_value = option.get_attribute("value")
        if not option_value:
            break
        page.select_option(selector, value=option_value)
        return True

    raise ValueError(f"Visao '{expected_view_name}' nao encontrada no relatorio do Linx.")


def _apply_date_range(
    page,
    start_selector: str,
    end_selector: str,
    start_date: date,
    end_date: date,
) -> None:
    page.locator(start_selector).fill(_format_linx_date(start_date))
    page.locator(end_selector).fill(_format_linx_date(end_date))


def _download_report(page, export_selector: str) -> tuple[str, bytes]:
    with page.expect_download() as download_info:
        page.locator(export_selector).click()
    download = download_info.value
    download_path = download.path()
    if not download_path:
        raise ValueError("O Linx nao retornou um arquivo para download.")
    return download.suggested_filename, Path(download_path).read_bytes()


def _page_body_text(page) -> str:
    try:
        return _normalize_label(page.locator("body").inner_text(timeout=2_000))
    except Exception:
        try:
            return _normalize_label(page.content())
        except Exception:
            return ""


def _page_contains_any_marker(page, markers: tuple[str, ...]) -> bool:
    body_text = _page_body_text(page)
    if not body_text:
        return False
    return any(_normalize_label(marker) in body_text for marker in markers)


def _build_empty_purchase_payables_report() -> bytes:
    return b"""
    <html>
      <body>
        <table>
          <tr><td></td><td>Periodo: 01/01/2000 a 31/12/2050</td><td></td></tr>
          <tr>
            <th>Emissao</th>
            <th>Fatura/ Empresa</th>
            <th>Venc.</th>
            <th>Parc.</th>
            <th>Valor Fatura</th>
            <th>Valor c/ Desconto e Tx. Financ.</th>
            <th>Cliente/Fornecedor</th>
            <th>Doc./ Serie/ Nosso Numero</th>
            <th>Status</th>
            <th></th>
          </tr>
          <tr><td>Legenda</td><td></td></tr>
        </table>
      </body>
    </html>
    """


def download_linx_sales_report(
    company: Company,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[str, bytes]:
    settings = _load_linx_settings(company)
    sync_playwright, timeout_error_cls = _require_playwright()
    period_start, period_end = _resolve_period(start_date, end_date)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(settings.timeout_ms)
        try:
            report_root = _login_and_get_report_root(page, settings, timeout_error_cls)
            page.goto(
                f"{report_root}/gestor_web/faturamento/relat_fat_diario.asp",
                wait_until="domcontentloaded",
            )

            if _select_view(page, "#Form1_id_visao", settings.sales_view_name):
                page.locator("input[name='Form1_SubmitVisao']").click()
                page.wait_for_load_state("domcontentloaded")

            _apply_date_range(page, "#dt_inicial", "#dt_final", period_start, period_end)
            page.locator("input[type='submit'][name='enviar']").click()
            page.wait_for_url("**/relat_fat_diario_listagem.asp**", timeout=settings.timeout_ms)
            page.locator("#botaoExportarXLS").wait_for(state="visible")
            return _download_report(page, "#botaoExportarXLS")
        except timeout_error_cls as error:
            raise ValueError(
                "Tempo esgotado ao gerar o relatorio de faturamento no Linx."
            ) from error
        finally:
            context.close()
            browser.close()


def download_linx_receivables_report(
    company: Company,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[str, bytes]:
    settings = _load_linx_settings(company)
    sync_playwright, timeout_error_cls = _require_playwright()
    _ = (start_date, end_date)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(settings.timeout_ms)
        try:
            report_root = _login_and_get_report_root(page, settings, timeout_error_cls)
            page.goto(
                (
                    f"{report_root}/gestor_web/financeiro/relatorio_faturas_periodo.asp"
                    "?tipolanc=receber&filtro_adm_cartao=S&lancamento=S"
                ),
                wait_until="domcontentloaded",
            )

            # For receivables, the saved Linx view carries the intended report scope.
            # Reapplying dates here makes Microvix fall back to the current-month search.
            _select_view(page, "#form1_id_visao", settings.receivables_view_name)
            page.locator("input[name='form1_SubmitVisao']").click()
            page.wait_for_url("**/listagem_relatorio_periodo.asp**", timeout=settings.timeout_ms)
            page.locator("#botaoExportarXLS").wait_for(state="visible")
            return _download_report(page, "#botaoExportarXLS")
        except timeout_error_cls as error:
            raise ValueError(
                "Tempo esgotado ao gerar o relatorio de faturas a receber no Linx."
            ) from error
        finally:
            context.close()
            browser.close()


def download_linx_purchase_payables_report(company: Company) -> tuple[str, bytes]:
    settings = _load_linx_settings(company)
    sync_playwright, timeout_error_cls = _require_playwright()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(settings.timeout_ms)
        try:
            report_root = _login_and_get_report_root(page, settings, timeout_error_cls)
            page.goto(
                (
                    f"{report_root}/gestor_web/financeiro/relatorio_faturas_periodo.asp"
                    "?tipolanc=pagar&lancamento=S"
                ),
                wait_until="domcontentloaded",
            )

            _select_view(page, "#form1_id_visao", settings.payables_view_name)
            page.locator("input[name='form1_SubmitVisao']").click()
            page.wait_for_load_state("domcontentloaded")
            try:
                page.locator("#botaoExportarXLS").wait_for(
                    state="visible",
                    timeout=min(settings.timeout_ms, 15_000),
                )
            except timeout_error_cls:
                if _page_contains_any_marker(page, EMPTY_LINX_PURCHASE_PAYABLES_MARKERS):
                    return "FaturasaPagarporPeriodo.xls", _build_empty_purchase_payables_report()
                raise
            return _download_report(page, "#botaoExportarXLS")
        except timeout_error_cls as error:
            raise ValueError(
                "Tempo esgotado ao gerar o relatorio de faturas a pagar no Linx."
            ) from error
        finally:
            context.close()
            browser.close()
