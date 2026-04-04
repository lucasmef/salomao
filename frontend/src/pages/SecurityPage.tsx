import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { formatBytes, formatDate } from "../lib/format";
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
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [credentialsForm, setCredentialsForm] = useState({
    email: currentUser.email,
    password: "",
  });
  const [linxForm, setLinxForm] = useState({
    base_url: linxSettings?.base_url ?? "https://erp.microvix.com.br",
    username: linxSettings?.username ?? "",
    password: "",
    sales_view_name: linxSettings?.sales_view_name ?? "FATURAMENTO SALOMAO",
    receivables_view_name: linxSettings?.receivables_view_name ?? "CREDIARIO SALOMAO",
    auto_sync_enabled: linxSettings?.auto_sync_enabled ?? false,
    auto_sync_alert_email: linxSettings?.auto_sync_alert_email ?? "",
  });
  const isLocalBackupMode = (instanceInfo?.backup_mode ?? "local-file") === "local-file";

  useEffect(() => {
    setCredentialsForm((current) => ({ ...current, email: currentUser.email }));
  }, [currentUser.email]);

  useEffect(() => {
    setLinxForm((current) => ({
      ...current,
      base_url: linxSettings?.base_url ?? "https://erp.microvix.com.br",
      username: linxSettings?.username ?? "",
      sales_view_name: linxSettings?.sales_view_name ?? "FATURAMENTO SALOMAO",
      receivables_view_name: linxSettings?.receivables_view_name ?? "CREDIARIO SALOMAO",
      auto_sync_enabled: linxSettings?.auto_sync_enabled ?? false,
      auto_sync_alert_email: linxSettings?.auto_sync_alert_email ?? "",
      password: "",
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
      sales_view_name: linxForm.sales_view_name,
      receivables_view_name: linxForm.receivables_view_name,
      auto_sync_enabled: linxForm.auto_sync_enabled,
      auto_sync_alert_email: linxForm.auto_sync_alert_email || undefined,
    });
    setLinxForm((current) => ({ ...current, password: "" }));
  }

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Administração"
          title="Segurança e continuidade"
          description="Usuários, MFA, backup local e operação segura durante a transição para o ambiente online."
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
              <button className="primary-button" disabled={submitting} type="submit">
                Salvar acesso
              </button>
            </form>
          </article>
        )}

        {(view === "all" || view === "backup") && (
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Backup</p>
              <h3>{isLocalBackupMode ? "Proteção da base local" : "Backups operacionais do servidor"}</h3>
            </div>
            {isLocalBackupMode ? (
              <>
                <div className="action-row">
                  <button className="primary-button" disabled={submitting} onClick={() => void onCreateBackup()} type="button">
                    Criar backup agora
                  </button>
                </div>
                <div className="upload-box">
                  <input type="file" accept=".sqlite3,.db" onChange={(event) => setRestoreFile(event.target.files?.[0] ?? null)} />
                  <button
                    className="ghost-button"
                    disabled={submitting || !restoreFile}
                    onClick={() => restoreFile && void onRestoreBackup(restoreFile)}
                    type="button"
                  >
                    Restaurar backup
                  </button>
                </div>
              </>
            ) : (
              <p className="empty-state">
                No modo servidor, os backups do PostgreSQL são operacionais e feitos pelos scripts dedicados, fora da UI.
              </p>
            )}
          </article>
        )}

        {view === "security" && (
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Segurança</p>
              <h3>Políticas e endurecimento</h3>
            </div>
            <div className="summary-list">
              <div className="summary-row"><span>Modo da aplicação</span><strong>{instanceInfo?.app_mode ?? "-"}</strong></div>
              <div className="summary-row"><span>Banco ativo</span><strong>{instanceInfo?.database_backend ?? "-"}</strong></div>
              <div className="summary-row"><span>MFA obrigatório</span><strong>{mfaStatus?.required ? "sim" : "não"}</strong></div>
              <div className="summary-row"><span>MFA do usuário atual</span><strong>{mfaStatus?.enabled ? "ativo" : "inativo"}</strong></div>
            </div>
          </article>
        )}

        {view === "security" && currentUser.role === "admin" && (
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
              <label className="checkbox-field">
                <input
                  checked={linxForm.auto_sync_enabled}
                  onChange={(event) => setLinxForm({ ...linxForm, auto_sync_enabled: event.target.checked })}
                  type="checkbox"
                />
                Ativar sincronizacao automatica diaria do Linx
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
                  <span>Agendamento</span>
                  <strong>{linxSettings?.auto_sync_enabled ? "Diario apos 22h" : "Inativo"}</strong>
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
              <button className="primary-button" disabled={submitting} type="submit">
                Salvar configuracao Linx
              </button>
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
                <button className="primary-button" disabled={submitting} onClick={() => void onStartMfaEnrollment()} type="button">
                  {mfaStatus?.enabled ? "Regenerar configuracao" : "Iniciar configuracao"}
                </button>
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
                <button className="primary-button" disabled={submitting} type="submit">
                  Confirmar MFA
                </button>
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
              <button className="primary-button" disabled={submitting} type="submit">
                Criar usuario
              </button>
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
                      <button className="ghost-button compact" disabled={submitting} onClick={() => void onDeactivateUser(user.id)} type="button">
                        Desativar
                      </button>
                    )}
                    {user.mfa_enabled && (
                      <button className="ghost-button compact" disabled={submitting} onClick={() => void onResetMfa(user.id)} type="button">
                        Resetar MFA
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {!users.length && <p className="empty-state">Nenhum outro usuario cadastrado.</p>}
            </div>
          </article>
        </section>
      )}

      {(view === "all" || view === "backup") && isLocalBackupMode && (
        <section className="interactive-grid single-column">
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Arquivos de backup</p>
              <h3>{backups.length} copias locais</h3>
            </div>
            <div className="table-list">
              {backups.map((backup) => (
                <div key={backup.filename} className="list-row">
                  <div>
                    <strong>{backup.filename}</strong>
                    <p>{formatDate(backup.created_at)}</p>
                  </div>
                  <span>{formatBytes(backup.size_bytes)}</span>
                </div>
              ))}
              {!backups.length && <p className="empty-state">Nenhum backup criado ainda.</p>}
            </div>
          </article>
        </section>
      )}

    </div>
  );
}
