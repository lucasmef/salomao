import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { findMainNavItem, mainNavigation, overviewNavigationItem, type MainNavItem } from "../data/navigation";
import { useNetworkActivityCount } from "../hooks/useNetworkActivityCount";
import type { AuthUser } from "../types";
import { Badge, Button, StatusPill } from "./ui";
import styles from "./AppShell.module.css";

type NavBadge = { tone?: "neutral" | "urgent" | "info"; count: number };

type Props = {
  user: AuthUser;
  children: ReactNode;
  onLogout: () => void;
  globalProductSearch: string;
  onGlobalProductSearchChange: (value: string) => void;
  onSubmitGlobalProductSearch: () => void;
  onNewEntry?: () => void;
  /** Mapa opcional de contadores por nav key (ex: { conciliacao: { tone: 'urgent', count: 12 } }) */
  navBadges?: Record<string, NavBadge>;
  busy?: boolean;
  busyLabel?: string;
};

const NAV_ITEMS: MainNavItem[] = [overviewNavigationItem, ...mainNavigation];

function formatBadgeCount(count: number) {
  return count > 99 ? "99+" : String(count);
}

export function AppShell({
  user,
  children,
  onLogout,
  globalProductSearch,
  onGlobalProductSearchChange,
  onSubmitGlobalProductSearch,
  onNewEntry,
  navBadges,
  busy = false,
  busyLabel = "",
}: Props) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const mobileSearchRef = useRef<HTMLInputElement>(null);
  const userWrapRef = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const networkActivity = useNetworkActivityCount();
  const activeSectionKey = findMainNavItem(location.pathname)?.key ?? overviewNavigationItem.key;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (drawerOpen) {
          mobileSearchRef.current?.focus();
        } else {
          searchRef.current?.focus();
        }
      }
      if (e.key === "Escape") {
        setDrawerOpen(false);
        setUserMenuOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [drawerOpen]);

  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = drawerOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [drawerOpen]);

  useEffect(() => {
    if (!userMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (userWrapRef.current && !userWrapRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [userMenuOpen]);

  const initial = user.full_name.charAt(0).toUpperCase();
  const firstName = user.full_name.split(" ")[0];

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        {/* === Linha 1 — brand + status + bell + user === */}
        <div className={`${styles.row} ${styles.row1}`}>
          <NavLink to="/overview/resumo" className={styles.brand}>
            <span className={styles.brandLogo}>S</span>
            <span className={styles.brandText}>Salomão</span>
          </NavLink>
          <span className={styles.tenantChip}>Confecções Salomão · Matriz</span>

          <div className={styles.row1Right}>
            <StatusPill status="online" pulse={networkActivity > 0}>
              {networkActivity > 0 ? "Sincronizando" : "Online"}
            </StatusPill>
            <button
              type="button"
              className={styles.iconButton}
              aria-label="Notificações"
            >
              <BellIcon />
            </button>
            <div className={styles.userWrap} ref={userWrapRef}>
              <button
                type="button"
                className={styles.userPill}
                onClick={() => setUserMenuOpen((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={userMenuOpen}
              >
                <span className={styles.avatar}>{initial}</span>
                <span className={styles.userName}>{firstName}</span>
                <span className={styles.chevron} aria-hidden="true">
                  <ChevronDown />
                </span>
              </button>
              {userMenuOpen && (
                <div className={styles.userPopover} role="menu">
                  <div className={styles.userPopoverHeader}>
                    <strong>{user.full_name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <div className={styles.popoverDivider} />
                  <button
                    type="button"
                    className={`${styles.popoverItem} ${styles.popoverItemDanger}`}
                    onClick={() => {
                      setUserMenuOpen(false);
                      onLogout();
                    }}
                  >
                    Sair do sistema
                  </button>
                </div>
              )}
            </div>
            <button
              type="button"
              className={styles.mobileToggle}
              onClick={() => setDrawerOpen((v) => !v)}
              aria-label={drawerOpen ? "Fechar menu" : "Abrir menu"}
              aria-expanded={drawerOpen}
            >
              {drawerOpen ? <CloseIcon /> : <MenuIcon />}
            </button>
          </div>
        </div>

        {/* === Linha 2 — pill nav + search + CTA === */}
        <div className={`${styles.row} ${styles.row2}`}>
          <nav className={styles.nav} aria-label="Navegação principal">
            {NAV_ITEMS.map((item) => {
              const active = activeSectionKey === item.key;
              return (
              <NavLink
                key={item.key}
                to={item.path}
                className={`${styles.navPill} ${active ? styles.active : ""}`}
                aria-current={active ? "page" : undefined}
              >
                {item.label}
                {navBadges?.[item.key] && navBadges[item.key].count > 0 && (
                  <Badge tone={navBadges[item.key].tone ?? "neutral"}>
                    {formatBadgeCount(navBadges[item.key].count)}
                  </Badge>
                )}
              </NavLink>
              );
            })}
          </nav>
          <form
            className={styles.search}
            onSubmit={(e) => {
              e.preventDefault();
              onSubmitGlobalProductSearch();
            }}
          >
            <SearchIcon />
            <input
              ref={searchRef}
              type="text"
              placeholder="Buscar produto, cliente, NF…"
              className={styles.searchInput}
              value={globalProductSearch}
              onChange={(e) => onGlobalProductSearchChange(e.target.value)}
            />
            <span className={styles.searchKbd} aria-hidden="true">⌘K</span>
          </form>
          {onNewEntry && (
            <Button variant="primary" size="sm" onClick={onNewEntry} iconLeft={<PlusIcon />}>
              Novo lançamento
            </Button>
          )}
        </div>
      </header>

      {/* === Drawer mobile === */}
      <div className={`${styles.mobileDrawer} ${drawerOpen ? styles.open : ""}`}>
        <form
          className={`${styles.search} ${styles.mobileSearch}`}
          onSubmit={(e) => {
            e.preventDefault();
            onSubmitGlobalProductSearch();
            setDrawerOpen(false);
          }}
        >
          <SearchIcon />
          <input
            ref={mobileSearchRef}
            type="text"
            placeholder="Buscar produto, cliente, NF..."
            className={styles.searchInput}
            value={globalProductSearch}
            onChange={(e) => onGlobalProductSearchChange(e.target.value)}
          />
        </form>
        {onNewEntry && (
          <div className={styles.mobileActions}>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setDrawerOpen(false);
                onNewEntry();
              }}
              iconLeft={<PlusIcon />}
            >
              Novo lançamento
            </Button>
          </div>
        )}
        {NAV_ITEMS.map((item) => {
          const active = activeSectionKey === item.key;
          return (
          <NavLink
            key={item.key}
            to={item.path}
            className={`${styles.mobileNavItem} ${active ? styles.active : ""}`}
            aria-current={active ? "page" : undefined}
          >
            {item.label}
            {navBadges?.[item.key] && navBadges[item.key].count > 0 && (
              <Badge tone={navBadges[item.key].tone ?? "neutral"}>
                {formatBadgeCount(navBadges[item.key].count)}
              </Badge>
            )}
          </NavLink>
          );
        })}
        <button type="button" className={styles.mobileLogout} onClick={onLogout}>
          Sair do sistema
        </button>
      </div>

      <main className={styles.viewport}>
        {busy && busyLabel && (
          <div className={styles.busyBanner}>
            <span className={styles.spinner} />
            <span>{busyLabel}</span>
          </div>
        )}
        <div className={styles.viewportInner}>{children}</div>
      </main>

      <div className={`${styles.loadingBar} ${busy ? styles.active : ""}`} />
    </div>
  );
}

/* === Icons (inline SVG, sem dependência) === */

function BellIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

function ChevronDown() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--color-text-muted)", flexShrink: 0 }}>
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
