import type { NavIconName } from "../types";

type Props = {
  name: NavIconName;
  className?: string;
};

export function NavIcon({ name, className }: Props) {
  const commonProps = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    className,
  };

  switch (name) {
    case "overview":
      return (
        <svg {...commonProps}>
          <path d="M4 12h6V4H4zM14 20h6v-8h-6zM14 10h6V4h-6zM4 20h6v-4H4z" />
        </svg>
      );
    case "finance":
      return (
        <svg {...commonProps}>
          <path d="M12 3v18" />
          <path d="M17 7.5c0-1.9-2.2-3.5-5-3.5S7 5.6 7 7.5 8.8 11 12 11s5 1.6 5 3.5S15.2 18 12 18s-5-1.6-5-3.5" />
        </svg>
      );
    case "operations":
      return (
        <svg {...commonProps}>
          <path d="M5 7h10" />
          <path d="m11 3 4 4-4 4" />
          <path d="M19 17H9" />
          <path d="m13 13-4 4 4 4" />
        </svg>
      );
    case "planning":
      return (
        <svg {...commonProps}>
          <path d="M4 19h16" />
          <path d="M6 15h3V8H6z" />
          <path d="M11 15h3V5h-3z" />
          <path d="M16 15h3v-6h-3z" />
        </svg>
      );
    case "imports":
      return (
        <svg {...commonProps}>
          <path d="M12 16V4" />
          <path d="m7 9 5-5 5 5" />
          <path d="M4 20h16" />
        </svg>
      );
    case "billing":
      return (
        <svg {...commonProps}>
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <path d="M8 9h8M8 13h5M8 17h3" />
        </svg>
      );
    case "reconciliation":
      return (
        <svg {...commonProps}>
          <path d="M7 7h6a4 4 0 0 1 0 8H9" />
          <path d="m7 11-4-4 4-4" />
          <path d="M17 17h-6a4 4 0 0 1 0-8h4" />
          <path d="m17 13 4 4-4 4" />
        </svg>
      );
    case "cashflow":
      return (
        <svg {...commonProps}>
          <path d="M4 18h16" />
          <path d="M7 15V9" />
          <path d="M12 15V6" />
          <path d="M17 15v-3" />
        </svg>
      );
    case "reports":
      return (
        <svg {...commonProps}>
          <path d="M5 19V5" />
          <path d="M19 19H5" />
          <path d="m8 15 3-3 2 2 4-5" />
        </svg>
      );
    case "security":
      return (
        <svg {...commonProps}>
          <path d="M12 3 5 6v6c0 4.4 2.9 7.9 7 9 4.1-1.1 7-4.6 7-9V6l-7-3Z" />
          <path d="M9.5 12.5 11 14l3.5-4" />
        </svg>
      );
    default:
      return null;
  }
}
