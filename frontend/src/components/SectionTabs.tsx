import { NavLink } from "react-router-dom";

import type { MainNavChild } from "../data/navigation";

type Props = {
  items: MainNavChild[];
};

function groupItems(items: MainNavChild[]) {
  const groups: Array<{ label: string | null; items: MainNavChild[] }> = [];

  for (const item of items) {
    const label = item.group ?? null;
    const currentGroup = groups[groups.length - 1];
    if (currentGroup && currentGroup.label === label) {
      currentGroup.items.push(item);
      continue;
    }
    groups.push({ label, items: [item] });
  }

  return groups;
}

export function SectionTabs({ items }: Props) {
  const groupedItems = groupItems(items);

  return (
    <nav className="section-tabs" aria-label="Abas da secao">
      {groupedItems.map((group, index) => (
        <div className="section-tab-group" key={`${group.label ?? "default"}-${index}`}>
          {group.label ? <span className="section-tab-group-label">{group.label}</span> : null}
          <div className="section-tab-group-links">
            {group.items.map((item) => (
              <NavLink
                key={item.key}
                className={({ isActive }) => `section-tab-link ${isActive ? "active" : ""}`}
                to={item.path}
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}
