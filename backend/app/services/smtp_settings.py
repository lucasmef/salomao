import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_text, encrypt_text
from app.db.models.email_settings import EmailSettings
from app.db.session import SessionLocal
from app.schemas.smtp import SmtpSettingsRead, SmtpSettingsUpdate


@dataclass
class SmtpConfiguration:
    enabled: bool
    host: str
    port: int
    encryption: str
    username: str
    sender: str
    recipients: str
    password: str | None = field(repr=False)
    source: str = "environment"


def environment_configuration() -> SmtpConfiguration:
    settings = get_settings()
    return SmtpConfiguration(
        enabled=settings.security_alert_email_enabled,
        host=settings.smtp_host or "",
        port=settings.smtp_port,
        encryption="ssl"
        if settings.smtp_use_ssl
        else "starttls"
        if settings.smtp_use_tls
        else "none",
        username=settings.smtp_username or "",
        sender=settings.security_alert_email_from or settings.smtp_username or "",
        recipients=settings.security_alert_email_to or "",
        password=settings.smtp_password,
    )


def read_configuration(db: Session) -> SmtpConfiguration:
    row = db.get(EmailSettings, 1)
    if row is None:
        return environment_configuration()
    return SmtpConfiguration(
        enabled=row.enabled,
        host=row.host,
        port=row.port,
        encryption=row.encryption,
        username=row.username,
        sender=row.sender,
        recipients=row.recipients,
        password=decrypt_text(row.password_encrypted),
        source="database",
    )


def runtime_configuration() -> SmtpConfiguration:
    with SessionLocal() as db:
        return read_configuration(db)


def serialize_configuration(config: SmtpConfiguration) -> SmtpSettingsRead:
    return SmtpSettingsRead(
        enabled=config.enabled,
        host=config.host,
        port=config.port,
        encryption=config.encryption,
        username=config.username,
        sender=config.sender,
        recipients=config.recipients,
        has_password=bool(config.password),
        source=config.source,
    )


def configuration_from_payload(db: Session, payload: SmtpSettingsUpdate) -> SmtpConfiguration:
    current = read_configuration(db)
    supplied_password = payload.password.get_secret_value() if payload.password is not None else ""
    if len(supplied_password) > 1024:
        raise ValueError("A senha deve ter no maximo 1024 caracteres")
    password = supplied_password or current.password
    # Credentials from a different account must never be silently reused.
    if not supplied_password and payload.username != current.username:
        raise ValueError("Informe a senha ao alterar o usuario SMTP")
    if not password:
        raise ValueError("Informe a senha da conta de e-mail")
    return SmtpConfiguration(
        enabled=payload.enabled,
        host=payload.host,
        port=payload.port,
        encryption=payload.encryption,
        username=payload.username,
        sender=payload.sender,
        recipients=payload.recipients,
        password=password,
        source="database",
    )


def save_configuration(db: Session, config: SmtpConfiguration) -> None:
    row = db.get(EmailSettings, 1)
    if row is None:
        row = EmailSettings(id=1)
        db.add(row)
    for name in ("enabled", "host", "port", "encryption", "username", "sender", "recipients"):
        setattr(row, name, getattr(config, name))
    row.password_encrypted = encrypt_text(config.password)
    db.flush()


def deliver_message(config: SmtpConfiguration, message: EmailMessage) -> None:
    client = smtplib.SMTP_SSL if config.encryption == "ssl" else smtplib.SMTP
    options = {"timeout": get_settings().smtp_timeout_seconds}
    if config.encryption == "ssl":
        options["context"] = ssl.create_default_context()
    with client(config.host, config.port, **options) as smtp:
        if config.encryption == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if config.username and config.password:
            smtp.login(config.username, config.password)
        smtp.send_message(message)


def send_test_email(config: SmtpConfiguration, recipient: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Salomao - teste de envio de e-mail"
    message["From"] = config.sender
    message["To"] = recipient
    message.set_content("Este e um e-mail de teste da configuracao SMTP do Salomao.")
    deliver_message(config, message)


def smtp_error_message(error: Exception) -> str:
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return (
            f"O servidor recusou o login (codigo {error.smtp_code}). Confira usuario, senha "
            "e se a conta permite acesso SMTP. Na KingHost, verifique a ativacao do SMTPi."
        )
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "O servidor recusou o destinatario do teste. Confira o e-mail informado."
    if isinstance(error, smtplib.SMTPSenderRefused):
        return "O servidor recusou o remetente. Confira se ele e autorizado para esta conta."
    if isinstance(error, ssl.SSLError):
        return "Falha ao validar a conexao segura. Confira servidor, porta e criptografia."
    return "Nao foi possivel enviar o teste. Confira servidor, porta e acesso ao SMTP."
