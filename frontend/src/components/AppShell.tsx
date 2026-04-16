import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { AppSidebar } from "./AppSidebar";
import { mainNavigation } from "../data/navigation";
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    // Optional: auto-collapse on mobile, etc.
  }, [location.pathname]);

  return (
    <div className={`app-shell-container ${sidebarCollapsed ? "is-collapsed" : ""}`}>
      <AppSidebar
        collapsed={sidebarCollapsed}
        groups={mainNavigation}
        onLogout={onLogout}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        section={location.pathname}
        user={user}
      />

      <div className="app-main-view">
        <header className="app-top-bar">
          <div className="top-bar-left">
            {busy && busyLabel ? (
              <div className="status-indicator">
                <span className="dot pulse" />
                <span className="label">{busyLabel}</span>
              </div>
            ) : (
              <div className="page-context">
                <span className="context-label">Plataforma Salomão</span>
              </div>
            )}
          </div>

          <div className="top-bar-center">
            <form
              className="global-search-form"
              onSubmit={(e) => {
                e.preventDefault();
                onSubmitGlobalProductSearch();
              }}
            >
              <span className="search-icon">🔍</span>
              <input
                onChange={(e) => onGlobalProductSearchChange(e.target.value)}
                placeholder="Buscar produto (Ctrl + K)"
                type="text"
                value={globalProductSearch}
              />
            </form>
          </div>

          <div className="top-bar-right">
            <div className="user-profile">
              <div className="user-info">
                <span className="user-name">{user.full_name}</span>
                <span className="user-role">{user.role}</span>
              </div>
              <div className="user-avatar">{user.full_name.charAt(0)}</div>
            </div>
          </div>
        </header>

        <main className="app-content-area">
          {children}
        </main>

        <div className={`global-progress-bar ${busy ? "is-active" : ""}`}>
          <div className="progress-fill" />
        </div>
      </div>
    </div>
  );
}
