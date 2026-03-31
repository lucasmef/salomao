import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { formatBytes, formatDate } from "../lib/format";
import type { AuthUser, BackupRead, InstanceInfo, MfaSetup, MfaStatus, UserCredentialsUpdatePayload } from "../types";

type Props = {
  submitting: boolean;
  currentUser: AuthUser;
  users: AuthUser[];
  backups: BackupRead[];
  instanceInfo: InstanceInfo | null;
  mfaStatus: MfaStatus | null;
  activeMfaSetup: MfaSetup | null;
  onCreateUser: (payload: Record<string, unknown>) => Promise<void>;
  onUpdateCredentials: (payload: UserCredentialsUpdatePayload) => Promise<void>;
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
  mfaStatus,
  activeMfaSetup,
  onCreateUser,
  onUpdateCredentials,
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
  const isLocalBackupMode = (instanceInfo?.backup_mode ?? "local-file") === "local-file";

  useEffect(() => {
    setCredentialsForm((current) => ({ ...current, email: currentUser.email }));
  }, [currentUser.email]);

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

  return (
    <div className="page-layout">
      {!embedded && (
        <PageHeader
          eyebrow="Administracao"
          title="Seguranca e continuidade"
          description="Usuarios, MFA, backup local e operacao segura durante a transicao para o ambiente online."
        />
      )}
      <section className="interactive-grid">
        {(view === "all" || view === "users") && (
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Sessao atual</p>
              <h3>Usuario autenticado</h3>
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
              <h3>{isLocalBackupMode ? "Protecao da base local" : "Backups operacionais do servidor"}</h3>
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
                No modo servidor, os backups do PostgreSQL sao operacionais e feitos pelos scripts dedicados, fora da UI.
              </p>
            )}
          </article>
        )}

        {view === "security" && (
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">Seguranca</p>
              <h3>Politicas e endurecimento</h3>
            </div>
            <div className="summary-list">
              <div className="summary-row"><span>Modo da aplicacao</span><strong>{instanceInfo?.app_mode ?? "-"}</strong></div>
              <div className="summary-row"><span>Banco ativo</span><strong>{instanceInfo?.database_backend ?? "-"}</strong></div>
              <div className="summary-row"><span>MFA obrigatorio</span><strong>{mfaStatus?.required ? "sim" : "nao"}</strong></div>
              <div className="summary-row"><span>MFA do usuario atual</span><strong>{mfaStatus?.enabled ? "ativo" : "inativo"}</strong></div>
            </div>
          </article>
        )}
      </section>

      {(view === "all" || view === "security") && (
        <section className="interactive-grid">
          <article className="panel-card">
            <div className="panel-heading">
              <p className="eyebrow">MFA TOTP</p>
              <h3>Autenticador do usuario atual</h3>
            </div>
            {!activeMfaSetup ? (
              <>
                <p className="supporting">
                  {mfaStatus?.enabled
                    ? "O MFA ja esta ativo para este usuario."
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
              <p className="eyebrow">Usuarios</p>
              <h3>Novo usuario local</h3>
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
