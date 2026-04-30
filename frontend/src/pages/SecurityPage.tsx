import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui";
import { formatDate } from "../lib/format";
import type {
  AuthUser,
  BackupRead,
  InstanceInfo,
  LinxSettings,
  LinxSettingsUpdatePayload,
  MfaSetup,
  MfaStatus,
  UserCredentialsUpdatePayload,
} from "../types";

type Props = {
  submitting: boolean;
  currentUser: AuthUser;
  users: AuthUser[];
  backups: BackupRead[];
  instanceInfo: InstanceInfo | null;
  linxSettings: LinxSettings | null;
  mfaStatus: MfaStatus | null;
  activeMfaSetup: MfaSetup | null;
  onCreateUser: (payload: Record<string, unknown>) => Promise<void>;
  onUpdateCredentials: (payload: UserCredentialsUpdatePayload) => Promise<void>;
  onUpdateLinxSettings: (payload: LinxSettingsUpdatePayload) => Promise<void>;
  onDeactivateUser: (userId: string) => Promise<void>;
  onCreateBackup: () => Promise<void>;
  onRestoreBackup: (file: File) => Promise<void>;
  onStartMfaEnrollment: () => Promise<void>;
  onConfirmMfaEnrollment: (code: string) => Promise<void>;
  onResetMfa: (userId: string) => Promise<void>;
  embedded?: boolean;
  view?: "all" | "users" | "backup" | "security";
};

export function SecurityPage({
  submitting,
  currentUser,
  users,
  backups,
  instanceInfo,
  linxSettings,
  mfaStatus,
  activeMfaSetup,
  onCreateUser,
  onUpdateCredentials,
  onUpdateLinxSettings,
  onDeactivateUser,
  onCreateBackup,
  onRestoreBackup,
  onStartMfaEnrollment,
  onConfirmMfaEnrollment,
  onResetMfa,
  embedded = false,
  view = "all",
}: Props) {
  const [userForm, setUserForm] = useState({
    full_name: "",
    email: "",
    password: "",
    role: "operador",
  });
  const [mfaCode, setMfaCode] = useState("");
  const [credentialsForm, setCredentialsForm] = useState({
    email: currentUser.email,
    password: "",
  });
  const [linxForm, setLinxForm] = useState({
    base_url: linxSettings?.base_url ?? "https://erp.microvix.com.br",
    username: linxSettings?.username ?? "",
    password: "",
    api_base_url: linxSettings?.api_base_url ?? "https://webapi.microvix.com.br/1.0/api/integracao",
    api_cnpj: linxSettings?.api_cnpj ?? "",
    api_key: "",
    sales_view_name: linxSettings?.sales_view_name ?? "FATURAMENTO SALOMAO",
    receivables_view_name: linxSettings?.receivables_view_name ?? "CREDIARIO SALOMAO",
    payables_view_name: linxSettings?.payables_view_name ?? "LANCAR NOTAS SALOMAO",
    auto_sync_enabled: linxSettings?.auto_sync_enabled ?? false,
    auto_sync_alert_email: linxSettings?.auto_sync_alert_email ?? "",
  });
  useEffect(() => {
    setCredentialsForm((current) => ({ ...current, email: currentUser.email }));
  }, [currentUser.email]);

  useEffect(() => {
    setLinxForm((current) => ({
      ...current,
      base_url: linxSettings?.base_url ?? "https://erp.microvix.com.br",
      username: linxSettings?.username ?? "",
      api_base_url: linxSettings?.api_base_url ?? "https://webapi.microvix.com.br/1.0/api/integracao",
      api_cnpj: linxSettings?.api_cnpj ?? "",
      sales_view_name: linxSettings?.sales_view_name ?? "FATURAMENTO SALOMAO",
      receivables_view_name: linxSettings?.receivables_view_name ?? "CREDIARIO SALOMAO",
      payables_view_name: linxSettings?.payables_view_name ?? "LANCAR NOTAS SALOMAO",
      auto_sync_enabled: linxSettings?.auto_sync_enabled ?? false,
      auto_sync_alert_email: linxSettings?.auto_sync_alert_email ?? "",
      password: "",
      api_key: "",
    }));
  }, [linxSettings]);

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreateUser(userForm);
    setUserForm({ full_name: "", email: "", password: "", role: "operador" });
  }

  async function handleConfirmMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onConfirmMfaEnrollment(mfaCode);
    setMfaCode("");
  }

  async function handleUpdateCredentials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onUpdateCredentials({
      email: credentialsForm.email,
      password: credentialsForm.password || undefined,
    });
    setCredentialsForm((current) => ({ ...current, password: "" }));
  }

  async function handleUpdateLinxSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onUpdateLinxSettings({
      base_url: linxForm.base_url,
      username: linxForm.username,
      password: linxForm.password || undefined,
      api_base_url: linxForm.api_base_url,
      api_cnpj: linxForm.api_cnpj || undefined,
      api_key: linxForm.api_key || undefined,
      sales_view_name: linxForm.sales_view_name,
      receivables_view_name: linxForm.receivables_view_name,
      payables_view_name: linxForm.payables_view_name,
      auto_sync_enabled: linxForm.auto_sync_enabled,
      auto_sync_alert_email: linxForm.auto_sync_alert_email || undefined,
    });
    setLinxForm((current) => ({ ...current, password: "", api_key: "" }));
  }

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Administração"
          title="Segurança e continuidade"
          description="Usuários, MFA e operação segura durante a transição para o ambiente online."
        />
      )}
      <section className="interactive-grid">
        {(view === "all" || view === "users") && (
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Sessão atual</p>
              <h3>Usuário autenticado</h3>
            </div>
            <div className="table-list">
              <div className="list-row">
                <div>
                  <strong>{currentUser.full_name}</strong>
                  <p>{currentUser.email}</p>
                </div>
                <span>{currentUser.role}</span>
              </div>
            </div>
          </article>
        )}

        {(view === "all" || view === "users" || view === "security") && (
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Meu acesso</p>
              <h3>Alterar login e senha</h3>
            </div>
            <form className="form-grid single" onSubmit={handleUpdateCredentials}>
              <label>
                Email de acesso
                <input
                  value={credentialsForm.email}
                  onChange={(event) => setCredentialsForm({ ...credentialsForm, email: event.target.value })}
                  required
                />
              </label>
              <label>
                Nova senha
                <input
                  type="password"
                  value={credentialsForm.password}
                  onChange={(event) => setCredentialsForm({ ...credentialsForm, password: event.target.value })}
                  placeholder="Deixe em branco para manter a atual"
                />
              </label>
              <Button type="submit" variant="primary" loading={submitting} disabled={submitting}>
                Salvar acesso
              </Button>
            </form>
          </article>
        )}

        {(view === "all" || view === "security") && currentUser.role === "admin" && (
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Integracao Linx</p>
              <h3>Credenciais e visoes</h3>
            </div>
            <form className="form-grid single" onSubmit={handleUpdateLinxSettings}>
              <label>
                URL base
                <input
                  value={linxForm.base_url}
                  onChange={(event) => setLinxForm({ ...linxForm, base_url: event.target.value })}
                  required
                />
              </label>
              <label>
                Usuario
                <input
                  value={linxForm.username}
                  onChange={(event) => setLinxForm({ ...linxForm, username: event.target.value })}
                  required
                />
              </label>
              <label>
                Senha
                <input
                  type="password"
                  value={linxForm.password}
                  onChange={(event) => setLinxForm({ ...linxForm, password: event.target.value })}
                  placeholder={linxSettings?.has_password ? "Deixe em branco para manter a atual" : ""}
                />
              </label>
              <label>
                URL API
                <input
                  value={linxForm.api_base_url}
                  onChange={(event) => setLinxForm({ ...linxForm, api_base_url: event.target.value })}
                  required
                />
              </label>
              <label>
                CNPJ API
                <input
                  value={linxForm.api_cnpj}
                  onChange={(event) => setLinxForm({ ...linxForm, api_cnpj: event.target.value })}
                  placeholder="Somente numeros"
                />
              </label>
              <label>
                Chave API
                <input
                  type="password"
                  value={linxForm.api_key}
                  onChange={(event) => setLinxForm({ ...linxForm, api_key: event.target.value })}
                  placeholder={linxSettings?.has_api_key ? "Deixe em branco para manter a atual" : ""}
                />
              </label>
              <label>
                Visao faturamento
                <input
                  value={linxForm.sales_view_name}
                  onChange={(event) => setLinxForm({ ...linxForm, sales_view_name: event.target.value })}
                  required
                />
              </label>
              <label>
                Visao faturas a receber
                <input
                  value={linxForm.receivables_view_name}
                  onChange={(event) => setLinxForm({ ...linxForm, receivables_view_name: event.target.value })}
                  required
                />
              </label>
              <label>
                Visao faturas a pagar
                <input
                  value={linxForm.payables_view_name}
                  onChange={(event) => setLinxForm({ ...linxForm, payables_view_name: event.target.value })}
                  required
                />
              </label>
              <label className="checkbox-field">
                <input
                  checked={linxForm.auto_sync_enabled}
                  onChange={(event) => setLinxForm({ ...linxForm, auto_sync_enabled: event.target.checked })}
                  type="checkbox"
                />
                Ativar sincronizacao automatica horaria da API Linx
              </label>
              <label>
                Email para aviso de falha
                <input
                  type="email"
                  value={linxForm.auto_sync_alert_email}
                  onChange={(event) => setLinxForm({ ...linxForm, auto_sync_alert_email: event.target.value })}
                  placeholder="financeiro@empresa.com"
                />
              </label>
              <div className="summary-list">
                <div className="summary-row">
                  <span>Senha cadastrada</span>
                  <strong>{linxSettings?.has_password ? "sim" : "nao"}</strong>
                </div>
                <div className="summary-row">
                  <span>Chave API cadastrada</span>
                  <strong>{linxSettings?.has_api_key ? "sim" : "nao"}</strong>
                </div>
                <div className="summary-row">
                  <span>Agendamento</span>
                  <strong>{linxSettings?.auto_sync_enabled ? "06h-22h de hora em hora" : "Inativo"}</strong>
                </div>
                <div className="summary-row">
                  <span>Ultima execucao</span>
                  <strong>{linxSettings?.auto_sync_last_run_at ? formatDate(linxSettings.auto_sync_last_run_at) : "-"}</strong>
                </div>
                <div className="summary-row">
                  <span>Status da ultima execucao</span>
                  <strong>{linxSettings?.auto_sync_last_status ?? "-"}</strong>
                </div>
              </div>
              {linxSettings?.auto_sync_last_error && (
                <p className="empty-state">
                  Ultima falha: {linxSettings.auto_sync_last_error}
                </p>
              )}
              <Button type="submit" variant="primary" loading={submitting} disabled={submitting}>
                Salvar configuracao Linx
              </Button>
            </form>
          </article>
        )}
      </section>

      {(view === "all" || view === "security") && (
        <section className="interactive-grid">
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">MFA TOTP</p>
              <h3>Autenticador do usuário atual</h3>
            </div>
            {!activeMfaSetup ? (
              <>
                <p className="supporting">
                  {mfaStatus?.enabled
                    ? "O MFA já está ativo para este usuário."
                    : "Ative o MFA agora para deixar a conta pronta para o ambiente online."}
                </p>
                <Button
                  type="button"
                  variant="primary"
                  loading={submitting}
                  disabled={submitting}
                  onClick={() => void onStartMfaEnrollment()}
                >
                  {mfaStatus?.enabled ? "Regenerar configuracao" : "Iniciar configuracao"}
                </Button>
              </>
            ) : (
              <form className="form-grid single" onSubmit={handleConfirmMfa}>
                <label>
                  Chave manual
                  <input readOnly value={activeMfaSetup.secret} />
                </label>
                <label>
                  URI de provisionamento
                  <textarea readOnly rows={3} value={activeMfaSetup.provisioning_uri} />
                </label>
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
                    value={mfaCode}
                  />
                </label>
                <Button type="submit" variant="primary" loading={submitting} disabled={submitting}>
                  Confirmar MFA
                </Button>
              </form>
            )}
          </article>
        </section>
      )}

      {(view === "all" || view === "users") && currentUser.role === "admin" && (
        <section className="interactive-grid">
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Usuários</p>
              <h3>Novo usuário local</h3>
            </div>
            <form className="form-grid" onSubmit={handleCreateUser}>
              <label>
                Nome
                <input value={userForm.full_name} onChange={(event) => setUserForm({ ...userForm, full_name: event.target.value })} required />
              </label>
              <label>
                Email
                <input value={userForm.email} onChange={(event) => setUserForm({ ...userForm, email: event.target.value })} required />
              </label>
              <label>
                Senha
                <input type="password" value={userForm.password} onChange={(event) => setUserForm({ ...userForm, password: event.target.value })} required />
              </label>
              <label>
                Perfil
                <select value={userForm.role} onChange={(event) => setUserForm({ ...userForm, role: event.target.value })}>
                  <option value="admin">Admin</option>
                  <option value="operador">Operador</option>
                  <option value="consulta">Consulta</option>
                </select>
              </label>
              <Button type="submit" variant="primary" loading={submitting} disabled={submitting}>
                Criar usuario
              </Button>
            </form>
          </article>

          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Acessos</p>
              <h3>{users.length} usuarios cadastrados</h3>
            </div>
            <div className="table-list">
              {users.map((user) => (
                <div key={user.id} className="entry-row">
                  <div>
                    <strong>{user.full_name}</strong>
                    <p>{user.email}</p>
                    <p>{user.is_active ? "ativo" : "inativo"} | MFA {user.mfa_enabled ? "ativo" : "inativo"}</p>
                  </div>
                  <div className="entry-aside">
                    <strong>{user.role}</strong>
                    {user.id !== currentUser.id && user.is_active && (
                      <Button type="button" variant="ghost" size="sm" disabled={submitting} onClick={() => void onDeactivateUser(user.id)}>
                        Desativar
                      </Button>
                    )}
                    {user.mfa_enabled && (
                      <Button type="button" variant="ghost" size="sm" disabled={submitting} onClick={() => void onResetMfa(user.id)}>
                        Resetar MFA
                      </Button>
                    )}
                  </div>
                </div>
              ))}
              {!users.length && <p className="empty-state">Nenhum outro usuario cadastrado.</p>}
            </div>
          </article>
        </section>
      )}

    </div>
  );
}
