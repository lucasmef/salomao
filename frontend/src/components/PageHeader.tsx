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

export function PageHeader({ eyebrow, title, description, actions }: Props) {
  const location = useLocation();
  const pathnames = location.pathname.split("/").filter((x) => x);

  return (
    <header className="premium-page-header">
      <nav className="header-breadcrumbs">
        <Link to="/overview/resumo" className="breadcrumb-item home">Início</Link>
        {pathnames.map((value, index) => {
          const last = index === pathnames.length - 1;
          const to = `/${pathnames.slice(0, index + 1).join("/")}`;
          const label = BREADCRUMB_MAP[value] || value.charAt(0).toUpperCase() + value.slice(1);

          return (
            <span key={to}>
              <span className="breadcrumb-separator">/</span>
              {last ? (
                <span className="breadcrumb-item active">{label}</span>
              ) : (
                <Link to={to} className="breadcrumb-item">{label}</Link>
              )}
            </span>
          );
        })}
      </nav>

      <div className="header-main-content">
        <div className="header-copy">
          {eyebrow && <span className="header-eyebrow">{eyebrow}</span>}
          <h1 className="header-title">{title}</h1>
          {description && <p className="header-description">{description}</p>}
        </div>
        {actions && <div className="header-actions">{actions}</div>}
      </div>
    </header>
  );
}
