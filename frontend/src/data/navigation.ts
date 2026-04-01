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

export const mainNavigation: MainNavItem[] = [
  {
    key: "overview",
    label: "Visão Geral",
    path: "/overview/resumo",
    title: "Visão Geral",
    description: "Leitura gerencial consolidada do periodo com indicadores e saldos.",
    children: [
      {
        key: "resumo",
        label: "Principal",
        path: "/overview/resumo",
        title: "Principal",
        description: "KPIs principais, DRE resumido e saldos consolidados do periodo.",
      },
    ],
  },
  {
    key: "financeiro",
    label: "Financeiro",
    path: "/financeiro/lancamentos",
    title: "Financeiro",
    description: "Operacao financeira do dia a dia: lancamentos, conciliacao bancaria e cobranca.",
    children: [
      {
        key: "lancamentos",
        label: "Lancamentos",
        path: "/financeiro/lancamentos",
        title: "Lancamentos",
        description: "Consulta principal, filtros, baixas e titulos em aberto em uma unica tela.",
      },
      {
        key: "conciliacao",
        label: "Conciliacao",
        path: "/financeiro/conciliacao",
        title: "Conciliacao",
        description: "Extrato bancario, importacao OFX e conciliacao com o sistema financeiro.",
      },
      {
        key: "cobranca",
        label: "Cobranca",
        path: "/financeiro/cobranca",
        title: "Cobranca",
        description: "Resumo, clientes e faturas com filtros de cobranca e importacao de recebiveis.",
      },
    ],
  },
  {
    key: "compras",
    label: "Compras",
    path: "/compras/resumo",
    title: "Compras",
    description: "Resumo das compras, notas fiscais e planejamento operacional em uma estrutura simplificada.",
    children: [
      {
        key: "resumo",
        label: "Resumo",
        path: "/compras/resumo",
        title: "Resumo",
        description: "Indicadores, fluxo mensal, notas fiscais e parcelas previstas das compras.",
      },
      {
        key: "planejamento",
        label: "Planejamento",
        path: "/compras/planejamento",
        title: "Planejamento",
        description: "Planejamento por marca com comparativos de colecao e acompanhamento do valor previsto.",
      },
      {
        key: "devolucoes",
        label: "Devolucoes",
        path: "/compras/devolucoes",
        title: "Devolucao de compras",
        description: "Registro e acompanhamento das devolucoes de compras por fornecedor.",
      },
    ],
  },
  {
    key: "caixa-resultados",
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
        description: "Saldos, leitura do periodo e projecao por horizonte.",
      },
      {
        key: "dre",
        label: "DRE",
        path: "/caixa-resultados/dre",
        title: "DRE",
        description: "Demonstracao do Resultado do Exercicio.",
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
        label: "Projecoes",
        path: "/caixa-resultados/projecoes",
        title: "Projecoes",
        description: "Recorrencias, contratos e impacto futuro no caixa.",
      },
      {
        key: "comparativos",
        label: "Comparativos",
        path: "/caixa-resultados/comparativos",
        title: "Comparativos",
        description: "Comparativos anuais, mensais e evolucao de indicadores.",
      },
    ],
  },
  {
    key: "cadastros",
    label: "Cadastros",
    path: "/cadastros/contas",
    title: "Cadastros",
    description: "Estruturas base do sistema: contas, categorias, clientes e regras.",
    children: [
      {
        key: "contas",
        label: "Contas",
        path: "/cadastros/contas",
        title: "Contas",
        description: "Contas bancarias, caixas e configuracao de OFX.",
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
        description: "Cadastro-base de clientes e configuracoes de cobranca.",
      },
      {
        key: "regras",
        label: "Regras",
        path: "/cadastros/regras",
        title: "Regras",
        description: "Regras recorrentes e padroes operacionais.",
      },
      {
        key: "fornecedores",
        label: "Fornecedores",
        path: "/cadastros/fornecedores",
        title: "Fornecedores",
        description: "Cadastro dos fornecedores usados no modulo de compras.",
      },
    ],
  },
  {
    key: "sistema",
    label: "Sistema",
    path: "/sistema/usuarios",
    title: "Sistema",
    description: "Administracao, backup, seguranca, importacoes tecnicas e auditoria.",
    children: [
      {
        key: "usuarios",
        label: "Usuarios",
        path: "/sistema/usuarios",
        title: "Usuarios",
        description: "Usuarios locais, perfis e acessos.",
      },
      {
        key: "backup",
        label: "Backup",
        path: "/sistema/backup",
        title: "Backup",
        description: "Criacao, restauracao e historico de backups.",
      },
      {
        key: "seguranca",
        label: "Seguranca",
        path: "/sistema/seguranca",
        title: "Seguranca",
        description: "Politicas, protecao da base e continuidade.",
      },
      {
        key: "importacoes-gerais",
        label: "Importacoes gerais",
        path: "/sistema/importacoes-gerais",
        title: "Importacoes gerais",
        description: "Historico central de importacoes e cargas historicas do sistema.",
      },
      {
        key: "auditoria",
        label: "Auditoria",
        path: "/sistema/auditoria",
        title: "Auditoria",
        description: "Historico de eventos relevantes, importacoes e restauracoes.",
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
  planejamento: "/compras/resumo",
  operacoes: "/caixa-resultados/projecoes",
  caixa: "/caixa-resultados/fluxo-caixa",
  relatorios: "/caixa-resultados/dre",
  cadastros: "/cadastros/contas",
  seguranca: "/sistema/usuarios",
};

export function findMainNavItem(pathname: string) {
  return (
    mainNavigation.find((item) => pathname.startsWith(item.path.replace(/\/[^/]+$/, ""))) ??
    mainNavigation[0]
  );
}

export function findChildNavItem(pathname: string) {
  const section = findMainNavItem(pathname);
  return section.children.find((child) => pathname.startsWith(child.path)) ?? section.children[0];
}
