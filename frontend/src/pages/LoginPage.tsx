import { FormEvent, useEffect, useState } from "react";

import salomaoLogo from "../assets/salomao-logo.png";
import type { AuthUser, MfaSetup } from "../types";

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

const highlights = ["Fluxo de caixa vivo", "Cobranca integrada", "Governanca com auditoria"];

const dashboardKpis = [
  { label: "Caixa projetado", value: "R$ 412 mil", tone: "primary" },
  { label: "Recebiveis", value: "128 titulos", tone: "neutral" },
  { label: "Atrasos criticos", value: "7 clientes", tone: "warning" },
];

const dashboardRows = [
  { client: "Clinica Aurora", status: "Atrasado", amount: "R$ 18.420" },
  { client: "Grupo Vértice", status: "Pago", amount: "R$ 42.900" },
  { client: "Orto Prime", status: "Em aberto", amount: "R$ 9.870" },
];

const proofPoints = ["DRE e DRO", "Conciliacao", "Boletos", "Auditoria"];

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
    if (!challenge) {
      return;
    }
    if (challenge.status === "mfa_setup_required") {
      await onConfirmMfaSetup(mfaCode, rememberDevice);
      return;
    }
    await onVerifyMfa(mfaCode, rememberDevice);
  }

  return (
    <div className="login-shell">
      <div className="login-backdrop" aria-hidden="true">
        <span className="login-orb login-orb-primary" />
        <span className="login-orb login-orb-secondary" />
        <span className="login-grid" />
      </div>

      <section className="login-landing">
        <div className="login-hero">
          <div className="login-brand-row">
            <img alt="Salomao" className="login-brand-logo" src={salomaoLogo} />
            <div className="login-brand-copy">
              <p className="eyebrow">Sistema Salomao</p>
              <span>Financeiro, cobranca e governanca operacional</span>
            </div>
          </div>

          <div className="login-hero-copy">
            <h1>Controle financeiro com cara de produto, nao de tela fria de sistema.</h1>
            <p className="supporting">
              O Salomao organiza caixa, cobranca, conciliacao e relatorios em uma operacao visual, direta e pronta para
              uso diario.
            </p>
          </div>

          <div className="login-highlight-list">
            {highlights.map((item) => (
              <div className="login-highlight-item" key={item}>
                <span className="login-highlight-bullet" aria-hidden="true" />
                <strong>{item}</strong>
              </div>
            ))}
          </div>

          <div className="login-visual-stage">
            <div className="login-dashboard-window">
              <div className="login-dashboard-topbar">
                <div className="login-dashboard-dots">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="login-dashboard-title">Painel financeiro Salomao</div>
              </div>

              <div className="login-dashboard-body">
                <aside className="login-dashboard-sidebar">
                  <span className="is-active">Overview</span>
                  <span>Cobranca</span>
                  <span>Fluxo</span>
                  <span>Relatorios</span>
                </aside>

                <div className="login-dashboard-main">
                  <div className="login-dashboard-kpis">
                    {dashboardKpis.map((item) => (
                      <article className={`login-dashboard-kpi is-${item.tone}`.trim()} key={item.label}>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </article>
                    ))}
                  </div>

                  <div className="login-dashboard-grid">
                    <section className="login-dashboard-chart">
                      <div className="login-chart-bars" aria-hidden="true">
                        <span style={{ height: "44%" }} />
                        <span style={{ height: "63%" }} />
                        <span style={{ height: "57%" }} />
                        <span style={{ height: "78%" }} />
                        <span style={{ height: "72%" }} />
                        <span style={{ height: "88%" }} />
                        <span style={{ height: "68%" }} />
                      </div>
                    </section>

                    <section className="login-dashboard-list">
                      {dashboardRows.map((row) => (
                        <article className="login-dashboard-row" key={row.client}>
                          <div>
                            <strong>{row.client}</strong>
                            <span>{row.status}</span>
                          </div>
                          <b>{row.amount}</b>
                        </article>
                      ))}
                    </section>
                  </div>
                </div>
              </div>
            </div>

            <article className="login-floating-card login-floating-card-primary">
              <span>Fluxo de caixa</span>
              <strong>+12,4%</strong>
              <small>comparado ao fechamento anterior</small>
            </article>

            <article className="login-floating-card login-floating-card-secondary">
              <span>Cobranca</span>
              <strong>Inter + avulso</strong>
              <small>operacao centralizada</small>
            </article>
          </div>

          <div className="login-proof-strip">
            {proofPoints.map((item) => (
              <span className="login-proof-chip" key={item}>
                {item}
              </span>
            ))}
          </div>
        </div>

        <section className="login-panel">
          <div className="login-panel-header">
            <p className="eyebrow">{challenge ? "Verificacao segura" : "Acesso ao sistema"}</p>
            <h2>{challenge ? "Validar identidade" : "Entrar na plataforma"}</h2>
            <p className="supporting">
              {challenge
                ? "Confirme o codigo do autenticador para concluir a entrada com seguranca."
                : "Use seu usuario local para abrir a operacao e continuar do ponto em que parou."}
            </p>
          </div>

          {!challenge ? (
            <form autoComplete="on" className="form-grid single login-form-grid" onSubmit={handleSubmit}>
              <label>
                Email
                <input
                  autoCapitalize="none"
                  autoComplete="username"
                  autoCorrect="off"
                  inputMode="email"
                  name="username"
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  spellCheck={false}
                  type="email"
                  value={email}
                />
              </label>
              <label>
                Senha
                <input
                  autoComplete="current-password"
                  name="password"
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type="password"
                  value={password}
                />
              </label>
              <button className="primary-button login-submit-button" disabled={loading} type="submit">
                {loading ? "Entrando..." : "Entrar no sistema"}
              </button>
            </form>
          ) : (
            <form className="form-grid single login-form-grid" onSubmit={handleMfaSubmit}>
              <div className="login-mfa-card">
                <div className="login-mfa-copy">
                  <strong>{challenge.status === "mfa_setup_required" ? "Configurar MFA TOTP" : "Validar MFA TOTP"}</strong>
                  <span>
                    Usuario: <b>{challenge.user.email}</b>
                  </span>
                </div>

                {challenge.status === "mfa_setup_required" && challenge.mfaSetup ? (
                  <div className="login-mfa-setup">
                    <p className="supporting">
                      Cadastre a chave abaixo no app autenticador e informe o codigo gerado para concluir a entrada.
                    </p>
                    <label>
                      Chave manual
                      <input readOnly value={challenge.mfaSetup.secret} />
                    </label>
                    <label>
                      URI de provisionamento
                      <textarea readOnly rows={3} value={challenge.mfaSetup.provisioning_uri} />
                    </label>
                  </div>
                ) : null}

                <label>
                  Codigo do autenticador
                  <input
                    autoComplete="one-time-code"
                    inputMode="numeric"
                    maxLength={6}
                    name="one-time-code"
                    onChange={(event) => setMfaCode(event.target.value)}
                    pattern="[0-9]*"
                    placeholder="000000"
                    required
                    type="text"
                    value={mfaCode}
                  />
                </label>

                <label className="checkbox-line compact-inline login-remember-line">
                  <input
                    checked={rememberDevice}
                    onChange={(event) => setRememberDevice(event.target.checked)}
                    type="checkbox"
                  />
                  Nao pedir MFA novamente neste dispositivo por 15 dias
                </label>

                <div className="action-row">
                  <button className="primary-button login-submit-button" disabled={loading} type="submit">
                    {loading
                      ? "Validando..."
                      : challenge.status === "mfa_setup_required"
                        ? "Ativar MFA e entrar"
                        : "Validar acesso"}
                  </button>
                  <button className="ghost-button" disabled={loading} onClick={onCancelChallenge} type="button">
                    Voltar
                  </button>
                </div>
              </div>
            </form>
          )}
        </section>
      </section>
    </div>
  );
}
