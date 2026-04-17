import { Link, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import "./PageHeader.css";

type Props = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
};

// Simple mapping for friendlier names
const BREADCRUMB_MAP: Record<string, string> = {
  overview: "Visão Geral",
  financeiro: "Financeiro",
  cadastros: "Cadastros",
  sistema: "Sistema",
  "caixa-resultados": "Caixa e Resultados",
  compras: "Planejamento de Compras",
  lancamentos: "Lançamentos",
  "em-aberto": "Títulos em Aberto",
  conciliacao: "Conciliação Bancária",
  cobranca: "Cobrança e Boletos",
  importacoes: "Importações",
  usuarios: "Usuários",
  backup: "Backup",
  seguranca: "Segurança",
  contas: "Contas Bancárias",
  categorias: "Categorias e DRE",
};

export function PageHeader({ title, actions }: Props) {
  return (
    <header className="premium-page-header compact">
      <div className="header-main-content">
        <h1 className="header-title">{title}</h1>
        {actions && <div className="header-actions">{actions}</div>}
      </div>
    </header>
  );
}
