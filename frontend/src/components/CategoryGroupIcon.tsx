export type CategoryGroupIconName =
  | "tag"
  | "cart"
  | "home"
  | "people"
  | "bank"
  | "truck"
  | "receipt"
  | "chart"
  | "briefcase"
  | "cash"
  | "card";

export type CategoryGroupIconConfig = {
  icon?: CategoryGroupIconName;
  image?: string;
};

export const CATEGORY_GROUP_ICON_STORAGE_KEY = "category-group-icons";

export const categoryGroupIconOptions: { value: CategoryGroupIconName; label: string }[] = [
  { value: "tag", label: "Padrao" },
  { value: "cart", label: "Compras" },
  { value: "home", label: "Casa" },
  { value: "people", label: "Pessoas" },
  { value: "bank", label: "Banco" },
  { value: "truck", label: "Logistica" },
  { value: "receipt", label: "Fiscal" },
  { value: "chart", label: "Resultado" },
  { value: "briefcase", label: "Servicos" },
  { value: "cash", label: "Dinheiro" },
  { value: "card", label: "Cartao" },
];

export function makeCategoryGroupIconKey(entryKind: string | null | undefined, group: string | null | undefined) {
  return `${entryKind || "any"}::${String(group ?? "").trim().toLowerCase()}`;
}

export function readCategoryGroupIconMap() {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    return JSON.parse(window.localStorage.getItem(CATEGORY_GROUP_ICON_STORAGE_KEY) ?? "{}") as Record<
      string,
      CategoryGroupIconConfig
    >;
  } catch {
    return {};
  }
}

export function writeCategoryGroupIconConfig(key: string, config: CategoryGroupIconConfig) {
  if (typeof window === "undefined") {
    return;
  }
  const current = readCategoryGroupIconMap();
  current[key] = config;
  window.localStorage.setItem(CATEGORY_GROUP_ICON_STORAGE_KEY, JSON.stringify(current));
}

function iconPath(icon: CategoryGroupIconName) {
  switch (icon) {
    case "cart":
      return "M2 3h1.2l1.2 6.2a1.6 1.6 0 0 0 1.6 1.3h5.2a1.6 1.6 0 0 0 1.5-1.1L14 5H4.2M6 13.2h.1M12 13.2h.1";
    case "home":
      return "M2.5 7.2 8 2.8l5.5 4.4M4 6.8v6h3V9.6h2v3.2h3v-6";
    case "people":
      return "M6.5 7.2a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4ZM2.5 13c.6-2.2 2-3.3 4-3.3s3.4 1.1 4 3.3M11 7.2a1.8 1.8 0 1 0 0-3.6M11.8 9.9c1 .4 1.7 1.4 2 3.1";
    case "bank":
      return "M2.5 5.5 8 2.5l5.5 3H2.5ZM4 7v5M7 7v5M10 7v5M13 7v5M2.8 13.5h10.4";
    case "truck":
      return "M2.5 4h7v6h-7V4Zm7 2h2.4l1.6 2.2V10h-4V6ZM5 12.5a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4Zm6.5 0a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4Z";
    case "receipt":
      return "M4 2.5h8v11l-1.6-1-1.6 1-1.6-1-1.6 1-1.6-1v-10Zm2 3h4M6 8h4M6 10.5h2.5";
    case "chart":
      return "M3 13h10M4.5 11V7M8 11V3M11.5 11V5.5";
    case "briefcase":
      return "M3 5h10v7.5H3V5Zm3-1.5h4V5H6V3.5Zm-3 4h10";
    case "cash":
      return "M2.5 5h11v6h-11V5Zm2 1.5h7M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z";
    case "card":
      return "M2.5 4.5h11v7h-11v-7Zm0 2.5h11M4.5 9.8h2";
    default:
      return "M2.5 3.8A1.3 1.3 0 0 1 3.8 2.5h3.5c.3 0 .6.1.9.4l4.9 4.9c.5.5.5 1.3 0 1.8l-3.5 3.5c-.5.5-1.3.5-1.8 0L2.9 8.2c-.3-.3-.4-.6-.4-.9V3.8Zm2.8.8h.1";
  }
}

export function CategoryGroupIcon({
  config,
  group,
  className = "",
}: {
  config?: CategoryGroupIconConfig;
  group?: string | null;
  className?: string;
}) {
  if (config?.image) {
    return <img alt="" className={className} src={config.image} />;
  }
  const icon = config?.icon ?? "tag";
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 16 16">
      <path d={iconPath(icon)} fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
      {icon === "tag" && group ? <title>{group}</title> : null}
    </svg>
  );
}
