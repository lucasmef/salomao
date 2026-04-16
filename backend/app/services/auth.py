from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_text, encrypt_text
from app.core.security import (
    build_totp_uri,
    generate_mfa_secret,
    generate_session_token,
    hash_password,
    hash_token,
    sign_state_token,
    token_expiration,
    utc_now,
    verify_password,
    verify_state_token,
    verify_totp_code,
)
from app.db.models.security import AuthSession, Company, MfaTrustedDevice, User
from app.schemas.auth import AuthUserRead, LoginResponse, MfaSetupRead, MfaStatusRead
from app.services.audit import write_audit_log


def _normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone(utc_now().tzinfo)


def serialize_user(user: User) -> AuthUserRead:
    settings = get_settings()
    return AuthUserRead(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        mfa_enabled=user.mfa_enabled,
        mfa_required=settings.require_mfa,
    )


def ensure_default_admin(db: Session, company: Company) -> User:
    user = db.scalar(select(User).where(User.company_id == company.id).order_by(User.created_at.asc()))
    if user:
        return user
    settings = get_settings()
    if not settings.has_bootstrap_admin_credentials:
        raise RuntimeError(
            "Primeiro administrador nao configurado. Defina BOOTSTRAP_ADMIN_EMAIL e "
            "BOOTSTRAP_ADMIN_PASSWORD antes de iniciar com banco vazio."
        )

    user = User(
        company_id=company.id,
        full_name="Administrador Local",
        email=settings.bootstrap_admin_email.strip().lower(),
        password_hash=hash_password(settings.bootstrap_admin_password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.flush()
    write_audit_log(
        db,
        action="bootstrap_admin",
        entity_name="user",
        entity_id=user.id,
        company_id=company.id,
        after_state={"email": user.email, "role": user.role},
    )
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais invalidas")
    return user


def create_auth_session(db: Session, user: User) -> tuple[AuthSession, str]:
    settings = get_settings()
    token = generate_session_token()
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=token_expiration(settings.session_hours),
        last_seen_at=utc_now(),
        is_active=True,
    )
    db.add(auth_session)
    db.flush()
    write_audit_log(
        db,
        action="login",
        entity_name="auth_session",
        entity_id=auth_session.id,
        company_id=user.company_id,
        actor_user=user,
        after_state={"expires_at": auth_session.expires_at.isoformat()},
    )
    return auth_session, token


def create_mfa_trusted_device(
    db: Session,
    user: User,
    *,
    user_agent: str | None = None,
) -> tuple[MfaTrustedDevice, str]:
    settings = get_settings()
    token = generate_session_token()
    trusted_device = MfaTrustedDevice(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=utc_now() + timedelta(days=max(settings.mfa_trusted_device_days, 1)),
        last_seen_at=utc_now(),
        is_active=True,
        user_agent=(user_agent or "").strip()[:512] or None,
    )
    db.add(trusted_device)
    db.flush()
    write_audit_log(
        db,
        action="trust_mfa_device",
        entity_name="mfa_trusted_device",
        entity_id=trusted_device.id,
        company_id=user.company_id,
        actor_user=user,
        after_state={"expires_at": trusted_device.expires_at.isoformat()},
    )
    return trusted_device, token


def get_valid_mfa_trusted_device(db: Session, user: User, token: str | None) -> MfaTrustedDevice | None:
    if not token:
        return None
    trusted_device = db.scalar(
        select(MfaTrustedDevice).where(
            MfaTrustedDevice.user_id == user.id,
            MfaTrustedDevice.token_hash == hash_token(token),
            MfaTrustedDevice.is_active.is_(True),
        )
    )
    expires_at = _normalize_utc(trusted_device.expires_at) if trusted_device else None
    if not trusted_device or not expires_at:
        return None
    if expires_at <= utc_now():
        trusted_device.is_active = False
        db.flush()
        return None
    trusted_device.last_seen_at = utc_now()
    db.flush()
    return trusted_device


def _pending_auth_token(user: User, purpose: str) -> str:
    settings = get_settings()
    expires_at = utc_now() + timedelta(minutes=max(settings.pending_auth_minutes, 1))
    payload = {
        "sub": user.id,
        "purpose": purpose,
        "exp": expires_at.isoformat(),
        "nonce": generate_session_token(),
    }
    return sign_state_token(payload, settings.session_secret)


def _resolve_pending_user(db: Session, pending_token: str, *, expected_purpose: str) -> User:
    settings = get_settings()
    try:
        payload = verify_state_token(pending_token, settings.session_secret)
    except Exception as exc:  # pragma: no cover - defensive parsing
        raise HTTPException(status_code=401, detail="Desafio de autenticacao invalido") from exc

    if payload.get("purpose") != expected_purpose:
        raise HTTPException(status_code=401, detail="Desafio de autenticacao invalido")
    expires_at = payload.get("exp")
    if not expires_at:
        raise HTTPException(status_code=401, detail="Desafio de autenticacao expirado")
    expires_at_value = _normalize_utc(datetime.fromisoformat(expires_at))
    if not expires_at_value or expires_at_value <= utc_now():
        raise HTTPException(status_code=401, detail="Desafio de autenticacao expirado")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario inativo")
    return user


def _create_mfa_setup_payload(user: User, secret: str) -> MfaSetupRead:
    settings = get_settings()
    return MfaSetupRead(
        secret=secret,
        provisioning_uri=build_totp_uri(secret, user.email, settings.mfa_issuer),
        issuer=settings.mfa_issuer,
        account_name=user.email,
    )


def start_mfa_enrollment(db: Session, user: User) -> MfaSetupRead:
    secret = generate_mfa_secret()
    user.mfa_pending_secret_encrypted = encrypt_text(secret)
    db.flush()
    write_audit_log(
        db,
        action="start_mfa_enrollment",
        entity_name="user",
        entity_id=user.id,
        company_id=user.company_id,
        actor_user=user,
        after_state={"mfa_pending": True},
    )
    return _create_mfa_setup_payload(user, secret)


def authenticate_login(
    db: Session,
    email: str,
    password: str,
    *,
    trusted_device_token: str | None = None,
) -> LoginResponse:
    settings = get_settings()
    user = authenticate_user(db, email, password)
    if settings.require_mfa:
        trusted_device = get_valid_mfa_trusted_device(db, user, trusted_device_token)
        if trusted_device is not None:
            auth_session, token = create_auth_session(db, user)
            return LoginResponse(
                status="authenticated",
                token=token,
                expires_at=auth_session.expires_at,
                trusted_device_expires_at=trusted_device.expires_at,
                user=serialize_user(user),
            )
        if user.mfa_enabled and user.mfa_secret_encrypted:
            return LoginResponse(
                status="mfa_required",
                pending_token=_pending_auth_token(user, "mfa-login"),
                user=serialize_user(user),
            )
        setup = start_mfa_enrollment(db, user)
        return LoginResponse(
            status="mfa_setup_required",
            pending_token=_pending_auth_token(user, "mfa-setup"),
            user=serialize_user(user),
            mfa_setup=setup,
        )

    auth_session, token = create_auth_session(db, user)
    return LoginResponse(
        status="authenticated",
        token=token,
        expires_at=auth_session.expires_at,
        user=serialize_user(user),
    )


def verify_login_mfa(
    db: Session,
    pending_token: str,
    code: str,
    *,
    remember_device: bool = False,
    trusted_device_user_agent: str | None = None,
) -> LoginResponse:
    user = _resolve_pending_user(db, pending_token, expected_purpose="mfa-login")
    secret = decrypt_text(user.mfa_secret_encrypted)
    if not secret or not verify_totp_code(secret, code):
        raise HTTPException(status_code=401, detail="Codigo MFA invalido")
    auth_session, token = create_auth_session(db, user)
    trusted_device_token = None
    trusted_device_expires_at = None
    if remember_device:
        trusted_device, trusted_device_token = create_mfa_trusted_device(
            db,
            user,
            user_agent=trusted_device_user_agent,
        )
        trusted_device_expires_at = trusted_device.expires_at
    return LoginResponse(
        status="authenticated",
        token=token,
        expires_at=auth_session.expires_at,
        trusted_device_token=trusted_device_token,
        trusted_device_expires_at=trusted_device_expires_at,
        user=serialize_user(user),
    )


def confirm_mfa_enrollment(
    db: Session,
    *,
    code: str,
    actor_user: User | None = None,
    pending_token: str | None = None,
    remember_device: bool = False,
    trusted_device_user_agent: str | None = None,
) -> LoginResponse | MfaStatusRead:
    login_completion = actor_user is None
    if login_completion:
        if not pending_token:
            raise HTTPException(status_code=401, detail="Desafio de autenticacao nao informado")
        user = _resolve_pending_user(db, pending_token, expected_purpose="mfa-setup")
    else:
        user = actor_user

    secret = decrypt_text(user.mfa_pending_secret_encrypted)
    if not secret or not verify_totp_code(secret, code):
        raise HTTPException(status_code=401, detail="Codigo MFA invalido")

    user.mfa_secret_encrypted = encrypt_text(secret)
    user.mfa_pending_secret_encrypted = None
    user.mfa_enabled = True
    user.mfa_enrolled_at = utc_now()
    db.flush()
    write_audit_log(
        db,
        action="confirm_mfa_enrollment",
        entity_name="user",
        entity_id=user.id,
        company_id=user.company_id,
        actor_user=actor_user or user,
        after_state={"mfa_enabled": True},
    )

    if not login_completion:
        return get_mfa_status(user)

    auth_session, token = create_auth_session(db, user)
    trusted_device_token = None
    trusted_device_expires_at = None
    if remember_device:
        trusted_device, trusted_device_token = create_mfa_trusted_device(
            db,
            user,
            user_agent=trusted_device_user_agent,
        )
        trusted_device_expires_at = trusted_device.expires_at
    return LoginResponse(
        status="authenticated",
        token=token,
        expires_at=auth_session.expires_at,
        trusted_device_token=trusted_device_token,
        trusted_device_expires_at=trusted_device_expires_at,
        user=serialize_user(user),
    )


def get_mfa_status(user: User) -> MfaStatusRead:
    settings = get_settings()
    return MfaStatusRead(
        enabled=user.mfa_enabled,
        required=settings.require_mfa,
        setup_pending=bool(user.mfa_pending_secret_encrypted),
        issuer=settings.mfa_issuer,
        mode=settings.app_mode,
    )


def reset_mfa(db: Session, *, user_id: str, actor_user: User) -> User:
    user = db.get(User, user_id)
    if not user or user.company_id != actor_user.company_id:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    user.mfa_pending_secret_encrypted = None
    user.mfa_enrolled_at = None
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(MfaTrustedDevice).where(MfaTrustedDevice.user_id == user.id))
    db.flush()
    write_audit_log(
        db,
        action="reset_mfa",
        entity_name="user",
        entity_id=user.id,
        company_id=user.company_id,
        actor_user=actor_user,
        after_state={"mfa_enabled": False},
    )
    return user


def get_user_from_token(db: Session, token: str) -> User:
    token_hash_value = hash_token(token)
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash_value,
            AuthSession.is_active.is_(True),
        )
    )
    expires_at = _normalize_utc(session.expires_at) if session else None
    if not session or not expires_at or expires_at <= utc_now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao invalida ou expirada")
    if not session.user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inativo")
    session.last_seen_at = utc_now()
    db.flush()
    return session.user


def revoke_session(db: Session, token: str, actor_user: User | None = None) -> None:
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if not session:
        return
    session.is_active = False
    db.flush()
    write_audit_log(
        db,
        action="logout",
        entity_name="auth_session",
        entity_id=session.id,
        company_id=actor_user.company_id if actor_user else None,
        actor_user=actor_user,
        after_state={"is_active": False},
    )


def revoke_mfa_trusted_device(db: Session, token: str, actor_user: User | None = None) -> None:
    trusted_device = db.scalar(select(MfaTrustedDevice).where(MfaTrustedDevice.token_hash == hash_token(token)))
    if not trusted_device:
        return
    trusted_device.is_active = False
    db.flush()
    write_audit_log(
        db,
        action="revoke_trusted_mfa_device",
        entity_name="mfa_trusted_device",
        entity_id=trusted_device.id,
        company_id=actor_user.company_id if actor_user else trusted_device.user.company_id,
        actor_user=actor_user,
        after_state={"is_active": False},
    )


def list_users(db: Session, company_id: str) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.company_id == company_id)
            .order_by(User.full_name.asc(), User.email.asc())
        )
    )


def create_user(
    db: Session,
    *,
    company_id: str,
    full_name: str,
    email: str,
    password: str,
    role: str,
    actor_user: User,
) -> User:
    normalized_email = email.strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        raise HTTPException(status_code=400, detail="Ja existe usuario com este email")
    user = User(
        company_id=company_id,
        full_name=full_name.strip(),
        email=normalized_email,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    write_audit_log(
        db,
        action="create_user",
        entity_name="user",
        entity_id=user.id,
        company_id=company_id,
        actor_user=actor_user,
        after_state={"email": user.email, "role": user.role},
    )
    return user


def update_current_user_credentials(
    db: Session,
    *,
    actor_user: User,
    email: str,
    password: str | None,
) -> User:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email obrigatorio")

    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing and existing.id != actor_user.id:
        raise HTTPException(status_code=400, detail="Ja existe usuario com este email")

    before_state = {"email": actor_user.email}
    actor_user.email = normalized_email
    if password:
        actor_user.password_hash = hash_password(password)
    db.flush()
    write_audit_log(
        db,
        action="update_own_credentials",
        entity_name="user",
        entity_id=actor_user.id,
        company_id=actor_user.company_id,
        actor_user=actor_user,
        before_state=before_state,
        after_state={"email": actor_user.email, "password_changed": bool(password)},
    )
    return actor_user


def deactivate_user(db: Session, user_id: str, actor_user: User) -> User:
    user = db.get(User, user_id)
    if not user or user.company_id != actor_user.company_id:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    if user.id == actor_user.id:
        raise HTTPException(status_code=400, detail="Nao e permitido desativar o proprio usuario")
    user.is_active = False
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(MfaTrustedDevice).where(MfaTrustedDevice.user_id == user.id))
    db.flush()
    write_audit_log(
        db,
        action="deactivate_user",
        entity_name="user",
        entity_id=user.id,
        company_id=user.company_id,
        actor_user=actor_user,
        after_state={"is_active": False},
    )
    return user
