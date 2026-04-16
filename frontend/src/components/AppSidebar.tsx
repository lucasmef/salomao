import { NavLink } from "react-router-dom";
import { NavIcon } from "./NavIcon";
import type { AuthUser, NavGroup } from "../types";
import "./AppSidebar.css";

type Props = {
  collapsed: boolean;
  groups: NavGroup[];
  section: string;
  user: AuthUser;
  onToggle: () => void;
  onLogout: () => void;
};

export function AppSidebar({ collapsed, groups, section, onToggle, onLogout }: Props) {
  return (
    <aside className={`app-sidebar ${collapsed ? "is-collapsed" : ""}`}>
      <div className="sidebar-header">
        <div className="brand-box">
          <div className="brand-logo">S</div>
          {!collapsed && <span className="brand-name">Salomão</span>}
        </div>
        <button className="toggle-btn" onClick={onToggle} type="button">
          {collapsed ? "→" : "←"}
        </button>
      </div>

      <nav className="sidebar-nav-container">
        {groups.map((group) => (
          <div key={group.id} className="nav-group">
            {!collapsed && <h3 className="group-title">{group.label}</h3>}
            <div className="group-items">
              {group.items.map((item) => (
                <NavLink
                  key={item.id}
                  to={item.path}
                  className={({ isActive }) => `nav-item ${isActive ? "is-active" : ""}`}
                  title={item.label}
                >
                  <span className="item-icon">
                    <NavIcon name={item.icon} />
                  </span>
                  {!collapsed && <span className="item-label">{item.label}</span>}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <button className="logout-btn" onClick={onLogout} type="button">
          <span className="item-icon">⎋</span>
          {!collapsed && <span className="item-label">Sair</span>}
        </button>
      </div>
    </aside>
  );
}
