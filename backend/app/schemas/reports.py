from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ReportOption(BaseModel):
    value: str
    label: str


class ReportGroupOption(BaseModel):
    value: str
    name: str
    entry_kind: str
    scope: str = Field(pattern="^(group|subgroup)$")


class ReportFormulaItem(BaseModel):
    referenced_line_id: str
    operation: str = Field(default="add", pattern="^(add|subtract)$")


class ReportGroupSelection(BaseModel):
    group_name: str = Field(min_length=1)
    operation: str = Field(default="add", pattern="^(add|subtract)$")


class ReportConfigLine(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=160)
    order: int = 0
    line_type: str = Field(default="source", pattern="^(source|totalizer)$")
    operation: str = Field(default="add", pattern="^(add|subtract)$")
    special_source: str | None = Field(default=None, max_length=60)
    category_groups: list[ReportGroupSelection] = Field(default_factory=list)
    formula: list[ReportFormulaItem] = Field(default_factory=list)
    show_on_dashboard: bool = False
    show_percent: bool = True
    percent_mode: str = Field(default="reference_line", pattern="^(reference_line|grouped_children)$")
    percent_reference_line_id: str | None = Field(default=None, max_length=36)
    is_active: bool = True
    is_hidden: bool = False
    summary_binding: str | None = Field(default=None, max_length=60)

    @field_validator("category_groups", mode="before")
    @classmethod
    def _normalize_category_groups(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        normalized: list[object] = []
        for item in value:
            if isinstance(item, str):
                normalized.append({"group_name": item, "operation": "add"})
                continue
            if isinstance(item, dict):
                normalized.append(
                    {
                        **item,
                        "group_name": item.get("group_name", item.get("value")),
                        "operation": item.get("operation", "add"),
                    }
                )
                continue
            normalized.append(item)
        return normalized


class ReportDashboardCard(BaseModel):
    key: str
    label: str
    amount: Decimal


class ReportConfig(BaseModel):
    kind: str = Field(pattern="^(dre|dro)$")
    lines: list[ReportConfigLine] = Field(default_factory=list)
    available_groups: list[ReportGroupOption] = Field(default_factory=list)
    unmapped_groups: list[str] = Field(default_factory=list)
    special_source_options: list[ReportOption] = Field(default_factory=list)


class ReportConfigUpdate(BaseModel):
    lines: list[ReportConfigLine] = Field(default_factory=list)


class ReportTreeNode(BaseModel):
    key: str
    label: str
    code: str | None = None
    amount: Decimal
    percent: Decimal | None = None
    tone: str = "default"
    children: list["ReportTreeNode"] = Field(default_factory=list)


class DreReport(BaseModel):
    period_label: str
    gross_revenue: Decimal
    deductions: Decimal
    net_revenue: Decimal
    cmv: Decimal
    gross_profit: Decimal
    other_operating_income: Decimal
    operating_expenses: Decimal
    financial_expenses: Decimal
    non_operating_income: Decimal
    non_operating_expenses: Decimal
    taxes_on_profit: Decimal
    net_profit: Decimal
    profit_distribution: Decimal
    remaining_profit: Decimal
    dashboard_cards: list[ReportDashboardCard] = Field(default_factory=list)
    statement: list[ReportTreeNode] = Field(default_factory=list)


class DroReport(BaseModel):
    period_label: str
    bank_revenue: Decimal
    sales_taxes: Decimal
    purchases_paid: Decimal
    contribution_margin: Decimal
    operating_expenses: Decimal
    financial_expenses: Decimal
    non_operating_income: Decimal
    non_operating_expenses: Decimal
    net_profit: Decimal
    profit_distribution: Decimal
    remaining_profit: Decimal
    dashboard_cards: list[ReportDashboardCard] = Field(default_factory=list)
    statement: list[ReportTreeNode] = Field(default_factory=list)


class ReportsOverview(BaseModel):
    dre: DreReport
    dro: DroReport


ReportTreeNode.model_rebuild()
