import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { mainNavigation, type MainNavItem } from "../data/navigation";
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isDesktopSearchFocused, setIsDesktopSearchFocused] = useState(false);

  function closeMobileMenu() {
    setMobileMenuOpen(false);
  }

  function handleLogoutClick() {
    setMobileMenuOpen(false);
    onLogout();
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        const input = document.querySelector(".top-search input") as HTMLInputElement | null;
        input?.focus();
      }
      if (e.key === "Escape") {
        setMobileMenuOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    document.body.style.overflow = mobileMenuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileMenuOpen]);

  const allNavigation: MainNavItem[] = mainNavigation;

  return (
    <div className="modern-shell">
      <header className="main-header">
        <div className="header-inner">
          <div className="header-brand">
            <NavLink className="brand-link" to="/overview/resumo">
              <span className="brand-logo">S</span>
              <span className="brand-text">Salomão</span>
            </NavLink>
          </div>

          <nav className="header-nav">
            {allNavigation.map((item: MainNavItem) => (
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
              className="top-search desktop-only"
              onSubmit={(e) => {
                e.preventDefault();
                onSubmitGlobalProductSearch();
              }}
            >
              <div className="search-input-wrapper">
                <input
                  onBlur={() => setIsDesktopSearchFocused(false)}
                  onChange={(e) => onGlobalProductSearchChange(e.target.value)}
                  onFocus={() => setIsDesktopSearchFocused(true)}
                  placeholder="Buscar produto..."
                  type="text"
                  value={globalProductSearch}
                />
                {!isDesktopSearchFocused && <kbd className="search-shortcut">Ctrl+K</kbd>}
              </div>
            </form>

            <button className="header-logout-button desktop-only" onClick={handleLogoutClick} type="button">
              Sair
            </button>

            <button
              aria-expanded={mobileMenuOpen}
              aria-label={mobileMenuOpen ? "Fechar menu" : "Abrir menu"}
              className="mobile-toggle"
              onClick={() => setMobileMenuOpen((current) => !current)}
              type="button"
            >
              {mobileMenuOpen ? "✕" : "☰"}
            </button>
          </div>
        </div>
      </header>

      <div
        aria-hidden={!mobileMenuOpen}
        className={`mobile-nav-overlay ${mobileMenuOpen ? "is-open" : ""}`}
        onClick={closeMobileMenu}
      >
        <nav className="mobile-nav-drawer" onClick={(e) => e.stopPropagation()}>
          <div className="mobile-nav-header">
            <div className="mobile-nav-user">
              <div className="avatar small">{user.full_name.charAt(0)}</div>
              <div className="mobile-nav-user-copy">
                <strong>{user.full_name}</strong>
                <span>{user.email}</span>
              </div>
            </div>
            <button aria-label="Fechar menu" className="mobile-nav-close" onClick={closeMobileMenu} type="button">
              ✕
            </button>
          </div>

          <form
            className="top-search mobile-nav-search"
            onSubmit={(e) => {
              e.preventDefault();
              onSubmitGlobalProductSearch();
              closeMobileMenu();
            }}
          >
            <div className="search-input-wrapper">
              <input
                onChange={(e) => onGlobalProductSearchChange(e.target.value)}
                placeholder="Buscar produto..."
                type="text"
                value={globalProductSearch}
              />
            </div>
            <button className="mobile-search-submit" type="submit">
              Buscar
            </button>
          </form>

          <div className="mobile-nav-links">
            {allNavigation.map((item: MainNavItem) => (
              <NavLink key={item.key} to={item.path} className="mobile-nav-item" onClick={closeMobileMenu}>
                {item.label}
              </NavLink>
            ))}
          </div>

          <div className="popover-divider" />

          <button className="logout-item mobile-logout-item" onClick={handleLogoutClick} type="button">
            Sair
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
        <div className="viewport-container">{children}</div>
      </main>

      <div className={`top-loading-bar ${busy ? "is-active" : ""}`} />
    </div>
  );
}
