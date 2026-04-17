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
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    className,
  };

  switch (name) {
    case "overview":
      return (
        <svg {...commonProps}>
          <rect width="7" height="9" x="3" y="3" rx="1" />
          <rect width="7" height="5" x="14" y="3" rx="1" />
          <rect width="7" height="9" x="14" y="12" rx="1" />
          <rect width="7" height="5" x="3" y="16" rx="1" />
        </svg>
      );
    case "finance":
      return (
        <svg {...commonProps}>
          <line x1="12" x2="12" y1="2" y2="22" />
          <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
        </svg>
      );
    case "operations":
      return (
        <svg {...commonProps}>
          <path d="m16 10 4 4-4 4" />
          <path d="m8 14-4-4 4-4" />
          <path d="M4 10h16" />
          <path d="M20 14h-7" />
          <path d="M13 14h-7" />
        </svg>
      );
    case "planning":
      return (
        <svg {...commonProps}>
          <path d="M16 20V4" />
          <path d="M12 20V10" />
          <path d="M8 20v-4" />
          <path d="M4 20v-2" />
        </svg>
      );
    case "imports":
      return (
        <svg {...commonProps}>
          <path d="M12 3v14" />
          <path d="m16 13-4 4-4-4" />
          <path d="M4 21h16" />
        </svg>
      );
    case "billing":
      return (
        <svg {...commonProps}>
          <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
          <path d="M15 2H9a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1Z" />
          <path d="M8 11h8" />
          <path d="M8 16h5" />
        </svg>
      );
    case "reconciliation":
      return (
        <svg {...commonProps}>
          <path d="M20 10c0-4.4-3.6-8-8-8s-8 3.6-8 8 3.6 8 8 8h8" />
          <path d="m16 14 4 4-4 4" />
        </svg>
      );
    case "cashflow":
      return (
        <svg {...commonProps}>
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
      );
    case "reports":
      return (
        <svg {...commonProps}>
          <path d="M12 20V10" />
          <path d="M18 20V4" />
          <path d="M6 20v-4" />
        </svg>
      );
    case "security":
      return (
        <svg {...commonProps}>
          <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      );
    default:
      return null;
  }
}
