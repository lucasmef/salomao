import { FormEvent, useEffect, useState } from "react";
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
        <div className="landing-orb orb-1" />
        <div className="landing-orb orb-2" />
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
                <div className="form-group">
                  <label className="form-label" htmlFor="email">Email</label>
                  <input
                    autoCapitalize="none"
                    autoComplete="username"
                    className="form-input"
                    id="email"
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="exemplo@empresa.com"
                    required
                    type="email"
                    value={email}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="password">Senha</label>
                  <input
                    autoComplete="current-password"
                    className="form-input"
                    id="password"
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    type="password"
                    value={password}
                  />
                </div>
                <button className="submit-btn" disabled={loading} type="submit">
                  {loading ? "Entrando..." : "Acessar Sistema"}
                </button>
              </form>
            ) : (
              <form className="landing-form" onSubmit={handleMfaSubmit}>
                <div className="mfa-container">
                  <div className="mfa-info">
                    Identidade: <b>{challenge.user.email}</b>
                  </div>

                  {challenge.status === "mfa_setup_required" && challenge.mfaSetup && (
                    <div className="mfa-setup-box">
                      <p style={{ fontSize: '0.8rem', marginBottom: '8px' }}>Ative o MFA escaneando ou inserindo a chave:</p>
                      <code>{challenge.mfaSetup.secret}</code>
                    </div>
                  )}

                  <div className="form-group">
                    <label className="form-label">Código do Autenticador</label>
                    <input
                      autoComplete="one-time-code"
                      className="form-input"
                      inputMode="numeric"
                      maxLength={6}
                      onChange={(e) => setMfaCode(e.target.value)}
                      placeholder="000000"
                      required
                      type="text"
                      value={mfaCode}
                    />
                  </div>

                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--lp-text-muted)' }}>
                    <input
                      checked={rememberDevice}
                      onChange={(e) => setRememberDevice(e.target.checked)}
                      type="checkbox"
                    />
                    Lembrar deste dispositivo por 15 dias
                  </label>

                  <div style={{ display: 'flex', gap: '12px' }}>
                    <button className="submit-btn" disabled={loading} style={{ flex: 1 }} type="submit">
                      {loading ? "Validando..." : "Confirmar"}
                    </button>
                    <button 
                      className="submit-btn" 
                      disabled={loading} 
                      onClick={onCancelChallenge} 
                      style={{ background: 'transparent', border: '1px solid var(--lp-glass-border)', flex: 0.5 }} 
                      type="button"
                    >
                      Voltar
                    </button>
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
