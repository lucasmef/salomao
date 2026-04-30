import { FormEvent, useEffect, useState } from "react";
import { Button, Field, Input } from "../components/ui";
import salomaoLogo from "../assets/salomao-logo.png";
import type { AuthUser, MfaSetup } from "../types";
import "./LoginPage.css";

type PendingChallenge = {
  status: "mfa_required" | "mfa_setup_required";
  pendingToken: string;
  user: AuthUser;
  mfaSetup: MfaSetup | null;
};

type Props = {
  loading: boolean;
  challenge: PendingChallenge | null;
  onLogin: (email: string, password: string) => Promise<void>;
  onVerifyMfa: (code: string, rememberDevice: boolean) => Promise<void>;
  onConfirmMfaSetup: (code: string, rememberDevice: boolean) => Promise<void>;
  onCancelChallenge: () => void;
};

export function LoginPage({ loading, challenge, onLogin, onVerifyMfa, onConfirmMfaSetup, onCancelChallenge }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [rememberDevice, setRememberDevice] = useState(false);

  useEffect(() => {
    setMfaCode("");
    setRememberDevice(false);
  }, [challenge?.pendingToken]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onLogin(email, password);
  }

  async function handleMfaSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!challenge) return;
    if (challenge.status === "mfa_setup_required") {
      await onConfirmMfaSetup(mfaCode, rememberDevice);
      return;
    }
    await onVerifyMfa(mfaCode, rememberDevice);
  }

  return (
    <div className="landing-shell">
      <div className="landing-backdrop">
        <div className="landing-grid" />
      </div>

      <header className="landing-nav">
        <div className="landing-logo">
          <img alt="Salomao Logo" src={salomaoLogo} />
          <span className="landing-logo-text">Salomão</span>
        </div>
      </header>

      <main className="landing-main">
        <section className="hero-content">
          <span className="hero-eyebrow">Plataforma de Gestão Inteligente</span>
          <h1 className="hero-title">
            Domine suas <span>finanças</span> com inteligência e clareza.
          </h1>
          <p className="hero-description">
            O Salomão transforma a complexidade financeira em uma operação visual, direta e automatizada. 
            Fluxo de caixa vivo, cobrança inteligente e governança em um só lugar.
          </p>
        </section>

        <section className="landing-auth-panel">
          <div className="auth-card">
            <div className="auth-header">
              <h2>{challenge ? "Verificação" : "Boas-vindas"}</h2>
              <p>
                {challenge
                  ? "Sua conta está protegida por MFA. Por favor, valide sua identidade."
                  : "Acesse sua conta para gerenciar sua operação."}
              </p>
            </div>

            {!challenge ? (
              <form className="landing-form" onSubmit={handleSubmit}>
                <Field label="Email" htmlFor="email" required>
                  {(id) => (
                    <Input
                      autoCapitalize="none"
                      autoComplete="username"
                      className="landing-input"
                      id={id}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="exemplo@empresa.com"
                      required
                      type="email"
                      value={email}
                    />
                  )}
                </Field>
                <Field label="Senha" htmlFor="password" required>
                  {(id) => (
                    <Input
                      autoComplete="current-password"
                      className="landing-input"
                      id={id}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="********"
                      required
                      type="password"
                      value={password}
                    />
                  )}
                </Field>
                <Button className="landing-submit" disabled={loading} loading={loading} size="md" type="submit">
                  {loading ? "Entrando..." : "Acessar Sistema"}
                </Button>
              </form>
            ) : (
              <form className="landing-form" onSubmit={handleMfaSubmit}>
                <div className="mfa-container">
                  <div className="mfa-info">
                    Identidade: <b>{challenge.user.email}</b>
                  </div>

                  {challenge.status === "mfa_setup_required" && challenge.mfaSetup && (
                    <div className="mfa-setup-box">
                      <p>Ative o MFA escaneando ou inserindo a chave:</p>
                      <code>{challenge.mfaSetup.secret}</code>
                    </div>
                  )}

                  <Field label="Código do autenticador" required>
                    {(id) => (
                      <Input
                        autoComplete="one-time-code"
                        className="landing-input"
                        id={id}
                        inputMode="numeric"
                        maxLength={6}
                        onChange={(e) => setMfaCode(e.target.value)}
                        placeholder="000000"
                        required
                        type="text"
                        value={mfaCode}
                      />
                    )}
                  </Field>

                  <label className="remember-device">
                    <input
                      checked={rememberDevice}
                      onChange={(e) => setRememberDevice(e.target.checked)}
                      type="checkbox"
                    />
                    Lembrar deste dispositivo por 15 dias
                  </label>

                  <div className="mfa-actions">
                    <Button className="landing-submit" disabled={loading} loading={loading} size="md" type="submit">
                      {loading ? "Validando..." : "Confirmar"}
                    </Button>
                    <Button
                      className="landing-secondary"
                      disabled={loading}
                      onClick={onCancelChallenge}
                      size="md"
                      type="button"
                      variant="secondary"
                    >
                      Voltar
                    </Button>
                  </div>
                </div>
              </form>
            )}
          </div>
        </section>
      </main>

      <div className="features-strip">
        <div className="feature-pill"><span /> Fluxo de Caixa Real-time</div>
        <div className="feature-pill"><span /> Cobrança Automatizada</div>
        <div className="feature-pill"><span /> Governança & Auditoria</div>
        <div className="feature-pill"><span /> DRE & DRO Precisos</div>
      </div>

      <footer className="landing-footer">
        &copy; {new Date().getFullYear()} Salomão Gestão Financeira. Todos os direitos reservados.
      </footer>
    </div>
  );
}
