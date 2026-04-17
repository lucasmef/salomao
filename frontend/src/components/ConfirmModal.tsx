import "./ConfirmModal.css";

type Props = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "danger" | "info";
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  tone = "info",
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null;

  return (
    <div className="confirm-overlay">
      <div className="confirm-modal-box">
        <div className="confirm-header">
          <h3 className={`confirm-title ${tone === "danger" ? "is-danger" : ""}`}>{title}</h3>
        </div>
        <div className="confirm-body">
          <p>{message}</p>
        </div>
        <div className="confirm-footer">
          <button className="secondary-button" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button 
            className={`primary-button ${tone === "danger" ? "danger-button" : ""}`} 
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
