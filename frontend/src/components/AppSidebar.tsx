import { NavIcon } from "./NavIcon";
import type { AuthUser, NavGroup, SectionId } from "../types";

type Props = {
  collapsed: boolean;
  groups: NavGroup[];
  section: SectionId;
  user: AuthUser;
  onToggle: () => void;
  onSelect: (section: SectionId) => void;
  onLogout: () => void;
  onHoverChange: (hovered: boolean) => void;
};

export function AppSidebar({ collapsed, groups, section, user, onToggle, onSelect, onLogout, onHoverChange }: Props) {
  return (
    <aside
      className={collapsed ? "erp-sidebar collapsed" : "erp-sidebar"}
      onMouseEnter={() => collapsed && onHoverChange(true)}
      onMouseLeave={() => onHoverChange(false)}
    >
      <div className="sidebar-top">
        <div className={collapsed ? "sidebar-brand is-compact" : "sidebar-brand"}>
          <div className="sidebar-brand-mark" aria-hidden="true">
            GF
          </div>
          {!collapsed && (
            <div className="sidebar-brand-copy">
              <span className="section-label">ERP financeiro</span>
              <h1>Gestor Financeiro</h1>
            </div>
          )}
        </div>

        <button
          className="sidebar-toggle"
          onClick={onToggle}
          title={collapsed ? "Expandir menu" : "Recolher menu"}
          type="button"
        >
          <span className="sidebar-toggle-icon">{collapsed ? ">" : "<"}</span>
          {!collapsed && <span className="sidebar-toggle-label">Menu</span>}
        </button>
      </div>

      <nav className="sidebar-groups" aria-label="Navegacao principal">
        {groups.map((group) => (
          <section key={group.id} className="sidebar-group">
            {!collapsed && <p className="sidebar-group-label">{group.label}</p>}
            <div className="sidebar-nav">
              {group.items.map((item) => {
                const active = item.id === section;
                return (
                  <button
                    key={item.id}
                    className={active ? "nav-link active" : "nav-link"}
                    onClick={() => onSelect(item.id)}
                    title={item.label}
                    type="button"
                  >
                    <span className="nav-link-icon">
                      <NavIcon name={item.icon} />
                    </span>
                    {!collapsed && <span className="nav-link-label">{item.label}</span>}
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </nav>

      <div className="sidebar-footer">
        <button
          className={collapsed ? "ghost-button sidebar-logout-compact" : "ghost-button full-width"}
          onClick={onLogout}
          title="Sair"
          type="button"
        >
          {collapsed ? "X" : "Sair do sistema"}
        </button>
      </div>
    </aside>
  );
}
