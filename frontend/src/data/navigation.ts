export type MainNavChild = {
  key: string;
  label: string;
  path: string;
  title: string;
  description: string;
};

export type MainNavItem = {
  key: string;
  label: string;
  path: string;
  title: string;
  description: string;
  children: MainNavChild[];
};

export const overviewNavigationItem: MainNavItem = {
  key: "overview",
  label: "Visão Geral",
  path: "/overview/resumo",
  title: "Visão Geral",
  description: "Leitura gerencial consolidada do período com indicadores e saldos.",
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
    path: "/financeiro/cobranca",
    title: "Cobrança",
    description: "Resumo, clientes e faturas com filtros de cobrança e importação de recebíveis.",
    children: [
      {
        key: "cobranca",
        label: "Cobrança",
        path: "/financeiro/cobranca",
        title: "Cobrança",
        description: "Resumo, clientes e faturas com filtros de cobrança e importação de recebíveis.",
      },
    ],
  },
  {
    key: "compras",
    label: "Compras",
    path: "/compras/planejamento",
    title: "Compras",
    description: "Planejamento operacional das compras, notas fiscais e devoluções.",
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
    children: [
      {
        key: "fluxo-caixa",
        label: "Fluxo de caixa",
        path: "/caixa-resultados/fluxo-caixa",
        title: "Fluxo de caixa",
        description: "Saldos, leitura do período e projeção por horizonte.",
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
    description: "Administração, cadastros base, segurança, importações técnicas e auditoria.",
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
        key: "clientes",
        label: "Clientes",
        path: "/cadastros/clientes",
        title: "Clientes",
        description: "Cadastro-base de clientes e configurações de cobrança.",
      },
      {
        key: "regras",
        label: "Regras",
        path: "/cadastros/regras",
        title: "Regras",
        description: "Regras recorrentes e padrões operacionais.",
      },
      {
        key: "fornecedores",
        label: "Fornecedores",
        path: "/cadastros/fornecedores",
        title: "Fornecedores",
        description: "Cadastro dos fornecedores usados no módulo de compras.",
      },
      {
        key: "usuarios",
        label: "Usuários",
        path: "/sistema/usuarios",
        title: "Usuários",
        description: "Usuários locais, perfis e acessos.",
      },
      {
        key: "seguranca",
        label: "Segurança",
        path: "/sistema/seguranca",
        title: "Segurança",
        description: "Políticas, proteção da base e continuidade.",
      },
      {
        key: "importacoes-gerais",
        label: "Importações gerais",
        path: "/sistema/importacoes-gerais",
        title: "Importações gerais",
        description: "Histórico central de importações e cargas históricas do sistema.",
      },
      {
        key: "auditoria",
        label: "Auditoria",
        path: "/sistema/auditoria",
        title: "Auditoria",
        description: "Histórico de eventos relevantes, importações e restaurações.",
      },
    ],
  },
];

export const legacySectionPathMap: Record<string, string> = {
  overview: "/overview/resumo",
  lancamentos: "/financeiro/lancamentos",
  conciliacao: "/financeiro/conciliacao",
  boletos: "/financeiro/cobranca",
  importacoes: "/sistema/importacoes-gerais",
  planejamento: "/compras/planejamento",
  operacoes: "/caixa-resultados/projecoes",
  caixa: "/caixa-resultados/fluxo-caixa",
  relatorios: "/caixa-resultados/dre",
  cadastros: "/cadastros/contas",
  seguranca: "/sistema/usuarios",
};

export function findMainNavItem(pathname: string) {
  const matchedItem =
    mainNavigation.find(
      (item) =>
        pathname === item.path ||
        pathname.startsWith(`${item.path}/`) ||
        item.children.some((child) => pathname === child.path || pathname.startsWith(`${child.path}/`)),
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
  const section = findMainNavItem(pathname);
  if (!section) {
    return overviewNavigationItem.children[0];
  }
  return section.children.find((child) => pathname === child.path || pathname.startsWith(`${child.path}/`)) ?? section.children[0];
}
