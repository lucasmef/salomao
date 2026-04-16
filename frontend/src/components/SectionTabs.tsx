import { NavLink, useLocation } from "react-router-dom";
import type { MainNavChild } from "../data/navigation";
import "./SectionTabs.css";

type Props = {
  items: MainNavChild[];
};

function isPathMatch(pathname: string, path: string) {
  return pathname === path || pathname.startsWith(`${path}/`);
}

function isTabActive(item: MainNavChild, pathname: string): boolean {
  if (isPathMatch(pathname, item.path)) {
    return true;
  }
  return item.children?.some((child) => isTabActive(child, pathname)) ?? false;
}

export function SectionTabs({ items }: Props) {
  const { pathname } = useLocation();
  const activeItem = items.find((item) => isTabActive(item, pathname)) ?? items[0] ?? null;

  return (
    <div className="section-navigation">
      <nav className="tabs-container" aria-label="Abas da seção">
        {items.map((item) => (
          <NavLink
            key={item.key}
            className={({ isActive }) => `tab-link ${isTabActive(item, pathname) || isActive ? "is-active" : ""}`}
            to={item.path}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      {activeItem?.children?.length ? (
        <nav className="subtabs-container" aria-label={`Subabas de ${activeItem.label}`}>
          {activeItem.children.map((item) => (
            <NavLink
              key={item.key}
              className={({ isActive }) => `subtab-link ${isTabActive(item, pathname) || isActive ? "is-active" : ""}`}
              to={item.path}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
    </div>
  );
}
