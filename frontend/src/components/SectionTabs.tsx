import { NavLink, useLocation } from "react-router-dom";
import type { MainNavChild } from "../data/navigation";
import "./SectionTabs.css";

type Props = {
  items: MainNavChild[];
  density?: "default" | "compact";
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

export function SectionTabs({ items, density = "default" }: Props) {
  const { pathname } = useLocation();
  const activeItem = items.find((item) => isTabActive(item, pathname)) ?? items[0] ?? null;
  const isCompact = density === "compact";

  return (
    <div className={`section-navigation${isCompact ? " section-navigation--compact" : ""}`}>
      <nav className={`tabs-container${isCompact ? " tabs-container--compact" : ""}`} aria-label="Abas da seção">
        {items.map((item) => (
          <NavLink
            key={item.key}
            className={({ isActive }) =>
              `tab-link${isCompact ? " tab-link--compact" : ""} ${isTabActive(item, pathname) || isActive ? "is-active" : ""}`
            }
            to={item.path}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      {activeItem?.children?.length ? (
        <nav
          className={`subtabs-container${isCompact ? " subtabs-container--compact" : ""}`}
          aria-label={`Subabas de ${activeItem.label}`}
        >
          {activeItem.children.map((item) => (
            <NavLink
              key={item.key}
              className={({ isActive }) =>
                `subtab-link${isCompact ? " subtab-link--compact" : ""} ${isTabActive(item, pathname) || isActive ? "is-active" : ""}`
              }
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
