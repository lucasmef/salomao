from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.db.models.finance import Category
from app.db.models.reporting import (
    ReportLayout,
    ReportLayoutFormulaItem,
    ReportLayoutLine,
    ReportLayoutLineGroup,
)
from app.db.models.security import Company
from app.schemas.reports import (
    ReportConfig,
    ReportConfigLine,
    ReportConfigUpdate,
    ReportFormulaItem,
    ReportGroupSelection,
    ReportGroupOption,
    ReportOption,
)


REPORT_SPECIAL_SOURCE_OPTIONS: dict[str, list[ReportOption]] = {
    "dre": [
        ReportOption(value="faturamento_bruto", label="Total vendido (API Linx)"),
        ReportOption(value="deducoes_faturamento", label="Devolucoes de venda (API Linx)"),
        ReportOption(value="cmv_faturamento", label="CMV dos itens vendidos (API Linx)"),
    ],
    "dro": [],
}

REPORT_DEFAULT_DASHBOARD_BINDINGS: dict[str, set[str]] = {
    "dre": {
        "gross_revenue",
        "deductions",
        "net_revenue",
        "cmv",
        "financial_expenses",
        "net_profit",
        "profit_distribution",
        "remaining_profit",
    },
    "dro": {
        "bank_revenue",
        "sales_taxes",
        "purchases_paid",
        "contribution_margin",
        "operating_expenses",
        "net_profit",
        "profit_distribution",
        "remaining_profit",
    },
}

LEGACY_SPECIAL_SOURCE_GROUPS: dict[str, dict[str, list[str]]] = {
    "dre": {
        "outras_receitas_operacionais_dre": ["group:Receitas Historicas"],
        "despesas_operacionais_dre": ["group:Despesas Operacionais", "group:Outras Despesas Operacionais"],
        "despesas_financeiras_dre": ["group:Despesas Financeiras"],
        "receitas_nao_operacionais_dre": ["group:Receitas Nao Operacionais"],
        "despesas_nao_operacionais_dre": ["group:Despesas Nao Operacionais"],
        "impostos_lucro_dre": ["group:Provisao para IRPJ e CSLL"],
        "lucro_distribuido_dre": ["subgroup:Distribuicao de Resultado"],
    },
    "dro": {
        "receitas_operacionais_dro": ["group:Receitas", "group:Receitas de Vendas", "group:Receitas Historicas"],
        "impostos_sobre_vendas_dro": ["group:Imposto de Vendas", "subgroup:Impostos e Taxas"],
        "compras_pagas": ["group:Compras Pagas"],
        "despesas_operacionais_dro": ["group:Despesas Operacionais", "group:Outras Despesas Operacionais"],
        "despesas_financeiras_dro": ["group:Despesas Financeiras"],
        "receitas_nao_operacionais_dro": ["group:Receitas Nao Operacionais"],
        "despesas_nao_operacionais_dro": ["group:Despesas Nao Operacionais"],
        "lucro_distribuido_dro": ["subgroup:Distribuicao de Resultado"],
    },
}


def _deserialize_group_selection(raw: str, *, default_operation: str) -> ReportGroupSelection:
    stripped = raw.strip()
    for operation in ("add", "subtract"):
        prefix = f"{operation}::"
        if stripped.startswith(prefix):
            return ReportGroupSelection(group_name=_normalize_group_value(stripped[len(prefix) :]), operation=operation)
    return ReportGroupSelection(group_name=_normalize_group_value(stripped), operation=default_operation)


def _serialize_group_selection(group: ReportGroupSelection) -> str:
    return f"{group.operation}::{group.group_name}"


def _make_group_selection(group_name: str, *, operation: str = "add") -> ReportGroupSelection:
    return ReportGroupSelection(group_name=_normalize_group_value(group_name), operation=operation)


def _new_id() -> str:
    return str(uuid4())


def _group_token(scope: str, name: str) -> str:
    return f"{scope}:{name.strip()}"


def _normalize_group_value(value: str) -> str:
    raw = value.strip()
    if not raw:
        return raw
    if raw.startswith("group:") or raw.startswith("subgroup:"):
        return raw
    return _group_token("group", raw)


def _make_source_line(
    *,
    name: str,
    operation: str,
    special_source: str | None = None,
    category_groups: list[str | ReportGroupSelection] | None = None,
    summary_binding: str | None = None,
    show_on_dashboard: bool = False,
    show_percent: bool = True,
    percent_mode: str = "reference_line",
    percent_reference_line_id: str | None = None,
) -> dict[str, object]:
    normalized_groups = [
        group if isinstance(group, ReportGroupSelection) else _make_group_selection(group, operation=operation)
        for group in (category_groups or [])
    ]
    return {
        "id": _new_id(),
        "name": name,
        "line_type": "source",
        "operation": operation,
        "special_source": special_source,
        "category_groups": normalized_groups,
        "formula": [],
        "show_on_dashboard": show_on_dashboard,
        "show_percent": show_percent,
        "percent_mode": percent_mode,
        "percent_reference_line_id": percent_reference_line_id,
        "is_active": True,
        "is_hidden": False,
        "summary_binding": summary_binding,
    }


def _make_totalizer_line(
    *,
    name: str,
    formula: list[dict[str, str]],
    summary_binding: str | None = None,
    show_on_dashboard: bool = False,
    show_percent: bool = True,
    percent_mode: str = "reference_line",
    percent_reference_line_id: str | None = None,
) -> dict[str, object]:
    return {
        "id": _new_id(),
        "name": name,
        "line_type": "totalizer",
        "operation": "add",
        "special_source": None,
        "category_groups": [],
        "formula": formula,
        "show_on_dashboard": show_on_dashboard,
        "show_percent": show_percent,
        "percent_mode": percent_mode,
        "percent_reference_line_id": percent_reference_line_id,
        "is_active": True,
        "is_hidden": False,
        "summary_binding": summary_binding,
    }


def _apply_default_percent_rules(lines: list[dict[str, object]]) -> list[dict[str, object]]:
    if not lines:
        return lines
    reference_line_id = str(lines[0]["id"])
    for index, line in enumerate(lines):
        if index == 0:
            line["show_percent"] = True
            line["percent_mode"] = "grouped_children"
            line["percent_reference_line_id"] = None
            continue
        line["show_percent"] = True
        line["percent_mode"] = "reference_line"
        line["percent_reference_line_id"] = reference_line_id
    return lines


def _default_dre_lines() -> list[dict[str, object]]:
    lines: dict[str, dict[str, object]] = {}
    lines["gross"] = _make_source_line(
        name="Receita Bruta de Vendas",
        operation="add",
        special_source="faturamento_bruto",
        summary_binding="gross_revenue",
        show_on_dashboard=True,
    )
    lines["deductions"] = _make_source_line(
        name="Deducoes de Vendas",
        operation="subtract",
        special_source="deducoes_faturamento",
        summary_binding="deductions",
        show_on_dashboard=True,
    )
    lines["net"] = _make_totalizer_line(
        name="Receita Liquida de Vendas",
        formula=[
            {"referenced_line_id": str(lines["gross"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["deductions"]["id"]), "operation": "subtract"},
        ],
        summary_binding="net_revenue",
        show_on_dashboard=True,
    )
    lines["cmv"] = _make_source_line(
        name="Custo dos Bens e Servicos Vendidos",
        operation="subtract",
        special_source="cmv_faturamento",
        summary_binding="cmv",
        show_on_dashboard=True,
    )
    lines["gross_profit"] = _make_totalizer_line(
        name="Resultado Operacional Bruto",
        formula=[
            {"referenced_line_id": str(lines["gross"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["deductions"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["cmv"]["id"]), "operation": "subtract"},
        ],
        summary_binding="gross_profit",
    )
    lines["other_income"] = _make_source_line(
        name="Outras Receitas Operacionais",
        operation="add",
        category_groups=[_group_token("group", "Receitas Historicas")],
        summary_binding="other_operating_income",
    )
    lines["operating_expenses"] = _make_source_line(
        name="Despesas Operacionais",
        operation="subtract",
        category_groups=[
            _group_token("group", "Despesas Operacionais"),
            _group_token("group", "Outras Despesas Operacionais"),
        ],
        summary_binding="operating_expenses",
    )
    lines["financial_expenses"] = _make_source_line(
        name="Despesas Financeiras",
        operation="subtract",
        category_groups=[_group_token("group", "Despesas Financeiras")],
        summary_binding="financial_expenses",
        show_on_dashboard=True,
    )
    lines["operating_result"] = _make_totalizer_line(
        name="Resultado Operacional Liquido",
        formula=[
            {"referenced_line_id": str(lines["gross"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["deductions"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["cmv"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["other_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["operating_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["financial_expenses"]["id"]), "operation": "subtract"},
        ],
    )
    lines["non_operating_income"] = _make_source_line(
        name="Receitas Nao Operacionais",
        operation="add",
        category_groups=[_group_token("group", "Receitas Nao Operacionais")],
        summary_binding="non_operating_income",
    )
    lines["non_operating_expenses"] = _make_source_line(
        name="Despesas Nao Operacionais",
        operation="subtract",
        category_groups=[_group_token("group", "Despesas Nao Operacionais")],
        summary_binding="non_operating_expenses",
    )
    lines["non_operating_result"] = _make_totalizer_line(
        name="Resultado Nao Operacional",
        formula=[
            {"referenced_line_id": str(lines["non_operating_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["non_operating_expenses"]["id"]), "operation": "subtract"},
        ],
    )
    lines["before_tax"] = _make_totalizer_line(
        name="Resultado antes do IRPJ e CSLL",
        formula=[
            {"referenced_line_id": str(lines["gross"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["deductions"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["cmv"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["other_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["operating_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["financial_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["non_operating_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["non_operating_expenses"]["id"]), "operation": "subtract"},
        ],
    )
    lines["taxes"] = _make_source_line(
        name="Provisao para IRPJ e CSLL",
        operation="subtract",
        category_groups=[_group_token("group", "Provisao para IRPJ e CSLL")],
        summary_binding="taxes_on_profit",
    )
    lines["net_profit"] = _make_totalizer_line(
        name="Resultado Liquido do Exercicio",
        formula=[
            {"referenced_line_id": str(lines["gross"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["deductions"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["cmv"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["other_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["operating_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["financial_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["non_operating_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["non_operating_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["taxes"]["id"]), "operation": "subtract"},
        ],
        summary_binding="net_profit",
        show_on_dashboard=True,
    )
    lines["distribution"] = _make_source_line(
        name="Lucro Distribuido",
        operation="subtract",
        category_groups=[_group_token("subgroup", "Distribuicao de Resultado")],
        summary_binding="profit_distribution",
        show_on_dashboard=True,
    )
    lines["remaining"] = _make_totalizer_line(
        name="Lucro Restante do Periodo",
        formula=[
            {"referenced_line_id": str(lines["gross"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["deductions"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["cmv"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["other_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["operating_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["financial_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["non_operating_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["non_operating_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["taxes"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["distribution"]["id"]), "operation": "subtract"},
        ],
        summary_binding="remaining_profit",
        show_on_dashboard=True,
    )
    return _apply_default_percent_rules(list(lines.values()))


def _default_dro_lines() -> list[dict[str, object]]:
    lines: dict[str, dict[str, object]] = {}
    lines["revenue"] = _make_source_line(
        name="Receita",
        operation="add",
        category_groups=[
            _group_token("group", "Receitas"),
            _group_token("group", "Receitas de Vendas"),
            _group_token("group", "Receitas Historicas"),
        ],
        summary_binding="bank_revenue",
        show_on_dashboard=True,
    )
    lines["taxes"] = _make_source_line(
        name="Impostos",
        operation="subtract",
        category_groups=[
            _group_token("group", "Imposto de Vendas"),
            _group_token("subgroup", "Impostos e Taxas"),
        ],
        summary_binding="sales_taxes",
        show_on_dashboard=True,
    )
    lines["purchases"] = _make_source_line(
        name="Compras Pagas",
        operation="subtract",
        category_groups=[_group_token("group", "Compras Pagas")],
        summary_binding="purchases_paid",
        show_on_dashboard=True,
    )
    lines["margin"] = _make_totalizer_line(
        name="Margem de Contribuicao",
        formula=[
            {"referenced_line_id": str(lines["revenue"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["taxes"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["purchases"]["id"]), "operation": "subtract"},
        ],
        summary_binding="contribution_margin",
        show_on_dashboard=True,
    )
    lines["operating_expenses"] = _make_source_line(
        name="Despesas Operacionais",
        operation="subtract",
        category_groups=[
            _group_token("group", "Despesas Operacionais"),
            _group_token("group", "Outras Despesas Operacionais"),
        ],
        summary_binding="operating_expenses",
        show_on_dashboard=True,
    )
    lines["financial_expenses"] = _make_source_line(
        name="Despesas Financeiras",
        operation="subtract",
        category_groups=[_group_token("group", "Despesas Financeiras")],
        summary_binding="financial_expenses",
    )
    lines["non_operating_income"] = _make_source_line(
        name="Receitas Nao Operacionais",
        operation="add",
        category_groups=[_group_token("group", "Receitas Nao Operacionais")],
        summary_binding="non_operating_income",
    )
    lines["non_operating_expenses"] = _make_source_line(
        name="Despesas Nao Operacionais",
        operation="subtract",
        category_groups=[_group_token("group", "Despesas Nao Operacionais")],
        summary_binding="non_operating_expenses",
    )
    lines["net_profit"] = _make_totalizer_line(
        name="Lucro Liquido",
        formula=[
            {"referenced_line_id": str(lines["revenue"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["taxes"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["purchases"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["operating_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["financial_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["non_operating_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["non_operating_expenses"]["id"]), "operation": "subtract"},
        ],
        summary_binding="net_profit",
        show_on_dashboard=True,
    )
    lines["distribution"] = _make_source_line(
        name="Lucro Distribuido",
        operation="subtract",
        category_groups=[_group_token("subgroup", "Distribuicao de Resultado")],
        summary_binding="profit_distribution",
        show_on_dashboard=True,
    )
    lines["remaining"] = _make_totalizer_line(
        name="Lucro Restante do Periodo",
        formula=[
            {"referenced_line_id": str(lines["revenue"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["taxes"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["purchases"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["operating_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["financial_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["non_operating_income"]["id"]), "operation": "add"},
            {"referenced_line_id": str(lines["non_operating_expenses"]["id"]), "operation": "subtract"},
            {"referenced_line_id": str(lines["distribution"]["id"]), "operation": "subtract"},
        ],
        summary_binding="remaining_profit",
        show_on_dashboard=True,
    )
    return _apply_default_percent_rules(list(lines.values()))


def _default_lines_for(kind: str) -> list[dict[str, object]]:
    if kind == "dre":
        return _default_dre_lines()
    if kind == "dro":
        return _default_dro_lines()
    raise HTTPException(status_code=400, detail="Tipo de relatorio invalido")


def _normalize_line(line: ReportConfigLine, *, order: int) -> ReportConfigLine:
    groups = [
        ReportGroupSelection(
            group_name=_normalize_group_value(group.group_name),
            operation=group.operation,
        )
        for group in line.category_groups
        if group.group_name.strip()
    ]
    normalized_percent_mode = "grouped_children" if not line.show_percent else line.percent_mode
    return line.model_copy(
        update={
            "name": line.name.strip(),
            "order": order,
            "category_groups": groups,
            "summary_binding": line.summary_binding.strip() if line.summary_binding else None,
            "special_source": line.special_source.strip() if line.special_source else None,
            "percent_reference_line_id": (
                line.percent_reference_line_id.strip()
                if line.percent_reference_line_id and normalized_percent_mode == "reference_line"
                else None
            ),
            "percent_mode": normalized_percent_mode,
        }
    )


def _known_bindings() -> set[str]:
    return {
        "gross_revenue",
        "deductions",
        "net_revenue",
        "cmv",
        "gross_profit",
        "other_operating_income",
        "operating_expenses",
        "financial_expenses",
        "non_operating_income",
        "non_operating_expenses",
        "taxes_on_profit",
        "net_profit",
        "profit_distribution",
        "remaining_profit",
        "bank_revenue",
        "sales_taxes",
        "purchases_paid",
        "contribution_margin",
    }


def _validate_layout(kind: str, lines: list[ReportConfigLine]) -> list[ReportConfigLine]:
    if not lines:
        raise HTTPException(status_code=400, detail="A configuracao precisa ter pelo menos uma linha.")

    known_sources = {option.value for option in REPORT_SPECIAL_SOURCE_OPTIONS[kind]}
    known_bindings = _known_bindings()
    normalized_lines = [_normalize_line(line, order=index) for index, line in enumerate(lines, start=1)]
    seen_ids: set[str] = set()
    group_owners: dict[str, str] = {}
    line_positions = {line.id: index for index, line in enumerate(normalized_lines)}
    for line in normalized_lines:
        if not line.id.strip():
            raise HTTPException(status_code=400, detail="Todas as linhas precisam de identificador.")
        if line.id in seen_ids:
            raise HTTPException(status_code=400, detail="Existem linhas duplicadas na configuracao.")
        seen_ids.add(line.id)

        if not line.name:
            raise HTTPException(status_code=400, detail="Todas as linhas precisam de nome.")

        if line.summary_binding:
            if line.summary_binding not in known_bindings:
                raise HTTPException(status_code=400, detail=f"Binding invalido: {line.summary_binding}")

        if line.show_percent:
            if line.percent_mode == "reference_line":
                if not line.percent_reference_line_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"A linha {line.name} precisa informar a referencia do percentual.",
                    )
                if line.percent_reference_line_id not in line_positions:
                    raise HTTPException(
                        status_code=400,
                        detail=f"A linha {line.name} referencia uma linha invalida para percentual.",
                    )
                if line.percent_reference_line_id == line.id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"A linha {line.name} nao pode usar a si mesma como referencia do percentual.",
                    )
                if line_positions[line.percent_reference_line_id] >= line_positions[line.id]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"A linha {line.name} so pode usar linhas anteriores como referencia do percentual.",
                    )
            else:
                if line.percent_reference_line_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"A linha {line.name} nao pode ter referencia externa quando o percentual e relativo aos lancamentos agrupados.",
                    )

        if line.line_type == "source":
            if line.formula:
                raise HTTPException(status_code=400, detail=f"A linha {line.name} nao pode ter formula sendo do tipo origem.")
            if line.special_source and line.special_source not in known_sources:
                raise HTTPException(status_code=400, detail=f"Fonte especial invalida: {line.special_source}")
            if not line.special_source and not line.category_groups:
                raise HTTPException(status_code=400, detail=f"A linha {line.name} precisa ter grupos ou uma fonte especial.")
            for group in line.category_groups:
                normalized_group_key = group.group_name.casefold()
                if normalized_group_key in group_owners:
                    raise HTTPException(
                        status_code=400,
                        detail=f"O grupo {group.group_name} ja esta sendo usado em outra linha do mesmo relatorio.",
                    )
                group_owners[normalized_group_key] = line.id
        else:
            if line.special_source or line.category_groups:
                raise HTTPException(
                    status_code=400,
                    detail=f"A linha totalizadora {line.name} nao pode ter grupos nem fonte especial.",
                )
            if not line.formula:
                raise HTTPException(status_code=400, detail=f"A linha totalizadora {line.name} precisa ter formula.")
            for formula_item in line.formula:
                if formula_item.referenced_line_id not in line_positions:
                    raise HTTPException(status_code=400, detail=f"A linha {line.name} referencia uma linha inexistente.")
                if formula_item.referenced_line_id == line.id:
                    raise HTTPException(status_code=400, detail=f"A linha {line.name} nao pode referenciar a si mesma.")
                if line_positions[formula_item.referenced_line_id] >= line_positions[line.id]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"A linha totalizadora {line.name} so pode depender de linhas anteriores.",
                    )

    return normalized_lines


def _serialize_layout(
    layout: ReportLayout,
    *,
    available_groups: list[ReportGroupOption],
) -> ReportConfig:
    lines = [
        ReportConfigLine(
            id=line.id,
            name=line.name,
            order=line.position,
            line_type=line.line_type,
            operation=line.operation,
            special_source=line.special_source,
            category_groups=[
                _deserialize_group_selection(group.group_name, default_operation=line.operation)
                for group in sorted(line.group_assignments, key=lambda item: item.position)
            ],
            formula=[
                {"referenced_line_id": item.referenced_line_id, "operation": item.operation}
                for item in sorted(line.formula_items, key=lambda item: item.position)
            ],
            show_on_dashboard=line.show_on_dashboard,
            show_percent=line.show_percent,
            percent_mode=line.percent_mode,
            percent_reference_line_id=line.percent_reference_line_id,
            is_active=line.is_active,
            is_hidden=line.is_hidden,
            summary_binding=line.summary_binding,
        )
        for line in sorted(layout.lines, key=lambda item: item.position)
    ]
    used_groups = {
        group.group_name.casefold()
        for line in lines
        if line.is_active and line.line_type == "source"
        for group in line.category_groups
    }
    unmapped_groups = [
        f"{'Grupo' if option.scope == 'group' else 'Subgrupo'}: {option.name}"
        for option in available_groups
        if option.value.casefold() not in used_groups
    ]
    return ReportConfig(
        kind=layout.kind,
        lines=lines,
        available_groups=available_groups,
        unmapped_groups=unmapped_groups,
        special_source_options=REPORT_SPECIAL_SOURCE_OPTIONS[layout.kind],
    )


def _available_groups(db: Session, company: Company) -> list[ReportGroupOption]:
    seen: dict[tuple[str, str, str], ReportGroupOption] = {}
    for category in db.scalars(
        select(Category).where(
            Category.company_id == company.id,
            Category.is_active.is_(True),
            Category.report_group.is_not(None),
        )
    ):
        group_name = (category.report_group or "").strip()
        subgroup_name = (category.report_subgroup or "").strip()
        if group_name:
            seen[(group_name, category.entry_kind, "group")] = ReportGroupOption(
                value=_group_token("group", group_name),
                name=group_name,
                entry_kind=category.entry_kind,
                scope="group",
            )
        if subgroup_name:
            seen[(subgroup_name, category.entry_kind, "subgroup")] = ReportGroupOption(
                value=_group_token("subgroup", subgroup_name),
                name=subgroup_name,
                entry_kind=category.entry_kind,
                scope="subgroup",
            )
    return sorted(seen.values(), key=lambda item: (item.entry_kind, item.scope, item.name))


def _layout_query(kind: str, company_id: str):
    return (
        select(ReportLayout)
        .options(
            joinedload(ReportLayout.lines).joinedload(ReportLayoutLine.group_assignments),
            joinedload(ReportLayout.lines).joinedload(ReportLayoutLine.formula_items),
        )
        .where(
            ReportLayout.company_id == company_id,
            ReportLayout.kind == kind,
        )
    )


def _fetch_layout(db: Session, *, company_id: str, kind: str) -> ReportLayout | None:
    return db.execute(_layout_query(kind, company_id)).unique().scalars().first()


def _persist_layout(
    db: Session,
    *,
    company: Company,
    kind: str,
    lines: list[ReportConfigLine],
) -> ReportLayout:
    layout = _fetch_layout(db, company_id=company.id, kind=kind)
    if not layout:
        layout = ReportLayout(company_id=company.id, kind=kind, name=kind.upper())
        db.add(layout)
        db.flush()
    else:
        line_ids = [line.id for line in layout.lines]
        if line_ids:
            db.execute(delete(ReportLayoutFormulaItem).where(ReportLayoutFormulaItem.line_id.in_(line_ids)))
            db.execute(delete(ReportLayoutLineGroup).where(ReportLayoutLineGroup.line_id.in_(line_ids)))
            db.execute(delete(ReportLayoutLine).where(ReportLayoutLine.id.in_(line_ids)))
            db.flush()

    for index, line in enumerate(lines, start=1):
        db_line = ReportLayoutLine(
            id=line.id,
            layout_id=layout.id,
            position=index,
            name=line.name,
            line_type=line.line_type,
            operation=line.operation,
            special_source=line.special_source,
            summary_binding=line.summary_binding,
            show_on_dashboard=line.show_on_dashboard,
            show_percent=line.show_percent,
            percent_mode=line.percent_mode,
            percent_reference_line_id=line.percent_reference_line_id,
            is_active=line.is_active,
            is_hidden=line.is_hidden,
        )
        db.add(db_line)
        for group_index, group in enumerate(line.category_groups, start=1):
            db.add(
                ReportLayoutLineGroup(
                    line_id=db_line.id,
                    position=group_index,
                    group_name=_serialize_group_selection(group),
                )
            )
        for formula_index, formula_item in enumerate(line.formula, start=1):
            db.add(
                ReportLayoutFormulaItem(
                    line_id=db_line.id,
                    referenced_line_id=formula_item.referenced_line_id,
                    position=formula_index,
                    operation=formula_item.operation,
                )
            )

    db.flush()
    db.commit()
    db.expire_all()
    return _fetch_layout(db, company_id=company.id, kind=kind)


def _normalize_existing_layout_if_needed(db: Session, company: Company, kind: str, layout: ReportLayout) -> ReportLayout:
    allowed_sources = {option.value for option in REPORT_SPECIAL_SOURCE_OPTIONS[kind]}
    changed = False
    normalized_lines: list[ReportConfigLine] = []
    raw_lines: list[ReportConfigLine] = []
    sales_tax_group = _group_token("group", "Imposto de Vendas")
    sales_tax_subgroup = _group_token("subgroup", "Impostos e Taxas")
    first_line_id = layout.lines[0].id if layout.lines else None

    for line in sorted(layout.lines, key=lambda item: item.position):
        category_groups = [group.group_name for group in sorted(line.group_assignments, key=lambda item: item.position)]
        special_source = line.special_source
        if special_source and special_source not in allowed_sources:
            category_groups = LEGACY_SPECIAL_SOURCE_GROUPS.get(kind, {}).get(special_source, category_groups)
            special_source = None
            changed = True

        normalized_groups = [
            _deserialize_group_selection(group, default_operation=line.operation)
            for group in category_groups
        ]
        if [_serialize_group_selection(group) for group in normalized_groups] != category_groups:
            changed = True
        if (
            kind == "dro"
            and line.summary_binding == "sales_taxes"
            and any(group.group_name == sales_tax_subgroup for group in normalized_groups)
            and not any(group.group_name == sales_tax_group for group in normalized_groups)
        ):
            normalized_groups = [*normalized_groups, _make_group_selection(sales_tax_group, operation="subtract")]
            changed = True

        normalized_show_percent = True if line.show_percent is None else line.show_percent
        normalized_percent_mode = line.percent_mode or ("grouped_children" if line.id == first_line_id else "reference_line")
        normalized_percent_reference_line_id = line.percent_reference_line_id
        if not normalized_show_percent:
            normalized_percent_mode = "grouped_children"
            normalized_percent_reference_line_id = None
        elif normalized_percent_mode == "reference_line":
            if not normalized_percent_reference_line_id or normalized_percent_reference_line_id == line.id:
                if line.id == first_line_id:
                    normalized_percent_mode = "grouped_children"
                    normalized_percent_reference_line_id = None
                else:
                    normalized_percent_reference_line_id = first_line_id
        else:
            normalized_percent_reference_line_id = None

        raw_line = ReportConfigLine(
            id=line.id,
            name=line.name,
            order=line.position,
            line_type=line.line_type,
            operation=line.operation,
            special_source=special_source,
            category_groups=normalized_groups,
            formula=[
                {"referenced_line_id": item.referenced_line_id, "operation": item.operation}
                for item in sorted(line.formula_items, key=lambda item: item.position)
            ],
            show_on_dashboard=line.show_on_dashboard,
            show_percent=normalized_show_percent,
            percent_mode=normalized_percent_mode,
            percent_reference_line_id=normalized_percent_reference_line_id,
            is_active=line.is_active,
            is_hidden=line.is_hidden,
            summary_binding=line.summary_binding,
        )
        if raw_line.show_on_dashboard != line.show_on_dashboard:
            changed = True
        if raw_line.show_percent != line.show_percent:
            changed = True
        if raw_line.percent_mode != (line.percent_mode or None):
            changed = True
        if raw_line.percent_reference_line_id != (line.percent_reference_line_id or None):
            changed = True
        raw_lines.append(raw_line)

    for raw_line in raw_lines:
        normalized_lines.append(
            raw_line
        )

    if not changed:
        return layout

    validated_lines = _validate_layout(kind, normalized_lines)
    return _persist_layout(db, company=company, kind=kind, lines=validated_lines)


def get_or_create_report_config(db: Session, company: Company, kind: str) -> ReportConfig:
    if kind not in {"dre", "dro"}:
        raise HTTPException(status_code=400, detail="Tipo de relatorio invalido")

    layout = _fetch_layout(db, company_id=company.id, kind=kind)
    if not layout:
        default_lines = [ReportConfigLine.model_validate({**line, "order": index}) for index, line in enumerate(_default_lines_for(kind), start=1)]
        validated_lines = _validate_layout(kind, default_lines)
        layout = _persist_layout(db, company=company, kind=kind, lines=validated_lines)
    else:
        layout = _normalize_existing_layout_if_needed(db, company, kind, layout)

    return _serialize_layout(layout, available_groups=_available_groups(db, company))


def update_report_config(db: Session, company: Company, kind: str, payload: ReportConfigUpdate) -> ReportConfig:
    if kind not in {"dre", "dro"}:
        raise HTTPException(status_code=400, detail="Tipo de relatorio invalido")

    validated_lines = _validate_layout(kind, payload.lines)
    layout = _persist_layout(db, company=company, kind=kind, lines=validated_lines)
    from app.services.cache_invalidation import clear_finance_analytics_caches

    clear_finance_analytics_caches(company.id, db=db, company=company)
    return _serialize_layout(layout, available_groups=_available_groups(db, company))
