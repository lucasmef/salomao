import { NavLink, useLocation } from "react-router-dom";

import type { MainNavChild } from "../data/navigation";

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
    <div className="section-tabs-stack">
      <nav className="section-tabs" aria-label="Abas da secao">
        {items.map((item) => (
          <NavLink
            key={item.key}
            className={`section-tab-link ${isTabActive(item, pathname) ? "active" : ""}`}
            to={item.path}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      {activeItem?.children?.length ? (
        <nav className="section-subtabs" aria-label={`Subabas de ${activeItem.label}`}>
          {activeItem.children.map((item) => (
            <NavLink
              key={item.key}
              className={`section-subtab-link ${isTabActive(item, pathname) ? "active" : ""}`}
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
