type Props = {
  onClick: () => void;
  disabled?: boolean;
  className?: string;
};

export function ModalCloseButton({ onClick, disabled = false, className = "" }: Props) {
  return (
    <button
      aria-label="Fechar modal"
      className={`modal-close-button ${className}`.trim()}
      disabled={disabled}
      onClick={onClick}
      title="Fechar"
      type="button"
    >
      <svg aria-hidden="true" viewBox="0 0 16 16">
        <path d="M4 4l8 8M12 4 4 12" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    </button>
  );
}
