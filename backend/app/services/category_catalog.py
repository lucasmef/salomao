from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models.finance import Category, FinancialEntry


@dataclass(frozen=True, slots=True)
class CategorySeed:
    code: str
    name: str
    entry_kind: str
    report_group: str
    report_subgroup: str
    is_financial_expense: bool = False


DEFAULT_CATEGORY_SEEDS: tuple[CategorySeed, ...] = (
    CategorySeed("4.1.1.1", "Comissoes", "expense", "Despesas Operacionais", "Despesas de Vendas"),
    CategorySeed("4.1.1.2", "Fretes e Carretos", "expense", "Despesas Operacionais", "Despesas de Vendas"),
    CategorySeed("4.1.1.3", "Revistas e Publicacoes", "expense", "Despesas Operacionais", "Despesas de Vendas"),
    CategorySeed("4.1.1.4", "Publicidade e Propaganda", "expense", "Despesas Operacionais", "Despesas de Vendas"),
    CategorySeed("4.1.1.5", "Bonificacoes e Brindes", "expense", "Despesas Operacionais", "Despesas de Vendas"),
    CategorySeed("4.1.2.1.1", "Despesa Salarios", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.2", "Participacoes e Gratificacoes", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.3", "Ferias", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.4", "13o Salario", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.5", "INSS", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.6", "Indenizacoes", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.7", "Plano de Saude", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.8", "Seguro de Vida", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.9", "Seguro de Trabalho", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.10", "Vale-Transporte", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.11", "Vale-Refeicao", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.12", "Outros Encargos", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.1.13", "FGTS", "expense", "Despesas Operacionais", "Despesa com Pessoal"),
    CategorySeed("4.1.2.2.1", "Energia Eletrica", "expense", "Despesas Operacionais", "Utilidades e Servicos"),
    CategorySeed("4.1.2.2.2", "Agua e Saneamento", "expense", "Despesas Operacionais", "Utilidades e Servicos"),
    CategorySeed("4.1.2.2.3", "Telefone", "expense", "Despesas Operacionais", "Utilidades e Servicos"),
    CategorySeed("4.1.2.2.4", "Correios", "expense", "Despesas Operacionais", "Utilidades e Servicos"),
    CategorySeed("4.1.2.2.5", "Seguros", "expense", "Despesas Operacionais", "Utilidades e Servicos"),
    CategorySeed("4.1.2.2.6", "Seguranca", "expense", "Despesas Operacionais", "Utilidades e Servicos"),
    CategorySeed("4.1.2.2.7", "Sistemas e Softwares", "expense", "Despesas Operacionais", "Utilidades e Servicos"),
    CategorySeed("4.1.2.3.1", "Despesas de Viagens", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.2", "Material de Escritorio", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.3", "Material de Consumo", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.4", "Material de Limpeza", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.6", "Equipamentos Informatica", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.7", "Combustiveis", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.8", "Assessoria Contabil", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.9", "Manutencao e Reparos", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.10", "Cursos e Treinamentos", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.11", "Servicos Profissionais", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.12", "Alugueis e Condominios", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.13", "Manutencao Automovel", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.14", "Loja Nova", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.3.99", "Despesas Gerais Diversas", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.2.4.1", "Refeitorio", "expense", "Despesas Operacionais", "Despesas Gerais"),
    CategorySeed("4.1.3.1", "Pagamento RAV", "expense", "Despesas Financeiras", "Despesas Financeiras", True),
    CategorySeed("4.1.3.2", "Descontos Concedidos", "expense", "Despesas Financeiras", "Despesas Financeiras", True),
    CategorySeed("4.1.3.3", "Despesas Bancarias", "expense", "Despesas Financeiras", "Despesas Financeiras", True),
    CategorySeed("4.1.3.4", "Taxa Financeira", "expense", "Despesas Financeiras", "Despesas Financeiras", True),
    CategorySeed("4.1.3.5", "Juros Pagos", "expense", "Despesas Financeiras", "Despesas Financeiras", True),
    CategorySeed("4.1.3.6", "Protestos", "expense", "Despesas Financeiras", "Despesas Financeiras", True),
    CategorySeed("4.1.3.7", "Diferencas de Caixa", "expense", "Despesas Financeiras", "Despesas Financeiras", True),
    CategorySeed("4.1.4.1.1", "Taxa Adm. Cartoes e Cheques", "expense", "Outras Despesas Operacionais", "Impostos e Taxas"),
    CategorySeed("4.1.4.1.2", "IPTU", "expense", "Outras Despesas Operacionais", "Impostos e Taxas"),
    CategorySeed("4.1.4.1.3", "Outros Impostos e Taxas", "expense", "Outras Despesas Operacionais", "Impostos e Taxas"),
    CategorySeed("4.1.4.1.4", "IPVA", "expense", "Outras Despesas Operacionais", "Impostos e Taxas"),
    CategorySeed("4.1.4.1.5", "Contribuicao Sindical", "expense", "Outras Despesas Operacionais", "Impostos e Taxas"),
    CategorySeed("4.1.4.1.6", "PIS e PASEP", "expense", "Outras Despesas Operacionais", "Impostos e Taxas"),
    CategorySeed("4.1.4.1.7", "Multas", "expense", "Outras Despesas Operacionais", "Impostos e Taxas"),
    CategorySeed("4.1.4.1.8", "DIFAL", "expense", "Outras Despesas Operacionais", "Impostos e Taxas"),
    CategorySeed("4.1.5.1", "Divisao de Lucros", "expense", "Despesas Nao Operacionais", "Distribuicao de Resultado"),
    CategorySeed("4.2.1", "IRPJ", "expense", "Provisao para IRPJ e CSLL", "Tributos sobre Resultado"),
    CategorySeed("4.2.2", "CSLL", "expense", "Provisao para IRPJ e CSLL", "Tributos sobre Resultado"),
    CategorySeed("4.4.1", "Emprestimo", "expense", "Emprestimo", "Emprestimo"),
    CategorySeed("HX.1", "Receitas Diversas Historicas", "income", "Receitas Historicas", "Receitas Diversas"),
    CategorySeed("HX.2", "Ajustes de Caixa", "expense", "Ajustes Historicos", "Ajustes de Caixa"),
    CategorySeed("HX.3", "Compras", "expense", "Compras Pagas", "Compras Historicas"),
    CategorySeed("HX.5", "Devolucoes de Compra", "income", "Compras Pagas", "Compras Historicas"),
    CategorySeed("HX.6", "Transferencia entre Contas", "transfer", "Movimentacoes Internas", "Transferencias Internas"),
    CategorySeed("HX.7", "Sangria", "transfer", "Movimentacoes Internas", "Transferencias Internas"),
    CategorySeed("HX.8", "Suprimento", "transfer", "Movimentacoes Internas", "Transferencias Internas"),
    CategorySeed("HX.9", "Adiantamentos", "transfer", "Movimentacoes Internas", "Transferencias Internas"),
    CategorySeed("HX.10", "Aplicacoes e Resgates", "transfer", "Movimentacoes Internas", "Transferencias Internas"),
)

LEGACY_CATEGORY_NAMES = {
    "Despesas Historicas Importadas",
    "Despesas Financeiras Historicas",
    "Recebimentos Historicos",
    "Transferencias Internas Historicas",
    "Compras Pagas Historicas",
    "Compra a Prazo Paga",
    "Compra a Vista",
    "Devolucoes de Compra Historicas",
    "Ajustes Historicos",
    "Juros e Encargos Financeiros",
}


def _find_category_by_code_or_name(db: Session, company_id: str, seed: CategorySeed) -> Category | None:
    category = db.scalar(
        select(Category).where(
            Category.company_id == company_id,
            Category.code == seed.code,
        )
    )
    if category:
        return category

    return db.scalar(
        select(Category).where(
            Category.company_id == company_id,
            Category.name == seed.name,
        )
    )


def ensure_category(
    db: Session,
    company_id: str,
    seed: CategorySeed,
) -> Category:
    category = _find_category_by_code_or_name(db, company_id, seed)
    if category:
        category.code = seed.code
        category.name = seed.name
        category.entry_kind = seed.entry_kind
        if category.report_group is None:
            category.report_group = seed.report_group
        if category.report_subgroup is None and category.report_group == seed.report_group:
            category.report_subgroup = seed.report_subgroup
        db.flush()
        return category

    category = Category(
        company_id=company_id,
        code=seed.code,
        name=seed.name,
        entry_kind=seed.entry_kind,
        report_group=seed.report_group,
        report_subgroup=seed.report_subgroup,
        is_financial_expense=seed.is_financial_expense,
        is_active=True,
    )
    db.add(category)
    db.flush()
    return category


def ensure_category_catalog(db: Session, company_id: str) -> dict[str, Category]:
    catalog: dict[str, Category] = {}
    for seed in DEFAULT_CATEGORY_SEEDS:
        category = ensure_category(db, company_id, seed)
        catalog[seed.name] = category
    return catalog


def ensure_default_financial_category(db: Session, company_id: str) -> Category:
    seed = next(item for item in DEFAULT_CATEGORY_SEEDS if item.name == "Juros Pagos")
    return ensure_category(db, company_id, seed)


def deactivate_legacy_categories(db: Session, company_id: str) -> None:
    for category in db.scalars(
        select(Category).where(
            Category.company_id == company_id,
            Category.name.in_(LEGACY_CATEGORY_NAMES),
        )
    ):
        category.is_active = False
    db.flush()


def _normalized(value: str) -> str:
    return (
        value.lower()
        .replace("ç", "c")
        .replace("ã", "a")
        .replace("á", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
    )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def match_historical_category_name(
    *,
    history: str,
    entry_type: str,
    inflow: bool,
) -> str:
    normalized = _normalized(history)

    if entry_type == "transfer":
        if "sangria" in normalized:
            return "Sangria"
        if "suprimento" in normalized:
            return "Suprimento"
        if "adiant" in normalized:
            return "Adiantamentos"
        if _contains_any(normalized, ("aplic", "resgate", "invest")):
            return "Aplicacoes e Resgates"
        return "Transferencia entre Contas"

    if entry_type == "historical_purchase":
        return "Compras"

    if entry_type == "historical_purchase_return":
        return "Devolucoes de Compra"

    if entry_type == "adjustment":
        if "divisao de lucros" in normalized:
            return "Divisao de Lucros"
        if "quebra de caixa" in normalized:
            return "Diferencas de Caixa"
        return "Ajustes de Caixa"

    if entry_type in {"historical_receipt", "income"}:
        return "Receitas Diversas Historicas"

    if "comiss" in normalized:
        return "Comissoes"
    if _contains_any(normalized, ("frete", "carreto")):
        return "Fretes e Carretos"
    if _contains_any(normalized, ("revista", "publica")):
        return "Revistas e Publicacoes"
    if _contains_any(normalized, ("propaganda", "publicidade", "marketing", "anuncio")):
        return "Publicidade e Propaganda"
    if _contains_any(normalized, ("brinde", "bonificacao")):
        return "Bonificacoes e Brindes"
    if _contains_any(normalized, ("salario", "folha")):
        return "Despesa Salarios"
    if "gratific" in normalized or "participa" in normalized:
        return "Participacoes e Gratificacoes"
    if "ferias" in normalized:
        return "Ferias"
    if "13" in normalized and "salario" in normalized:
        return "13o Salario"
    if "fgts" in normalized:
        return "FGTS"
    if "inss" in normalized:
        return "INSS"
    if "indeniz" in normalized:
        return "Indenizacoes"
    if "plano de saude" in normalized:
        return "Plano de Saude"
    if "seguro de vida" in normalized:
        return "Seguro de Vida"
    if "seguro de trabalho" in normalized:
        return "Seguro de Trabalho"
    if "vale-transporte" in normalized or "vale transporte" in normalized:
        return "Vale-Transporte"
    if "vale-refeicao" in normalized or "vale refeicao" in normalized:
        return "Vale-Refeicao"
    if _contains_any(normalized, ("encargo", "pro-labore", "pro labore")):
        return "Outros Encargos"
    if _contains_any(normalized, ("energia", "luz", "celesc", "copel")):
        return "Energia Eletrica"
    if _contains_any(normalized, ("agua", "saneamento")):
        return "Agua e Saneamento"
    if _contains_any(normalized, ("telefone", "internet", "vivo", "claro", "oi")):
        return "Telefone"
    if "correio" in normalized:
        return "Correios"
    if "seguranca" in normalized:
        return "Seguranca"
    if _contains_any(normalized, ("software", "sistema", "linx", "site", "portal")):
        return "Sistemas e Softwares"
    if _contains_any(normalized, ("viagem", "hosped", "hotel", "passagem")):
        return "Despesas de Viagens"
    if "material de escritorio" in normalized or "mat escritorio" in normalized:
        return "Material de Escritorio"
    if "material de limpeza" in normalized:
        return "Material de Limpeza"
    if "material de consumo" in normalized:
        return "Material de Consumo"
    if _contains_any(normalized, ("informatica", "computador", "notebook", "impressora")):
        return "Equipamentos Informatica"
    if _contains_any(normalized, ("combust", "gasolina", "diesel", "etanol")):
        return "Combustiveis"
    if _contains_any(normalized, ("contabil", "contador")):
        return "Assessoria Contabil"
    if "automovel" in normalized or "veiculo" in normalized:
        return "Manutencao Automovel"
    if _contains_any(normalized, ("manutenc", "reparo", "conserto")):
        return "Manutencao e Reparos"
    if _contains_any(normalized, ("curso", "treinamento", "capacita")):
        return "Cursos e Treinamentos"
    if _contains_any(normalized, ("aluguel", "condominio")):
        return "Alugueis e Condominios"
    if _contains_any(normalized, ("refeitorio", "alimentacao interna")):
        return "Refeitorio"
    if _contains_any(normalized, ("cartoes", "cartao", "cheques", "cheque")) and _contains_any(
        normalized,
        ("taxa adm", "taxaadm", "administracao", "cielo", "stone", "getnet"),
    ):
        return "Taxa Adm. Cartoes e Cheques"
    if "iptu" in normalized:
        return "IPTU"
    if "ipva" in normalized:
        return "IPVA"
    if "difal" in normalized:
        return "DIFAL"
    if _contains_any(normalized, ("pis", "pasep")):
        return "PIS e PASEP"
    if "sindical" in normalized:
        return "Contribuicao Sindical"
    if "multa" in normalized:
        return "Multas"
    if "emprest" in normalized or "pronampe" in normalized:
        return "Emprestimo"
    if _contains_any(normalized, ("juros", "mora")):
        return "Juros Pagos"
    if _contains_any(normalized, ("despesa bancaria", "despesas bancarias", "tarifa bancaria")):
        return "Despesas Bancarias"
    if "taxa financeira" in normalized:
        return "Taxa Financeira"
    if "protest" in normalized:
        return "Protestos"
    if "diferenca de caixa" in normalized:
        return "Diferencas de Caixa"
    if _contains_any(normalized, ("imposto", "taxa")):
        return "Outros Impostos e Taxas"
    if inflow:
        return "Receitas Diversas Historicas"
    return "Despesas Gerais Diversas"


def recategorize_historical_entries(db: Session, company_id: str) -> int:
    needs_update = db.scalar(
        select(FinancialEntry.id)
        .join(Category, Category.id == FinancialEntry.category_id)
        .where(
            FinancialEntry.company_id == company_id,
            FinancialEntry.external_source == "historical_cashbook",
            or_(
                Category.name.in_(LEGACY_CATEGORY_NAMES),
                Category.report_subgroup.is_(None),
            ),
        )
        .limit(1)
    )
    if not needs_update:
        deactivate_legacy_categories(db, company_id)
        db.flush()
        return 0

    catalog = ensure_category_catalog(db, company_id)
    updated = 0
    for entry in db.scalars(
        select(FinancialEntry).where(
            FinancialEntry.company_id == company_id,
            FinancialEntry.external_source == "historical_cashbook",
        )
    ):
        category_name = match_historical_category_name(
            history=entry.title or entry.description or "",
            entry_type=entry.entry_type,
            inflow=entry.entry_type in {"historical_receipt", "income"},
        )
        category = catalog.get(category_name)
        if category and entry.category_id != category.id:
            entry.category_id = category.id
            updated += 1
    deactivate_legacy_categories(db, company_id)
    db.flush()
    return updated
