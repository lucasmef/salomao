import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import styles from "./DropdownMenu.module.css";

export type DropdownItem = {
  label: ReactNode;
  onSelect: () => void;
  tone?: "default" | "danger";
  disabled?: boolean;
  hidden?: boolean;
};

type Props = {
  trigger: (state: { open: boolean; toggle: () => void; close: () => void; id: string }) => ReactNode;
  items: DropdownItem[];
  align?: "left" | "right";
  ariaLabel?: string;
};

export function DropdownMenu({ trigger, items, align = "right", ariaLabel }: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const close = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((v) => !v), []);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target && wrapRef.current && !wrapRef.current.contains(target)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const visible = items.filter((item) => !item.hidden);

  return (
    <div ref={wrapRef} className={styles.wrap}>
      {trigger({ open, toggle, close, id: menuId })}
      {open && visible.length > 0 && (
        <div role="menu" aria-label={ariaLabel} id={menuId} className={styles.menu} data-align={align}>
          {visible.map((item, index) => (
            <button
              key={index}
              type="button"
              role="menuitem"
              className={styles.item}
              data-tone={item.tone ?? "default"}
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
