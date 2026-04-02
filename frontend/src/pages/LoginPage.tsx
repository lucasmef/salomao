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
      <section className="login-card">
        <img alt="Salomao" className="login-brand-logo" src={salomaoLogo} />
        <p className="eyebrow">Salomão</p>
        <h1>Operação financeira com transição segura entre desktop local e ambiente online</h1>
        <p className="supporting">
          Entre com o usuário local para acessar importações, lançamentos, fluxo de caixa, DRE, DRO e trilha de
          segurança.
        </p>

        {!challenge && (
          <form autoComplete="on" className="form-grid single" onSubmit={handleSubmit}>
            <label>
              Email
              <input
                autoCapitalize="none"
                autoComplete="username"
                autoCorrect="off"
                inputMode="email"
                name="username"
                spellCheck={false}
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              Senha
              <input
                autoComplete="current-password"
                name="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button className="primary-button" disabled={loading} type="submit">
              {loading ? "Entrando..." : "Entrar no sistema"}
            </button>
          </form>
        )}

        {challenge && (
          <form className="form-grid single" onSubmit={handleMfaSubmit}>
            <div className="panel-card">
              <div className="panel-heading">
                <p className="eyebrow">Segurança adicional</p>
                <h3>{challenge.status === "mfa_setup_required" ? "Configurar MFA TOTP" : "Validar MFA TOTP"}</h3>
              </div>
              <p className="supporting">
                Usuário: <strong>{challenge.user.email}</strong>
              </p>
              {challenge.status === "mfa_setup_required" && challenge.mfaSetup && (
                <>
                  <p className="supporting">
                    Cadastre a chave abaixo no app autenticador e depois informe o código gerado para concluir a entrada.
                  </p>
                  <label>
                    Chave manual
                    <input readOnly value={challenge.mfaSetup.secret} />
                  </label>
                  <label>
                    URI de provisionamento
                    <textarea readOnly rows={3} value={challenge.mfaSetup.provisioning_uri} />
                  </label>
                </>
              )}
              <label>
                Código do autenticador
                <input
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  maxLength={6}
                  name="one-time-code"
                  onChange={(event) => setMfaCode(event.target.value)}
                  pattern="[0-9]*"
                  placeholder="000000"
                  required
                  value={mfaCode}
                />
              </label>
              <label className="checkbox-line compact-inline">
                <input
                  checked={rememberDevice}
                  onChange={(event) => setRememberDevice(event.target.checked)}
                  type="checkbox"
                />
                Não pedir MFA novamente neste dispositivo por 15 dias
              </label>
              <div className="action-row">
                <button className="primary-button" disabled={loading} type="submit">
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
    </div>
  );
}
