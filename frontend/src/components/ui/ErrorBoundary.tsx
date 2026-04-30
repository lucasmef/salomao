import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorState } from "./ErrorState";
import { Button } from "./Button";

type Props = {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
};

type State = {
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (typeof console !== "undefined") {
      console.error("[ErrorBoundary]", error, info.componentStack);
    }
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) {
      return this.props.fallback(error, this.reset);
    }

    return (
      <div style={{ padding: "var(--space-8)", display: "flex", justifyContent: "center" }}>
        <ErrorState
          title="Algo quebrou ao renderizar esta tela"
          message={error.message || "Recarregue a página ou volte ao início."}
          actions={
            <>
              <Button variant="secondary" size="md" onClick={this.reset}>
                Tentar novamente
              </Button>
              <Button variant="primary" size="md" onClick={() => window.location.reload()}>
                Recarregar página
              </Button>
            </>
          }
        />
      </div>
    );
  }
}
