import type { NavIconName, SectionId } from "../types";

export type MainNavChild = {
  key: string;
  label: string;
  path: string;
  title: string;
  description: string;
  id?: SectionId;
  icon?: NavIconName;
  children?: MainNavChild[];
};

export type MainNavItem = {
  key: string;
  label: string;
  path: string;
  title: string;
  description: string;
  id: SectionId;
  icon: NavIconName;
  children: MainNavChild[];
};

export const overviewNavigationItem: MainNavItem = {
  key: "overview",
  label: "Visão Geral",
  path: "/overview/resumo",
  title: "Visão Geral",
  description: "Leitura gerencial consolidada do período com indicadores e saldos.",
  id: "overview",
  icon: "overview",
  children: [
    {
      key: "resumo",
      label: "Principal",
      path: "/overview/resumo",
      title: "Principal",
      description: "KPIs principais, DRE resumido e saldos consolidados do período.",
    },
  ],
};

export const mainNavigation: MainNavItem[] = [
  {
    key: "lancamentos",
    label: "Lançamentos",
    path: "/financeiro/lancamentos",
    title: "Lançamentos",
    description: "Consulta principal, filtros, baixas e títulos em aberto em uma única tela.",
    id: "lancamentos",
    icon: "finance",
    children: [
      {
        key: "lancamentos",
        label: "Lançamentos",
        path: "/financeiro/lancamentos",
        title: "Lançamentos",
        description: "Consulta principal, filtros, baixas e títulos em aberto em uma única tela.",
      },
    ],
  },
  {
    key: "conciliacao",
    label: "Conciliação",
    path: "/financeiro/conciliacao",
    title: "Conciliação",
    description: "Extrato bancário, importação OFX e conciliação com o sistema financeiro.",
    id: "conciliacao",
    icon: "reconciliation",
    children: [
      {
        key: "conciliacao",
        label: "Conciliação",
        path: "/financeiro/conciliacao",
        title: "Conciliação",
        description: "Extrato bancário, importação OFX e conciliação com o sistema financeiro.",
      },
    ],
  },
  {
    key: "cobranca",
    label: "Cobrança",
    path: "/financeiro/cobranca/faturas",
    title: "Cobrança",
    description: "Cobrança operacional consolidada em faturas e boletos.",
    id: "boletos",
    icon: "billing",
    children: [
      {
        key: "faturas",
        label: "Faturas",
        path: "/financeiro/cobranca/faturas",
        title: "Faturas",
        description: "Todas as faturas importadas com filtros por status, vencimento e cliente.",
      },
      {
        key: "boletos",
        label: "Boletos",
        path: "/financeiro/cobranca/boletos",
        title: "Boletos",
        description: "Boletos recorrentes, avulsos e pendências operacionais em uma única grade.",
      },
    ],
  },
  {
    key: "compras",
    label: "Compras",
    path: "/compras/planejamento",
    title: "Compras",
    description: "Planejamento operacional das compras, notas fiscais e devoluções.",
    id: "planejamento",
    icon: "planning",
    children: [
      {
        key: "planejamento",
        label: "Planejamento",
        path: "/compras/planejamento",
        title: "Planejamento",
        description: "Planejamento por marca com comparativos de coleção e acompanhamento do valor previsto.",
      },
    ],
  },
  {
    key: "resultados",
    label: "Resultados",
    path: "/caixa-resultados/fluxo-caixa",
    title: "Resultados",
    description: "Fluxo de caixa, demonstrativos e comparativos de desempenho.",
    id: "caixa",
    icon: "cashflow",
    children: [
      {
        key: "fluxo-caixa",
        label: "Fluxo de caixa",
        path: "/caixa-resultados/fluxo-caixa",
        title: "Fluxo de caixa",
        description: "Saldos, leitura do período e projeção por horizonte.",
      },
      {
        key: "vendas",
        label: "Vendas",
        path: "/caixa-resultados/vendas",
        title: "Vendas",
        description: "Relatório de vendas Linx agrupado por nota, cliente e período.",
      },
      {
        key: "dre",
        label: "DRE",
        path: "/caixa-resultados/dre",
        title: "DRE",
        description: "Demonstração do Resultado do Exercício.",
      },
      {
        key: "dro",
        label: "DRO",
        path: "/caixa-resultados/dro",
        title: "DRO",
        description: "Demonstrativo de Resultados Operacionais com base no caixa.",
      },
      {
        key: "projecoes",
        label: "Projeções",
        path: "/caixa-resultados/projecoes",
        title: "Projeções",
        description: "Recorrências, contratos e impacto futuro no caixa.",
      },
      {
        key: "comparativos",
        label: "Comparativos",
        path: "/caixa-resultados/comparativos",
        title: "Comparativos",
        description: "Comparativos anuais, mensais e evolução de indicadores.",
      },
    ],
  },
  {
    key: "sistema",
    label: "Sistema",
    path: "/cadastros/contas",
    title: "Sistema",
    description: "Administração, cadastros base, segurança e importações técnicas.",
    id: "cadastros",
    icon: "security",
    children: [
      {
        key: "contas",
        label: "Contas",
        path: "/cadastros/contas",
        title: "Contas",
        description: "Contas bancárias, caixas e configuração de OFX.",
      },
      {
        key: "categorias",
        label: "Categorias",
        path: "/cadastros/categorias",
        title: "Categorias",
        description: "Tipos, grupos e categorias do financeiro.",
      },
      {
        key: "linx",
        label: "Linx",
        path: "/cadastros/clientes",
        title: "Linx",
        description: "Bases integradas do Linx para clientes, produtos, movimentos e faturas a receber.",
        children: [
          {
            key: "clientes",
            label: "Clientes e fornecedores",
            path: "/cadastros/clientes",
            title: "Clientes e fornecedores",
            description: "Base Linx de clientes e fornecedores com visão das configurações de cobrança.",
          },
          {
            key: "produtos",
            label: "Produtos",
            path: "/cadastros/produtos",
            title: "Produtos",
            description: "Base Linx de produtos com custo, venda, fornecedor e coleção.",
          },
          {
            key: "movimentos",
            label: "Movimentos",
            path: "/cadastros/movimentos",
            title: "Movimentos",
            description: "Espelho Linx detalhado por produto para vendas e compras relevantes ao lucro por coleção.",
          },
          {
            key: "faturas-receber",
            label: "Faturas a receber",
            path: "/cadastros/faturas-a-receber",
            title: "Faturas a receber",
            description: "Espelho Linx das faturas em aberto do crediário, sem alterar a cobrança atual.",
          },
        ],
      },
      {
        key: "regras",
        label: "Regras",
        path: "/cadastros/regras",
        title: "Regras",
        description: "Regras recorrentes e padrões operacionais.",
      },
      {
        key: "seguranca",
        label: "Segurança",
        path: "/sistema/seguranca",
        title: "Segurança",
        description: "Usuários, acessos, MFA, integrações e continuidade.",
      },
      {
        key: "importacoes-gerais",
        label: "Importações gerais",
        path: "/sistema/importacoes-gerais",
        title: "Importações gerais",
        description: "Histórico central de importações e cargas históricas do sistema.",
      },
    ],
  },
];

export const legacySectionPathMap: Record<string, string> = {
  overview: "/overview/resumo",
  lancamentos: "/financeiro/lancamentos",
  conciliacao: "/financeiro/conciliacao",
  boletos: "/financeiro/cobranca/faturas",
  importacoes: "/sistema/importacoes-gerais",
  planejamento: "/compras/planejamento",
  operacoes: "/caixa-resultados/projecoes",
  caixa: "/caixa-resultados/fluxo-caixa",
  relatorios: "/caixa-resultados/dre",
  cadastros: "/cadastros/contas",
  seguranca: "/sistema/seguranca",
};

export function findMainNavItem(pathname: string) {
  function childMatchesPath(child: MainNavChild): boolean {
    if (pathname === child.path || pathname.startsWith(`${child.path}/`)) {
      return true;
    }
    return child.children?.some(childMatchesPath) ?? false;
  }

  const matchedItem =
    mainNavigation.find(
      (item) =>
        pathname === item.path ||
        pathname.startsWith(`${item.path}/`) ||
        item.children.some(childMatchesPath),
    ) ?? null;
  if (matchedItem) {
    return matchedItem;
  }
  if (pathname === overviewNavigationItem.path || pathname.startsWith(`${overviewNavigationItem.path}/`)) {
    return null;
  }
  return mainNavigation[0] ?? null;
}

export function findChildNavItem(pathname: string) {
  function findMatchingChild(items: MainNavChild[]): MainNavChild | null {
    for (const item of items) {
      if (pathname === item.path || pathname.startsWith(`${item.path}/`)) {
        return item.children ? findMatchingChild(item.children) ?? item : item;
      }
      if (item.children) {
        const nestedMatch = findMatchingChild(item.children);
        if (nestedMatch) {
          return nestedMatch;
        }
      }
    }
    return null;
  }

  function firstNavigableChild(items: MainNavChild[]): MainNavChild {
    const firstItem = items[0];
    if (!firstItem) {
      return overviewNavigationItem.children[0];
    }
    return firstItem.children ? firstNavigableChild(firstItem.children) : firstItem;
  }

  const section = findMainNavItem(pathname);
  if (!section) {
    return overviewNavigationItem.children[0];
  }
  return findMatchingChild(section.children) ?? firstNavigableChild(section.children);
}

export function findNavChildByKey(items: MainNavChild[], key: string): MainNavChild | null {
  for (const item of items) {
    if (item.key === key) {
      return item;
    }
    if (item.children) {
      const nestedMatch = findNavChildByKey(item.children, key);
      if (nestedMatch) {
        return nestedMatch;
      }
    }
  }
  return null;
}
