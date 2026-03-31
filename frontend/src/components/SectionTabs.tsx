import { NavLink } from "react-router-dom";

import type { MainNavChild } from "../data/navigation";

type Props = {
  items: MainNavChild[];
};

export function SectionTabs({ items }: Props) {
  return (
    <nav className="section-tabs" aria-label="Abas da secao">
      {items.map((item) => (
        <NavLink
          key={item.key}
          className={({ isActive }) => `section-tab-link ${isActive ? "active" : ""}`}
          to={item.path}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
