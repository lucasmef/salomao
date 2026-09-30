import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { fetchJson } from "../lib/api";
import { parseApiError } from "../lib/format";

type SmtpSettings = {
  enabled: boolean;
  host: string;
  port: number;
  encryption: "ssl" | "starttls" | "none";
  username: string;
  sender: string;
  recipients: string;
  has_password: boolean;
  source: "environment" | "database";
};

type Props = { token: string | null; userEmail: string };

export function SmtpSettingsCard({ token, userEmail }: Props) {
  const [settings, setSettings] = useState<SmtpSettings | null>(null);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [recipient, setRecipient] = useState(userEmail);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ error: boolean; message: string } | null>(null);

  useEffect(() => {
    let active = true;
    fetchJson<SmtpSettings>("/company-settings/smtp", { token }).then((value) => {
      if (active) setSettings(value);
    }).catch((error: unknown) => {
      if (active) setFeedback({ error: true, message: parseApiError(error) });
    });
    return () => { active = false; };
  }, [token]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings) return;
    const testing = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("name") === "test";
    if (testing && !recipient.trim()) {
      setFeedback({ error: true, message: "Informe o destinatário do teste." });
      return;
    }
    setBusy(true);
    setFeedback(null);
    const payload = {
      enabled: settings.enabled, host: settings.host, port: settings.port,
      encryption: settings.encryption, username: settings.username,
      sender: settings.sender, recipients: settings.recipients,
      password: password || undefined,
    };
    try {
      if (testing) {
        const result = await fetchJson<{ message: string }>("/company-settings/smtp/test", {
          token, method: "POST", body: JSON.stringify({ ...payload, recipient }),
        });
        setFeedback({ error: false, message: result.message });
      } else {
        const result = await fetchJson<SmtpSettings>("/company-settings/smtp", {
          token, method: "PUT", body: JSON.stringify(payload),
        });
        setSettings(result);
        setPassword("");
        setShowPassword(false);
        setFeedback({ error: false, message: "Configuração salva. Os próximos envios já usarão estes dados." });
      }
    } catch (error) {
      setFeedback({ error: true, message: parseApiError(error) });
    } finally {
      setBusy(false);
    }
  }

  function update<K extends keyof SmtpSettings>(key: K, value: SmtpSettings[K]) {
    setSettings((current) => current ? { ...current, [key]: value } : current);
  }

  return (
    <article className="panel-card">
      <div className="panel-heading"><p className="eyebrow">E-mails do sistema</p><h3>Configuração de envio SMTP</h3></div>
      <p className="supporting">Configure o envio de alertas e avisos do Salomão. A senha é armazenada de forma criptografada.</p>
      {feedback && <p role={feedback.error ? "alert" : "status"} className="supporting">{feedback.message}</p>}
      {!settings ? <p className="empty-state">{feedback?.error ? "Não foi possível carregar a configuração." : "Carregando configuração…"}</p> : (
        <form className="form-grid single" onSubmit={submit}>
          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: "1rem" }}>
            <label className="checkbox-line compact-inline"><input type="checkbox" checked={settings.enabled} onChange={(event) => update("enabled", event.target.checked)} />Ativar envio de e-mails</label>
            <label>Servidor SMTP<input required maxLength={255} value={settings.host} onChange={(event) => update("host", event.target.value)} placeholder="smtpi.kinghost.net" /></label>
            <label>Porta<input required type="number" min={1} max={65535} value={settings.port} onChange={(event) => update("port", Number(event.target.value))} /></label>
            <label>Conexão segura<select required value={settings.encryption} onChange={(event) => update("encryption", event.target.value as SmtpSettings["encryption"])}>
              {settings.encryption === "none" && <option value="none" disabled>Selecione uma conexão segura</option>}
              <option value="ssl">SSL/TLS (geralmente porta 465)</option><option value="starttls">STARTTLS (geralmente porta 587)</option>
            </select></label>
            <label>Usuário SMTP<input required maxLength={255} value={settings.username} onChange={(event) => update("username", event.target.value)} autoComplete="off" placeholder="alertas@raqueltalita.com.br" /></label>
            <label>Senha da caixa de e-mail<input type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" maxLength={1024} placeholder={settings.has_password ? "Deixe em branco para manter a senha salva" : "Digite ou cole a senha"} /></label>
            <label className="checkbox-line compact-inline"><input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)} />Mostrar senha digitada</label>
            <p className="supporting">{settings.has_password ? "Há uma senha cadastrada." : "Nenhuma senha cadastrada."} Ao mudar o usuário SMTP, informe a senha da nova conta.</p>
            <label>E-mail do remetente<input required type="email" maxLength={255} value={settings.sender} onChange={(event) => update("sender", event.target.value)} /></label>
            <label>Destinatários dos alertas de segurança<input maxLength={4000} value={settings.recipients} onChange={(event) => update("recipients", event.target.value)} placeholder="Separe os e-mails por vírgula" /></label>
            {settings.source === "environment" && <p className="supporting">A configuração atual foi carregada do servidor. Ao salvar, você poderá administrá-la por esta tela.</p>}
            <button type="submit" name="save" className="primary-button">{busy ? "Aguarde…" : "Salvar configuração"}</button>
            <label>Destinatário do teste<input type="email" maxLength={255} value={recipient} onChange={(event) => setRecipient(event.target.value)} /></label>
            <button type="submit" name="test" className="ghost-button">Enviar e-mail de teste</button>
            <p className="supporting">O teste usa os dados preenchidos, mesmo com o envio desativado, e não salva alterações. Após testar, clique em Salvar configuração.</p>
          </fieldset>
        </form>
      )}
    </article>
  );
}
