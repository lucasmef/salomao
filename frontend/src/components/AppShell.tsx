import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { mainNavigation, overviewNavigationItem } from "../data/navigation";
import type { AuthUser } from "../types";
import "./AppShell.css";

type Props = {
  user: AuthUser;
  children: ReactNode;
  onLogout: () => void;
  globalProductSearch: string;
  onGlobalProductSearchChange: (value: string) => void;
  onSubmitGlobalProductSearch: () => void;
  busy?: boolean;
  busyLabel?: string;
};

export function AppShell({
  user,
  children,
  onLogout,
  globalProductSearch,
  onGlobalProductSearchChange,
  onSubmitGlobalProductSearch,
  busy = false,
  busyLabel = "",
}: Props) {
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  const allNavigation = [overviewNavigationItem, ...mainNavigation];

  return (
    <div className="modern-shell">
      <header className="main-header">
        <div className="header-inner">
          <div className="header-brand">
            <NavLink to="/overview/resumo" className="brand-link">
              <span className="brand-logo">S</span>
              <span className="brand-text">Salomão</span>
            </NavLink>
          </div>

          <nav className="header-nav">
            {allNavigation.map((item) => (
              <NavLink
                key={item.key}
                to={item.path}
                className={({ isActive }) => `nav-link ${isActive ? "is-active" : ""}`}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="header-actions">
            <form
              className="top-search"
              onSubmit={(e) => {
                e.preventDefault();
                onSubmitGlobalProductSearch();
              }}
            >
              <input
                onChange={(e) => onGlobalProductSearchChange(e.target.value)}
                placeholder="Buscar produto..."
                type="text"
                value={globalProductSearch}
              />
            </form>

            <div className="user-dropdown">
              <button className="user-btn" onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
                <div className="avatar small">{user.full_name.charAt(0)}</div>
                <span className="user-name-compact">{user.full_name.split(" ")[0]}</span>
              </button>
              
              {mobileMenuOpen && (
                <div className="user-menu-popover">
                  <div className="popover-header">
                    <strong>{user.full_name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <div className="popover-divider" />
                  <button className="logout-item" onClick={onLogout}>
                    Sair do Sistema
                  </button>
                </div>
              )}
            </div>
            
            <button className="mobile-toggle" onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
              {mobileMenuOpen ? "✕" : "☰"}
            </button>
          </div>
        </div>
      </header>

      <div className={`mobile-nav-overlay ${mobileMenuOpen ? "is-open" : ""}`}>
        <nav className="mobile-nav-links">
          {allNavigation.map((item) => (
            <NavLink
              key={item.key}
              to={item.path}
              className="mobile-nav-item"
              onClick={() => setMobileMenuOpen(false)}
            >
              {item.label}
            </NavLink>
          ))}
          <div className="popover-divider" />
          <button className="logout-item" onClick={onLogout}>
            Sair do Sistema
          </button>
        </nav>
      </div>

      <main className="main-viewport">
        {busy && busyLabel && (
          <div className="top-busy-banner">
            <span className="spinner" />
            <span>{busyLabel}</span>
          </div>
        )}
        <div className="viewport-container">
          {children}
        </div>
      </main>

      <div className={`top-loading-bar ${busy ? "is-active" : ""}`} />
    </div>
  );
}
