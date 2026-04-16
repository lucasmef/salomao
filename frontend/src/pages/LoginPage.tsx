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

const highlights = [
  "Fluxo de caixa, DRE e DRO no mesmo painel",
  "Importacoes e conciliacao com trilha operacional",
  "Cobranca, boletos e controle de recebiveis em um fluxo unico",
];

const pillars = [
  {
    title: "Operacao viva",
    body: "Acompanhe entradas, saidas e cobranca com leitura rapida para a rotina do escritorio.",
  },
  {
    title: "Controle financeiro",
    body: "Centralize caixa, faturamento, conciliacao, relatorios gerenciais e governanca em uma unica camada.",
  },
  {
    title: "Seguranca aplicada",
    body: "Acesso com MFA, trilha de auditoria e separacao clara entre processos locais e online.",
  },
];

const statCards = [
  { value: "Financeiro", label: "operacao centralizada" },
  { value: "Cobranca", label: "visao consolidada" },
  { value: "Auditoria", label: "seguranca rastreavel" },
];

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
            <h1>Uma entrada unica para comandar a operacao financeira do Salomao.</h1>
            <p className="supporting">
              Acesse caixa, cobranca, conciliacao, auditoria e relatorios em uma experiencia pensada para decisao
              rapida e rotina pesada.
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

          <div className="login-stat-grid">
            {statCards.map((card) => (
              <article className="login-stat-card" key={card.value}>
                <strong>{card.value}</strong>
                <span>{card.label}</span>
              </article>
            ))}
          </div>

          <div className="login-pillar-grid">
            {pillars.map((pillar) => (
              <article className="login-pillar-card" key={pillar.title}>
                <strong>{pillar.title}</strong>
                <p>{pillar.body}</p>
              </article>
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
