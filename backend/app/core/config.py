from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_PLACEHOLDER_SECRET_PREFIXES = (
    "troque-isto",
    "change-me",
    "changeme",
    "replace-me",
    "replace-this",
)

_PLACEHOLDER_SECRET_MARKERS = (
    "placeholder",
    "example-secret",
    "example-key",
)


def _normalize_secret(secret: str) -> str:
    return secret.strip().lower()


def _looks_like_placeholder_secret(secret: str) -> bool:
    normalized = _normalize_secret(secret)
    if normalized.startswith(_PLACEHOLDER_SECRET_PREFIXES):
        return True
    return any(marker in normalized for marker in _PLACEHOLDER_SECRET_MARKERS)


def _validate_runtime_secret(value: str, env_name: str) -> None:
    if len(value.strip()) < 32:
        raise ValueError(f"{env_name} deve ter pelo menos 32 caracteres em APP_MODE=server")
    if _looks_like_placeholder_secret(value):
        raise ValueError(f"{env_name} nao pode usar placeholders em APP_MODE=server")


class Settings(BaseSettings):
    app_name: str = "Gestor Financeiro"
    api_prefix: str = "/api/v1"
    app_mode: str = "desktop"
    database_url: str = "sqlite:///./gestor_financeiro.db"
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
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
    api_docs_enabled: bool | None = None
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
        bootstrap_fields = {
            "BOOTSTRAP_ADMIN_EMAIL": self.bootstrap_admin_email,
            "BOOTSTRAP_ADMIN_PASSWORD": self.bootstrap_admin_password,
        }
        provided_bootstrap_fields = {
            name: value for name, value in bootstrap_fields.items() if value not in {None, ""}
        }
        if provided_bootstrap_fields and len(provided_bootstrap_fields) != len(bootstrap_fields):
            raise ValueError(
                "BOOTSTRAP_ADMIN_EMAIL e BOOTSTRAP_ADMIN_PASSWORD devem ser informados juntos"
            )
        if self.app_mode == "server":
            insecure_secrets = {
                "dev-session-secret-change-me",
                "dev-field-encryption-key-change-me",
            }
            if self.session_secret in insecure_secrets:
                raise ValueError("SESSION_SECRET deve ser configurado para APP_MODE=server")
            if self.field_encryption_key in insecure_secrets:
                raise ValueError("FIELD_ENCRYPTION_KEY deve ser configurado para APP_MODE=server")
            _validate_runtime_secret(self.session_secret, "SESSION_SECRET")
            _validate_runtime_secret(self.field_encryption_key, "FIELD_ENCRYPTION_KEY")
        return self

    @property
    def has_bootstrap_admin_credentials(self) -> bool:
        return bool(self.bootstrap_admin_email and self.bootstrap_admin_password)

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
    def resolved_api_docs_enabled(self) -> bool:
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return not self.is_server_mode

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
