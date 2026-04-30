import styles from "./PeriodChips.module.css";

export type PeriodKey = string;

type Option = {
  key: PeriodKey;
  label: string;
};

type Props = {
  options: Option[];
  value: PeriodKey;
  onChange: (key: PeriodKey) => void;
  customLabel?: string;
  onCustomClick?: () => void;
};

export function PeriodChips({ options, value, onChange, customLabel, onCustomClick }: Props) {
  return (
    <div className={styles.group} role="tablist" aria-label="Período">
      {options.map((opt) => {
        const active = opt.key === value;
        return (
          <button
            key={opt.key}
            type="button"
            role="tab"
            aria-selected={active}
            className={[styles.chip, active ? styles.active : ""].filter(Boolean).join(" ")}
            onClick={() => onChange(opt.key)}
          >
            {opt.label}
          </button>
        );
      })}
      {onCustomClick && (
        <button type="button" className={[styles.chip, styles.custom].join(" ")} onClick={onCustomClick}>
          <span aria-hidden="true">+</span>
          {customLabel ?? "Personalizado"}
        </button>
      )}
    </div>
  );
}
