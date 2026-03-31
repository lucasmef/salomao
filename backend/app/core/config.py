from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Gestor Financeiro"
    api_prefix: str = "/api/v1"
    app_mode: str = "desktop"
    database_url: str = "sqlite:///./gestor_financeiro.db"
    session_secret: str = "dev-session-secret-change-me"
    field_encryption_key: str = "dev-field-encryption-key-change-me"
    mfa_issuer: str = "Gestor Financeiro"
    session_cookie_name: str = "gestor_financeiro_session"
    mfa_trusted_device_cookie_name: str = "gestor_financeiro_mfa_device"
    session_cookie_secure: bool | None = None
    session_cookie_samesite: str = "lax"
    session_hours: int = 12
    mfa_trusted_device_days: int = 15
    pending_auth_minutes: int = 10
    allow_header_auth: bool = False
    public_origin: str | None = None
    security_alert_email_enabled: bool = False
    security_alert_email_from: str | None = None
    security_alert_email_to: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    ipinfo_token: str | None = None
    security_alert_allowed_countries: str = "BR"
    security_alert_failure_window_seconds: int = 600
    security_alert_failure_threshold: int = 3
    security_alert_dedup_window_seconds: int = 1800
    login_rate_limit_attempts: int = 6
    login_rate_limit_window_seconds: int = 300
    mfa_rate_limit_attempts: int = 8
    mfa_rate_limit_window_seconds: int = 300
    backup_on_startup: bool = True
    backup_startup_min_hours: int = 12
    backup_before_imports: bool = True
    backup_import_min_minutes: int = 30
    backup_retention_max_files: int = 60
    backup_retention_days: int = 120
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ])
    cors_origin_regex: str | None = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    server_backup_dir: str = "./server_backups"
    server_backup_encrypted: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_security_requirements(self) -> "Settings":
        if self.app_mode not in {"desktop", "server"}:
            raise ValueError("APP_MODE deve ser 'desktop' ou 'server'")
        if self.app_mode == "server":
            insecure_secrets = {
                "dev-session-secret-change-me",
                "dev-field-encryption-key-change-me",
            }
            if self.session_secret in insecure_secrets:
                raise ValueError("SESSION_SECRET deve ser configurado para APP_MODE=server")
            if self.field_encryption_key in insecure_secrets:
                raise ValueError("FIELD_ENCRYPTION_KEY deve ser configurado para APP_MODE=server")
        return self

    @property
    def is_server_mode(self) -> bool:
        return self.app_mode == "server"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def require_mfa(self) -> bool:
        return self.is_server_mode

    @property
    def resolved_cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.is_server_mode

    @property
    def backup_mode(self) -> str:
        return "local-file" if self.is_sqlite else "server-managed"

    @property
    def security_alert_recipients(self) -> list[str]:
        raw = self.security_alert_email_to or ""
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def allowed_country_codes(self) -> set[str]:
        raw = self.security_alert_allowed_countries or ""
        return {item.strip().upper() for item in raw.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
