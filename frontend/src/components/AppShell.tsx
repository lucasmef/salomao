import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";

import salomaoLogo from "../assets/salomao-logo.png";
import type { MainNavItem } from "../data/navigation";
import type { AuthUser } from "../types";

type Props = {
  user: AuthUser;
  mainNavigation: MainNavItem[];
  children: ReactNode;
  onLogout: () => void;
  busy?: boolean;
  busyLabel?: string;
};

export function AppShell({
  user: _user,
  mainNavigation,
  children,
  onLogout,
  busy = false,
  busyLabel = "",
}: Props) {
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <header className={`app-shell-header ${mobileMenuOpen ? "mobile-menu-open" : ""}`}>
        <div className="app-shell-brand">
          <img alt="Salomão" className="app-shell-brand-logo" src={salomaoLogo} />
          <button
            aria-controls="app-shell-primary-navigation"
            aria-expanded={mobileMenuOpen}
            aria-label={mobileMenuOpen ? "Fechar menu principal" : "Abrir menu principal"}
            className="app-shell-mobile-menu-button"
            onClick={() => setMobileMenuOpen((current) => !current)}
            type="button"
          >
            <span aria-hidden="true" className="app-shell-mobile-menu-icon">
              {mobileMenuOpen ? "x" : "="}
            </span>
            <span>Menu</span>
          </button>
        </div>

        <nav className="app-shell-main-nav" aria-label="Navegacao principal" id="app-shell-primary-navigation">
          {mainNavigation.map((item) => (
            <NavLink
              key={item.key}
              className={`app-shell-main-link ${
                location.pathname.startsWith(item.path.replace(/\/[^/]+$/, "")) ? "active" : ""
              }`}
              onClick={() => setMobileMenuOpen(false)}
              to={item.path}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="app-shell-header-tools">
          {busy && busyLabel ? (
            <div className="app-shell-status" role="status" aria-live="polite">
              <span aria-hidden="true" className="app-shell-status-dot" />
              <span>{busyLabel}</span>
            </div>
          ) : null}

          <label className="app-shell-search">
            <span className="sr-only">Busca global</span>
            <input placeholder="Buscar..." type="search" />
          </label>

          <div className="app-shell-user-actions">
            <button className="app-shell-user-action" onClick={onLogout} type="button">
              Sair
            </button>
          </div>
        </div>
      </header>

      <div aria-hidden="true" className={`app-shell-progress ${busy ? "active" : ""}`}>
        <span />
      </div>

      <main aria-busy={busy} className="app-shell-content">
        {children}
      </main>
    </div>
  );
}
