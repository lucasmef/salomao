from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from threading import Lock
from time import monotonic

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models.finance import Category, FinancialEntry
from app.db.models.linx import LinxMovement
from app.db.models.reporting import (
    ReportLayout,
    ReportLayoutFormulaItem,
    ReportLayoutLine,
    ReportLayoutLineGroup,
)
from app.db.models.security import Company
from app.schemas.reports import (
    DreReport,
    DroReport,
    ReportConfigLine,
    ReportDashboardCard,
    ReportGroupSelection,
    ReportsOverview,
    ReportTreeNode,
)
from app.services.analytics_hybrid import (
    ANALYTICS_REPORTS_OVERVIEW,
    clear_live_cache,
    is_full_month_period,
    is_historical_period,
    iter_month_segments,
    read_live_cache,
    read_snapshot_or_rebuild,
    write_live_cache,
)
from app.services.report_layouts import get_or_create_report_config


ZERO = Decimal("0.00")

OPERATING_EXPENSE_GROUPS = {"Despesas Operacionais", "Outras Despesas Operacionais"}
FINANCIAL_EXPENSE_GROUP = "Despesas Financeiras"
NON_OPERATING_EXPENSE_GROUP = "Despesas Nao Operacionais"
PROFIT_TAX_GROUP = "Provisao para IRPJ e CSLL"
PURCHASES_PAID_GROUP = "Compras Pagas"
LOAN_PRINCIPAL_GROUP = "Emprestimo"
INCOME_ENTRY_TYPES = {"income", "historical_receipt"}
PURCHASE_RETURN_ENTRY_TYPES = {"historical_purchase_return"}
CONTROL_RECEIVABLE_SOURCE = "linx_sales_control"
SETTLEMENT_ADJUSTMENT_SOURCE = "settlement_adjustment"
CURRENT_MONTH_REPORTS_CACHE_TTL_SECONDS = 86400
HISTORICAL_MONTH_REPORTS_CACHE_TTL_SECONDS = 604800
MAX_REPORTS_CACHE_ITEMS = 24


@dataclass(slots=True)
class ReportsOverviewCacheEntry:
    expires_at: float
    payload: ReportsOverview


_reports_overview_cache: dict[tuple[str, str, str], ReportsOverviewCacheEntry] = {}
_reports_overview_cache_lock = Lock()


@dataclass
class SourceDefinition:
    amount: Decimal
    items: list[dict[str, object]]
    detail_label: str | None = None


@dataclass
class ReportContext:
    special_sources: dict[str, SourceDefinition]
    group_items: dict[str, list[dict[str, object]]]


@dataclass
class EvaluatedLine:
    line: ReportConfigLine
    formula_value: Decimal
    display_amount: Decimal
    items: list[dict[str, object]]
    detail_label: str | None


def _special_source_item(label: str, amount: Decimal) -> dict[str, object]:
    return {
        "component_key": f"special:{label}",
        "code": None,
        "label": label,
        "report_group": label,
        "subgroup_label": label,
        "subgroup_code": None,
        "macro_code": None,
        "macro_label": label,
        "amount": amount,
        "component_kind": "special_source",
    }


def _money(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _percent(
    amount: Decimal,
    base: Decimal | None,
    *,
    absolute_base: bool = False,
) -> Decimal | None:
    if base is None:
        return None
    denominator = abs(base) if absolute_base else base
    if denominator == ZERO:
        return ZERO
    return _money((amount / denominator) * Decimal("100.00"))


def _safe_decimal(value: Decimal | None) -> Decimal:
    return Decimal(value or 0)


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return (
        value.lower()
        .replace("ã§", "c")
        .replace("ã£", "a")
        .replace("ã¡", "a")
        .replace("ã¢", "a")
        .replace("ã©", "e")
        .replace("ãª", "e")
        .replace("ã­", "i")
        .replace("ã³", "o")
        .replace("ã´", "o")
        .replace("ãµ", "o")
        .replace("ãº", "u")
    )


def _group_token(scope: str, name: str | None) -> str | None:
    if not name:
        return None
    stripped = name.strip()
    if not stripped:
        return None
    return f"{scope}:{stripped}"


def _display_period_label(start: date, end: date) -> str:
    return f"{start.isoformat()} a {end.isoformat()}"


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _month_end(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1).replace(day=1) - date.resolution
    return date(value.year, value.month + 1, 1) - date.resolution


def _resolve_period(start: date | None, end: date | None, *, today: date | None = None) -> tuple[date, date]:
    reference_day = today or date.today()
    return start or date(reference_day.year, reference_day.month, 1), end or reference_day


def _is_full_month_period(start: date, end: date) -> bool:
    return start == _month_start(start) and end == _month_end(start)


def _reports_cache_ttl_seconds(start: date, end: date, *, today: date | None = None) -> int | None:
    if not _is_full_month_period(start, end):
        return None
    reference_day = today or date.today()
    current_month_start = _month_start(reference_day)
    current_month_end = _month_end(reference_day)
    if start == current_month_start and end == current_month_end:
        return CURRENT_MONTH_REPORTS_CACHE_TTL_SECONDS
    return HISTORICAL_MONTH_REPORTS_CACHE_TTL_SECONDS


def _reports_cache_key(company_id: str, start: date, end: date) -> tuple[str, str, str]:
    return company_id, start.isoformat(), end.isoformat()


def _prune_reports_overview_cache(now: float) -> None:
    expired_keys = [key for key, entry in _reports_overview_cache.items() if entry.expires_at <= now]
    for key in expired_keys:
        _reports_overview_cache.pop(key, None)
    if len(_reports_overview_cache) <= MAX_REPORTS_CACHE_ITEMS:
        return
    keys_by_expiry = sorted(_reports_overview_cache.items(), key=lambda item: item[1].expires_at)
    for key, _entry in keys_by_expiry[: len(_reports_overview_cache) - MAX_REPORTS_CACHE_ITEMS]:
        _reports_overview_cache.pop(key, None)


def clear_reports_overview_cache(company_id: str | None = None) -> None:
    with _reports_overview_cache_lock:
        if company_id is None:
            _reports_overview_cache.clear()
            clear_live_cache(None, kinds=[ANALYTICS_REPORTS_OVERVIEW])
            return
        keys_to_remove = [key for key in _reports_overview_cache if key[0] == company_id]
        for key in keys_to_remove:
            _reports_overview_cache.pop(key, None)
    clear_live_cache(company_id, kinds=[ANALYTICS_REPORTS_OVERVIEW])


def _merge_dashboard_cards(cards: list[ReportDashboardCard], other_cards: list[ReportDashboardCard]) -> list[ReportDashboardCard]:
    merged: dict[str, ReportDashboardCard] = {card.key: card.model_copy(deep=True) for card in cards}
    ordered_keys = [card.key for card in cards]
    for card in other_cards:
        if card.key not in merged:
            merged[card.key] = card.model_copy(deep=True)
            ordered_keys.append(card.key)
            continue
        current = merged[card.key]
        current.amount = _money(current.amount + card.amount)
    return [merged[key] for key in ordered_keys]


def _merge_tree_nodes(base_nodes: list[ReportTreeNode], new_nodes: list[ReportTreeNode]) -> list[ReportTreeNode]:
    merged: dict[str, ReportTreeNode] = {node.key: node.model_copy(deep=True) for node in base_nodes}
    ordered_keys = [node.key for node in base_nodes]
    for node in new_nodes:
        if node.key not in merged:
            merged[node.key] = node.model_copy(deep=True)
            ordered_keys.append(node.key)
            continue
        current = merged[node.key]
        current.amount = _money(current.amount + node.amount)
        current.children = _merge_tree_nodes(current.children, node.children)
    return [merged[key] for key in ordered_keys]


def _merge_dre_reports(left: DreReport, right: DreReport, *, period_label: str) -> DreReport:
    return DreReport(
        period_label=period_label,
        gross_revenue=_money(left.gross_revenue + right.gross_revenue),
        deductions=_money(left.deductions + right.deductions),
        net_revenue=_money(left.net_revenue + right.net_revenue),
        cmv=_money(left.cmv + right.cmv),
        gross_profit=_money(left.gross_profit + right.gross_profit),
        other_operating_income=_money(left.other_operating_income + right.other_operating_income),
        operating_expenses=_money(left.operating_expenses + right.operating_expenses),
        financial_expenses=_money(left.financial_expenses + right.financial_expenses),
        non_operating_income=_money(left.non_operating_income + right.non_operating_income),
        non_operating_expenses=_money(left.non_operating_expenses + right.non_operating_expenses),
        taxes_on_profit=_money(left.taxes_on_profit + right.taxes_on_profit),
        net_profit=_money(left.net_profit + right.net_profit),
        profit_distribution=_money(left.profit_distribution + right.profit_distribution),
        remaining_profit=_money(left.remaining_profit + right.remaining_profit),
        dashboard_cards=_merge_dashboard_cards(left.dashboard_cards, right.dashboard_cards),
        statement=_merge_tree_nodes(left.statement, right.statement),
    )


def _merge_dro_reports(left: DroReport, right: DroReport, *, period_label: str) -> DroReport:
    return DroReport(
        period_label=period_label,
        bank_revenue=_money(left.bank_revenue + right.bank_revenue),
        sales_taxes=_money(left.sales_taxes + right.sales_taxes),
        purchases_paid=_money(left.purchases_paid + right.purchases_paid),
        contribution_margin=_money(left.contribution_margin + right.contribution_margin),
        operating_expenses=_money(left.operating_expenses + right.operating_expenses),
        financial_expenses=_money(left.financial_expenses + right.financial_expenses),
        non_operating_income=_money(left.non_operating_income + right.non_operating_income),
        non_operating_expenses=_money(left.non_operating_expenses + right.non_operating_expenses),
        net_profit=_money(left.net_profit + right.net_profit),
        profit_distribution=_money(left.profit_distribution + right.profit_distribution),
        remaining_profit=_money(left.remaining_profit + right.remaining_profit),
        dashboard_cards=_merge_dashboard_cards(left.dashboard_cards, right.dashboard_cards),
        statement=_merge_tree_nodes(left.statement, right.statement),
    )


def _compose_reports_overview(parts: list[ReportsOverview], *, period_label: str) -> ReportsOverview:
    aggregate = parts[0].model_copy(deep=True)
    aggregate.dre.period_label = period_label
    aggregate.dro.period_label = period_label
    for part in parts[1:]:
        aggregate.dre = _merge_dre_reports(aggregate.dre, part.dre, period_label=period_label)
        aggregate.dro = _merge_dro_reports(aggregate.dro, part.dro, period_label=period_label)
    return aggregate


def _get_reports_segment(
    db: Session,
    company: Company,
    *,
    start: date,
    end: date,
) -> ReportsOverview:
    if not is_full_month_period(start, end):
        return build_reports_overview(db, company, start=start, end=end)
    if is_historical_period(start, end):
        return read_snapshot_or_rebuild(
            db,
            ReportsOverview,
            company=company,
            kind=ANALYTICS_REPORTS_OVERVIEW,
            snapshot_month=start,
            build_func=lambda: build_reports_overview(db, company, start=start, end=end),
        )
    ttl_seconds = _reports_cache_ttl_seconds(start, end)
    cached = read_live_cache(
        ReportsOverview,
        kind=ANALYTICS_REPORTS_OVERVIEW,
        company_id=company.id,
        start=start,
        end=end,
    )
    if cached is not None:
        return cached
    report = build_reports_overview(db, company, start=start, end=end)
    if ttl_seconds:
        write_live_cache(
            report,
            kind=ANALYTICS_REPORTS_OVERVIEW,
            company_id=company.id,
            start=start,
            end=end,
            ttl_seconds=ttl_seconds,
        )
    return report


def _competence_date(entry: FinancialEntry) -> date | None:
    return entry.competence_date or entry.issue_date or entry.due_date


def _cash_date(entry: FinancialEntry) -> date | None:
    if entry.settled_at:
        return entry.settled_at.date()
    return entry.due_date or entry.competence_date or entry.issue_date


def _dro_date(entry: FinancialEntry) -> date | None:
    return entry.due_date or entry.competence_date or entry.issue_date


def _category_code(category: Category | None) -> str | None:
    return category.code if category and category.code else None


def _category_name(category: Category | None, fallback: str) -> str:
    return category.name if category and category.name else fallback


def _category_subgroup(category: Category | None) -> str:
    if not category:
        return "Sem Grupo"
    return category.report_subgroup or category.report_group or "Sem Grupo"


def _is_profit_distribution(category: Category | None) -> bool:
    if not category:
        return False
    code = _normalize(category.code)
    name = _normalize(category.name)
    return code.startswith("4.1.5.1") or "divisao de lucros" in name


def _is_sales_tax(category: Category | None) -> bool:
    if not category:
        return False
    code = _normalize(category.code)
    if not code.startswith("4.1.4.1"):
        return False
    return code != "4.1.4.1.1"


def _is_non_operating_income(entry: FinancialEntry) -> bool:
    category_text = " ".join(
        filter(
            None,
            [
                entry.category.report_group if entry.category else None,
                entry.category.report_subgroup if entry.category else None,
                entry.category.name if entry.category else None,
                entry.title,
            ],
        )
    )
    normalized = _normalize(category_text)
    return any(
        keyword in normalized
        for keyword in (
            "juros recebidos",
            "descontos obtidos",
            "multas recebidas",
            "nao operacional",
            "receitas financeiras",
        )
    )


def _should_include_operating_income_in_dre(entry: FinancialEntry) -> bool:
    return False


def _movement_reference_date(movement: LinxMovement) -> date | None:
    if movement.launch_date:
        return movement.launch_date.date()
    if movement.issue_date:
        return movement.issue_date.date()
    return None


def _movement_total_amount(movement: LinxMovement) -> Decimal:
    if movement.total_amount is not None:
        return _safe_decimal(movement.total_amount)
    return _safe_decimal(movement.net_amount)


def _movement_cost_amount(movement: LinxMovement) -> Decimal:
    quantity = abs(_safe_decimal(movement.quantity))
    cost_price = _safe_decimal(movement.cost_price)
    if quantity == ZERO or cost_price == ZERO:
        return ZERO
    return _money(quantity * cost_price)


def _macro_for_category(category: Category | None) -> tuple[str | None, str]:
    if not category:
        return None, "Sem Categoria"

    subgroup = category.report_subgroup or category.report_group or "Sem Grupo"
    report_group = category.report_group or "Sem Grupo"
    code = category.code or ""

    if report_group == "Despesas Operacionais":
        if subgroup == "Despesas de Vendas":
            return "4.1.1", "Despesas de Vendas"
        if subgroup in {"Despesa com Pessoal", "Utilidades e Servicos", "Despesas Gerais"}:
            return "4.1.2", "Despesas Administrativas"
        return "4.1", report_group
    if report_group == FINANCIAL_EXPENSE_GROUP:
        return "4.1.3", "Despesas Financeiras"
    if report_group == "Outras Despesas Operacionais":
        return "4.1.4", "Outras Despesas Operacionais"
    if report_group == NON_OPERATING_EXPENSE_GROUP:
        return "4.1.5", "Despesas Nao Operacionais"
    if report_group == PROFIT_TAX_GROUP:
        return "4.2", "Provisao para IRPJ e CSLL"
    if report_group == PURCHASES_PAID_GROUP:
        return "3.3.1", "Compras Pagas"
    if code.startswith("3.4.2"):
        return "3.4.2", "Receitas Financeiras"
    return None, report_group


def _subgroup_code(category: Category | None) -> str | None:
    code = _category_code(category)
    if not code or "." not in code or code.startswith("HX."):
        return None
    parts = code.split(".")
    if len(parts) <= 1:
        return code
    return ".".join(parts[:-1])


def _build_tree_node(
    *,
    key: str,
    label: str,
    amount: Decimal,
    percent: Decimal | None,
    tone: str = "default",
    code: str | None = None,
    children: list[ReportTreeNode] | None = None,
) -> ReportTreeNode:
    return ReportTreeNode(
        key=key,
        label=label,
        code=code,
        amount=_money(amount),
        percent=_money(percent) if percent is not None else None,
        tone=tone,
        children=children or [],
    )


def _build_category_breakdown(
    items: list[dict[str, object]],
    *,
    percent_base: Decimal | None,
    absolute_percent_base: bool = False,
    root_key: str,
) -> list[ReportTreeNode]:
    def _percent_amount(amount: Decimal) -> Decimal:
        return abs(amount) if absolute_percent_base else amount

    macro_buckets: dict[tuple[str | None, str], list[dict[str, object]]] = defaultdict(list)
    for item in items:
        macro_buckets[(item.get("macro_code"), str(item["macro_label"]))].append(item)

    nodes: list[ReportTreeNode] = []
    for index, ((macro_code, macro_label), macro_items) in enumerate(sorted(macro_buckets.items(), key=lambda item: item[0][1])):
        subgroup_buckets: dict[tuple[str | None, str], list[dict[str, object]]] = defaultdict(list)
        macro_total = sum((Decimal(bucket["amount"]) for bucket in macro_items), ZERO)
        for bucket in macro_items:
            subgroup_buckets[(bucket.get("subgroup_code"), str(bucket["subgroup_label"]))].append(bucket)

        subgroup_nodes: list[ReportTreeNode] = []
        for subgroup_index, ((sub_code, sub_label), subgroup_items) in enumerate(sorted(subgroup_buckets.items(), key=lambda item: item[0][1])):
            subgroup_total = sum((Decimal(bucket["amount"]) for bucket in subgroup_items), ZERO)
            category_nodes = [
                _build_tree_node(
                    key=f"{root_key}-leaf-{index}-{subgroup_index}-{leaf_index}",
                    label=str(bucket["label"]),
                    code=str(bucket["code"]) if bucket.get("code") else None,
                    amount=Decimal(bucket["amount"]),
                    percent=_percent(_percent_amount(Decimal(bucket["amount"])), percent_base, absolute_base=absolute_percent_base),
                    tone="detail",
                )
                for leaf_index, bucket in enumerate(sorted(subgroup_items, key=lambda item: str(item["label"])))
            ]

            if sub_label == macro_label or not sub_label or (len(category_nodes) == 1 and not sub_code):
                subgroup_nodes.extend(category_nodes)
                continue

            subgroup_nodes.append(
                _build_tree_node(
                    key=f"{root_key}-subgroup-{index}-{subgroup_index}",
                    label=sub_label,
                    code=sub_code,
                    amount=subgroup_total,
                    percent=_percent(_percent_amount(subgroup_total), percent_base, absolute_base=absolute_percent_base),
                    tone="subtotal",
                    children=category_nodes,
                )
            )

        if not macro_code and len(subgroup_nodes) == 1 and subgroup_nodes[0].label == macro_label:
            nodes.extend(subgroup_nodes)
            continue

        nodes.append(
            _build_tree_node(
                key=f"{root_key}-macro-{index}",
                label=macro_label,
                code=macro_code,
                amount=macro_total,
                percent=_percent(_percent_amount(macro_total), percent_base, absolute_base=absolute_percent_base),
                tone="subtotal",
                children=subgroup_nodes,
            )
        )
    return nodes


def _entry_component_items(entry: FinancialEntry, *, use_paid_amount: bool) -> list[dict[str, object]]:
    if entry.source_system == SETTLEMENT_ADJUSTMENT_SOURCE:
        raw_amount = _safe_decimal(entry.paid_amount if use_paid_amount else entry.total_amount)
        amount = raw_amount if raw_amount > ZERO else _safe_decimal(entry.total_amount)
        if amount <= ZERO:
            return []

        adjustment_kind = (entry.source_reference or "").rsplit(":", 1)[-1]
        signed_amount = -amount if adjustment_kind == "discount" else amount
        category = entry.category or entry.interest_category
        macro_code, macro_label = _macro_for_category(category)
        return [
            {
                "component_key": f"entry:{entry.id}:adjustment:{adjustment_kind or 'settlement_adjustment'}",
                "code": _category_code(category) or "4.1.3.5",
                "label": _category_name(category, entry.title),
                "report_group": category.report_group if category else FINANCIAL_EXPENSE_GROUP,
                "subgroup_label": _category_subgroup(category) if category else FINANCIAL_EXPENSE_GROUP,
                "subgroup_code": _subgroup_code(category) if category else "4.1.3",
                "macro_code": macro_code or "4.1.3",
                "macro_label": macro_label or FINANCIAL_EXPENSE_GROUP,
                "amount": signed_amount,
                "component_kind": adjustment_kind or "settlement_adjustment",
            }
        ]

    if use_paid_amount:
        principal_amount = _safe_decimal(entry.paid_amount)
        if principal_amount <= ZERO and entry.status in {"settled", "planned"}:
            principal_amount = _safe_decimal(entry.total_amount)
    else:
        principal_amount = _safe_decimal(entry.principal_amount)
        if principal_amount <= ZERO:
            principal_amount = _safe_decimal(entry.total_amount)

    if principal_amount <= ZERO:
        return []

    category = entry.category
    macro_code, macro_label = _macro_for_category(category)
    return [
        {
            "component_key": f"entry:{entry.id}:principal:{category.id if category else 'uncategorized'}",
            "code": _category_code(category),
            "label": _category_name(category, entry.title),
            "report_group": category.report_group if category else None,
            "subgroup_label": _category_subgroup(category),
            "subgroup_code": _subgroup_code(category),
            "macro_code": macro_code,
            "macro_label": macro_label,
            "amount": principal_amount,
            "component_kind": "principal",
        }
    ]


def _entry_items_in_period(
    entries: list[FinancialEntry],
    *,
    start: date,
    end: date,
    date_basis: str,
    use_paid_amount: bool,
) -> list[tuple[FinancialEntry, list[dict[str, object]]]]:
    output: list[tuple[FinancialEntry, list[dict[str, object]]]] = []
    for entry in entries:
        if entry.source_system == CONTROL_RECEIVABLE_SOURCE or entry.entry_type == "transfer":
            continue
        effective_components: list[dict[str, object]] = []
        for component in _entry_component_items(entry, use_paid_amount=use_paid_amount):
            component_kind = str(component.get("component_kind") or "principal")
            if date_basis == "cash":
                effective_date = _cash_date(entry)
            elif date_basis == "due":
                effective_date = _dro_date(entry)
            else:
                effective_date = _competence_date(entry)
            if not effective_date or effective_date < start or effective_date > end:
                continue
            effective_components.append(component)
        if effective_components:
            output.append((entry, effective_components))
    return output


def _clone_item(item: dict[str, object]) -> dict[str, object]:
    cloned = dict(item)
    cloned["amount"] = Decimal(item["amount"])
    return cloned


def _build_group_items(
    entries: list[FinancialEntry],
    *,
    start: date,
    end: date,
    date_basis: str,
    use_paid_amount: bool,
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for entry, components in _entry_items_in_period(entries, start=start, end=end, date_basis=date_basis, use_paid_amount=use_paid_amount):
        for component in components:
            item = _clone_item(component)
            if use_paid_amount and entry.entry_type in PURCHASE_RETURN_ENTRY_TYPES:
                item["amount"] = -Decimal(item["amount"])
            group_token = _group_token("group", str(item.get("report_group") or "Sem Grupo"))
            subgroup_group_token = _group_token("group", str(item.get("subgroup_label") or "Sem Grupo"))
            subgroup_token = _group_token("subgroup", str(item.get("subgroup_label") or "Sem Grupo"))
            if group_token:
                grouped[group_token].append(item)
            if subgroup_group_token and subgroup_group_token != group_token:
                grouped[subgroup_group_token].append(item)
            if subgroup_token:
                grouped[subgroup_token].append(item)
    return grouped


def _build_dre_context(
    *,
    start: date,
    end: date,
    movements: list[LinxMovement],
    entries: list[FinancialEntry],
) -> ReportContext:
    gross_revenue = ZERO
    deductions = ZERO
    cmv = ZERO
    other_operating_income = ZERO
    non_operating_income = ZERO
    operating_expenses = ZERO
    financial_expenses = ZERO
    non_operating_expenses = ZERO
    taxes_on_profit = ZERO
    profit_distribution = ZERO

    for movement in movements:
        movement_date = _movement_reference_date(movement)
        if movement_date is None or movement_date < start or movement_date > end:
            continue

        if movement.movement_type == "sale":
            gross_revenue += _movement_total_amount(movement)
            cmv += _movement_cost_amount(movement)
        elif movement.movement_type == "sale_return":
            deductions += _movement_total_amount(movement)

    income_items: list[dict[str, object]] = []
    non_operating_income_items: list[dict[str, object]] = []
    operating_expense_items: list[dict[str, object]] = []
    financial_expense_items: list[dict[str, object]] = []
    non_operating_expense_items: list[dict[str, object]] = []
    tax_items: list[dict[str, object]] = []
    distribution_items: list[dict[str, object]] = []

    for entry, components in _entry_items_in_period(entries, start=start, end=end, date_basis="competence", use_paid_amount=False):
        if entry.entry_type in INCOME_ENTRY_TYPES:
            amount = _safe_decimal(entry.total_amount)
            if _is_non_operating_income(entry):
                non_operating_income += amount
                non_operating_income_items.append(
                    {
                        "code": _category_code(entry.category),
                        "label": _category_name(entry.category, entry.title),
                        "subgroup_code": _subgroup_code(entry.category),
                        "subgroup_label": _category_subgroup(entry.category),
                        "macro_code": "3.4.2",
                        "macro_label": "Receitas Nao Operacionais",
                        "amount": amount,
                    }
                )
            elif _should_include_operating_income_in_dre(entry):
                other_operating_income += amount
                income_items.append(
                    {
                        "code": _category_code(entry.category),
                        "label": _category_name(entry.category, entry.title),
                        "subgroup_code": _subgroup_code(entry.category),
                        "subgroup_label": _category_subgroup(entry.category),
                        "macro_code": None,
                        "macro_label": "Outras Receitas Operacionais",
                        "amount": amount,
                    }
                )
            continue

        if entry.entry_type in PURCHASE_RETURN_ENTRY_TYPES:
            continue

        for item in components:
            amount = Decimal(item["amount"])
            category = entry.category if item["label"] == _category_name(entry.category, entry.title) else entry.interest_category
            report_group = str(item.get("report_group") or "")

            if _is_profit_distribution(category):
                profit_distribution += amount
                distribution_items.append(_clone_item(item))
            elif report_group == PROFIT_TAX_GROUP:
                taxes_on_profit += amount
                tax_items.append(_clone_item(item))
            elif report_group == NON_OPERATING_EXPENSE_GROUP:
                non_operating_expenses += amount
                non_operating_expense_items.append(_clone_item(item))
            elif report_group == FINANCIAL_EXPENSE_GROUP:
                financial_expenses += amount
                financial_expense_items.append(_clone_item(item))
            elif report_group in {LOAN_PRINCIPAL_GROUP, PURCHASES_PAID_GROUP}:
                continue
            else:
                operating_expenses += amount
                operating_expense_items.append(_clone_item(item))
    return ReportContext(
        special_sources={
            "faturamento_bruto": SourceDefinition(amount=gross_revenue, items=[], detail_label="Total vendido na API Linx"),
            "deducoes_faturamento": SourceDefinition(amount=deductions, items=[], detail_label="Devolucoes de venda da API Linx"),
            "cmv_faturamento": SourceDefinition(amount=cmv, items=[], detail_label="Preco de custo dos itens vendidos"),
        },
        group_items=_build_group_items(entries, start=start, end=end, date_basis="competence", use_paid_amount=False),
    )


def _build_dro_context(
    *,
    start: date,
    end: date,
    entries: list[FinancialEntry],
) -> ReportContext:
    operating_revenue = ZERO
    sales_taxes = ZERO
    purchases_paid = ZERO
    operating_expenses = ZERO
    financial_expenses = ZERO
    non_operating_income = ZERO
    non_operating_expenses = ZERO
    profit_distribution = ZERO

    revenue_items: list[dict[str, object]] = []
    non_operating_income_items: list[dict[str, object]] = []
    purchases_items: list[dict[str, object]] = []
    operating_expense_items: list[dict[str, object]] = []
    financial_expense_items: list[dict[str, object]] = []
    non_operating_expense_items: list[dict[str, object]] = []
    distribution_items: list[dict[str, object]] = []
    sales_tax_items: list[dict[str, object]] = []

    for entry, components in _entry_items_in_period(entries, start=start, end=end, date_basis="due", use_paid_amount=True):
        if entry.entry_type in INCOME_ENTRY_TYPES:
            amount = _safe_decimal(entry.paid_amount if entry.paid_amount > ZERO else entry.total_amount)
            if _is_non_operating_income(entry):
                non_operating_income += amount
                non_operating_income_items.append(
                    {
                        "code": _category_code(entry.category),
                        "label": _category_name(entry.category, entry.title),
                        "subgroup_code": _subgroup_code(entry.category),
                        "subgroup_label": _category_subgroup(entry.category),
                        "macro_code": "3.4.2",
                        "macro_label": "Receitas Nao Operacionais",
                        "amount": amount,
                    }
                )
            else:
                operating_revenue += amount
                revenue_items.append(
                    {
                        "code": _category_code(entry.category),
                        "label": _category_name(entry.category, entry.title),
                        "subgroup_code": _subgroup_code(entry.category),
                        "subgroup_label": _category_subgroup(entry.category),
                        "macro_code": _subgroup_code(entry.category),
                        "macro_label": entry.category.report_group if entry.category and entry.category.report_group else "Receita",
                        "amount": amount,
                    }
                )
            continue

        if entry.entry_type in PURCHASE_RETURN_ENTRY_TYPES:
            amount = _safe_decimal(entry.paid_amount if entry.paid_amount > ZERO else entry.total_amount)
            purchases_paid -= amount
            purchases_items.append(
                {
                    "code": _category_code(entry.category),
                    "label": _category_name(entry.category, entry.title),
                    "subgroup_code": _subgroup_code(entry.category),
                    "subgroup_label": _category_subgroup(entry.category),
                    "macro_code": "3.3.1",
                    "macro_label": "Compras Pagas",
                    "amount": -amount,
                }
            )
            continue

        for item in components:
            amount = Decimal(item["amount"])
            category = entry.category if item["label"] == _category_name(entry.category, entry.title) else entry.interest_category
            report_group = str(item.get("report_group") or "")

            if _is_profit_distribution(category):
                profit_distribution += amount
                distribution_items.append(_clone_item(item))
            elif report_group == PURCHASES_PAID_GROUP:
                purchases_paid += amount
                purchases_items.append(_clone_item(item))
            elif _is_sales_tax(category):
                sales_taxes += amount
                sales_tax_items.append(_clone_item(item))
            elif report_group == FINANCIAL_EXPENSE_GROUP:
                financial_expenses += amount
                financial_expense_items.append(_clone_item(item))
            elif report_group == LOAN_PRINCIPAL_GROUP:
                continue
            elif report_group == NON_OPERATING_EXPENSE_GROUP:
                non_operating_expenses += amount
                non_operating_expense_items.append(_clone_item(item))
            else:
                operating_expenses += amount
                operating_expense_items.append(_clone_item(item))

    return ReportContext(
        special_sources={},
        group_items=_build_group_items(entries, start=start, end=end, date_basis="due", use_paid_amount=True),
    )


def _line_tone(line: ReportConfigLine) -> str:
    if line.line_type == "totalizer":
        if line.summary_binding in {"net_profit", "remaining_profit"}:
            return "result-strong"
        return "result"
    return "negative" if line.operation == "subtract" else "section"


def _children_for_evaluated_line(
    evaluated: EvaluatedLine,
    *,
    evaluated_map: dict[str, EvaluatedLine],
) -> list[ReportTreeNode]:
    if not evaluated.line.show_percent:
        percent_base: Decimal | None = None
        absolute_percent_base = False
    elif evaluated.line.percent_mode == "grouped_children":
        percent_base = abs(evaluated.formula_value)
        absolute_percent_base = True
    else:
        referenced = evaluated_map.get(evaluated.line.percent_reference_line_id or "")
        percent_base = referenced.display_amount if referenced else None
        absolute_percent_base = False

    if evaluated.items:
        return _build_category_breakdown(
            evaluated.items,
            percent_base=percent_base,
            absolute_percent_base=absolute_percent_base,
            root_key=evaluated.line.id,
        )
    if evaluated.detail_label and evaluated.display_amount != ZERO:
        return [
            _build_tree_node(
                key=f"{evaluated.line.id}-detail",
                label=evaluated.detail_label,
                amount=evaluated.display_amount,
                percent=_percent(evaluated.display_amount, percent_base, absolute_base=absolute_percent_base),
                tone="detail",
            )
        ]
    return []


def _items_for_groups(context: ReportContext, group_selections: list[ReportGroupSelection]) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for group_selection in group_selections:
        sign = Decimal("-1.00") if group_selection.operation == "subtract" else Decimal("1.00")
        for item in context.group_items.get(group_selection.group_name, []):
            component_key = str(item.get("component_key") or "")
            if component_key and component_key in seen_keys:
                continue
            if component_key:
                seen_keys.add(component_key)
            cloned_item = _clone_item(item)
            cloned_item["amount"] = Decimal(cloned_item["amount"]) * sign
            selected.append(cloned_item)
    return selected


def _evaluate_lines(
    *,
    lines: list[ReportConfigLine],
    context: ReportContext,
) -> tuple[list[EvaluatedLine], dict[str, Decimal]]:
    evaluated_map: dict[str, EvaluatedLine] = {}
    evaluated_lines: list[EvaluatedLine] = []
    metrics: dict[str, Decimal] = {}

    for line in sorted(lines, key=lambda item: item.order):
        if not line.is_active:
            continue

        if line.line_type == "source":
            items = _items_for_groups(context, line.category_groups)
            display_amount = sum((Decimal(item["amount"]) for item in items), ZERO)
            detail_label = None
            if line.special_source:
                source = context.special_sources.get(line.special_source, SourceDefinition(amount=ZERO, items=[]))
                special_source_sign = Decimal("-1.00") if line.operation == "subtract" else Decimal("1.00")
                display_amount += source.amount * special_source_sign
                for source_item in source.items:
                    cloned_item = _clone_item(source_item)
                    cloned_item["amount"] = Decimal(cloned_item["amount"]) * special_source_sign
                    items.append(cloned_item)
                if source.detail_label and source.amount != ZERO and not source.items:
                    items.append(_special_source_item(source.detail_label, source.amount * special_source_sign))
            formula_value = abs(display_amount)
        else:
            items = []
            detail_label = None
            display_amount = ZERO
            for formula_item in line.formula:
                referenced = evaluated_map[formula_item.referenced_line_id]
                if formula_item.operation == "add":
                    display_amount += referenced.formula_value
                else:
                    display_amount -= referenced.formula_value
            formula_value = display_amount

        evaluated = EvaluatedLine(
            line=line,
            formula_value=_money(formula_value),
            display_amount=_money(display_amount),
            items=items,
            detail_label=detail_label,
        )
        evaluated_map[line.id] = evaluated
        evaluated_lines.append(evaluated)
        if line.summary_binding:
            metrics[line.summary_binding] = evaluated.formula_value

    return evaluated_lines, metrics


def _line_percent(
    evaluated: EvaluatedLine,
    *,
    evaluated_map: dict[str, EvaluatedLine],
) -> Decimal | None:
    if not evaluated.line.show_percent:
        return None
    if evaluated.line.percent_mode == "grouped_children":
        if evaluated.display_amount == ZERO:
            return ZERO
        return Decimal("100.00")
    referenced = evaluated_map.get(evaluated.line.percent_reference_line_id or "")
    if not referenced:
        return None
    return _percent(evaluated.display_amount, referenced.display_amount)


def _build_dashboard_cards(lines: list[EvaluatedLine]) -> list[ReportDashboardCard]:
    return [
        ReportDashboardCard(
            key=evaluated.line.id,
            label=evaluated.line.name,
            amount=evaluated.display_amount,
        )
        for evaluated in lines
        if evaluated.line.show_on_dashboard and evaluated.line.is_active
    ]


def _build_statement(
    *,
    lines: list[EvaluatedLine],
) -> list[ReportTreeNode]:
    statement: list[ReportTreeNode] = []
    evaluated_map = {evaluated.line.id: evaluated for evaluated in lines}
    for evaluated in lines:
        if evaluated.line.is_hidden:
            continue
        statement.append(
            _build_tree_node(
                key=evaluated.line.id,
                label=evaluated.line.name,
                amount=evaluated.display_amount,
                percent=_line_percent(evaluated, evaluated_map=evaluated_map),
                tone=_line_tone(evaluated.line),
                children=_children_for_evaluated_line(evaluated, evaluated_map=evaluated_map),
            )
        )
    return statement


def build_reports_overview(
    db: Session,
    company: Company,
    start: date | None = None,
    end: date | None = None,
) -> ReportsOverview:
    period_start, period_end = _resolve_period(start, end)

    dre_config = get_or_create_report_config(db, company, "dre")
    dro_config = get_or_create_report_config(db, company, "dro")

    period_start_dt = datetime.combine(period_start, time.min)
    period_end_dt = datetime.combine(period_end, time.max)

    dre_movements = list(
        db.scalars(
            select(LinxMovement).where(
                LinxMovement.company_id == company.id,
                LinxMovement.movement_group == "sale",
                or_(
                    and_(
                        LinxMovement.launch_date.is_not(None),
                        LinxMovement.launch_date >= period_start_dt,
                        LinxMovement.launch_date <= period_end_dt,
                    ),
                    and_(
                        LinxMovement.launch_date.is_(None),
                        LinxMovement.issue_date.is_not(None),
                        LinxMovement.issue_date >= period_start_dt,
                        LinxMovement.issue_date <= period_end_dt,
                    ),
                ),
            )
        )
    )

    dre_entries = list(
        db.scalars(
            select(FinancialEntry)
            .options(
                joinedload(FinancialEntry.category),
                joinedload(FinancialEntry.interest_category),
            )
            .where(
                FinancialEntry.company_id == company.id,
                FinancialEntry.entry_type != "transfer",
                FinancialEntry.is_deleted.is_(False),
                FinancialEntry.status.in_(["planned", "settled", "partial"]),
            )
        )
    )

    dro_entries = list(
        db.scalars(
            select(FinancialEntry)
            .options(
                joinedload(FinancialEntry.category),
                joinedload(FinancialEntry.interest_category),
            )
            .where(
                FinancialEntry.company_id == company.id,
                FinancialEntry.entry_type != "transfer",
                FinancialEntry.is_deleted.is_(False),
                FinancialEntry.status.in_(["planned", "settled", "partial"]),
            )
        )
    )

    dre_context = _build_dre_context(start=period_start, end=period_end, movements=dre_movements, entries=dre_entries)
    dro_context = _build_dro_context(start=period_start, end=period_end, entries=dro_entries)
    dre_lines, dre_metrics = _evaluate_lines(lines=dre_config.lines, context=dre_context)
    dro_lines, dro_metrics = _evaluate_lines(lines=dro_config.lines, context=dro_context)

    return ReportsOverview(
        dre=DreReport(
            period_label=_display_period_label(period_start, period_end),
            gross_revenue=_money(dre_metrics.get("gross_revenue")),
            deductions=_money(dre_metrics.get("deductions")),
            net_revenue=_money(dre_metrics.get("net_revenue")),
            cmv=_money(dre_metrics.get("cmv")),
            gross_profit=_money(dre_metrics.get("gross_profit")),
            other_operating_income=_money(dre_metrics.get("other_operating_income")),
            operating_expenses=_money(dre_metrics.get("operating_expenses")),
            financial_expenses=_money(dre_metrics.get("financial_expenses")),
            non_operating_income=_money(dre_metrics.get("non_operating_income")),
            non_operating_expenses=_money(dre_metrics.get("non_operating_expenses")),
            taxes_on_profit=_money(dre_metrics.get("taxes_on_profit")),
            net_profit=_money(dre_metrics.get("net_profit")),
            profit_distribution=_money(dre_metrics.get("profit_distribution")),
            remaining_profit=_money(dre_metrics.get("remaining_profit")),
            dashboard_cards=_build_dashboard_cards(dre_lines),
            statement=_build_statement(lines=dre_lines),
        ),
        dro=DroReport(
            period_label=_display_period_label(period_start, period_end),
            bank_revenue=_money(dro_metrics.get("bank_revenue")),
            sales_taxes=_money(dro_metrics.get("sales_taxes")),
            purchases_paid=_money(dro_metrics.get("purchases_paid")),
            contribution_margin=_money(dro_metrics.get("contribution_margin")),
            operating_expenses=_money(dro_metrics.get("operating_expenses")),
            financial_expenses=_money(dro_metrics.get("financial_expenses")),
            non_operating_income=_money(dro_metrics.get("non_operating_income")),
            non_operating_expenses=_money(dro_metrics.get("non_operating_expenses")),
            net_profit=_money(dro_metrics.get("net_profit")),
            profit_distribution=_money(dro_metrics.get("profit_distribution")),
            remaining_profit=_money(dro_metrics.get("remaining_profit")),
            dashboard_cards=_build_dashboard_cards(dro_lines),
            statement=_build_statement(lines=dro_lines),
        ),
    )


def get_cached_reports_overview(
    db: Session,
    company: Company,
    start: date | None = None,
    end: date | None = None,
) -> ReportsOverview:
    period_start, period_end = _resolve_period(start, end)
    segments = iter_month_segments(period_start, period_end)
    if len(segments) == 1:
        segment_start, segment_end = segments[0]
        return _get_reports_segment(db, company, start=segment_start, end=segment_end)
    parts = [_get_reports_segment(db, company, start=segment_start, end=segment_end) for segment_start, segment_end in segments]
    return _compose_reports_overview(parts, period_label=_display_period_label(period_start, period_end))
