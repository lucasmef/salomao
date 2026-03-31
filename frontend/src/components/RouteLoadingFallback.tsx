import { useEffect } from "react";

type Props = {
  onVisibilityChange?: (visible: boolean) => void;
};

export function RouteLoadingFallback({ onVisibilityChange }: Props) {
  useEffect(() => {
    onVisibilityChange?.(true);
    return () => onVisibilityChange?.(false);
  }, [onVisibilityChange]);

  return (
    <div className="route-loading-fallback" role="status" aria-live="polite">
      <div className="route-loading-card">
        <span className="route-loading-kicker">Lazy load ativo</span>
        <strong>Carregando módulo</strong>
        <p>Estamos preparando esta área e atualizando os dados necessários.</p>
        <div aria-hidden="true" className="route-loading-bar">
          <span />
        </div>
      </div>
    </div>
  );
}
