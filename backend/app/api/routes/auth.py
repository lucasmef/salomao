from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from app.api.deps import CurrentUser, DbSession, require_role
from app.core.config import get_settings
from app.core.rate_limit import rate_limiter
from app.db.models.security import User
from app.schemas.auth import (
    AuthUserRead,
    LoginRequest,
    LoginResponse,
    MfaEnrollConfirmRequest,
    MfaResetRequest,
    MfaSetupRead,
    MfaStatusRead,
    MfaVerifyRequest,
    UserCreate,
    UserCredentialsUpdate,
)
from app.services.auth import (
    authenticate_login,
    confirm_mfa_enrollment,
    create_user,
    deactivate_user,
    get_mfa_status,
    list_users,
    reset_mfa,
    revoke_mfa_trusted_device,
    revoke_session,
    serialize_user,
    start_mfa_enrollment,
    update_current_user_credentials,
    verify_login_mfa,
)
from app.services.company_context import get_current_company
from app.services.security_alerts import (
    alert_on_foreign_access,
    get_client_ip,
    record_auth_failure,
    record_rate_limit_attack,
)

router = APIRouter()


def _client_identity(request: Request) -> str:
    fallback = request.client.host if request.client else "unknown"
    return get_client_ip(request.headers, fallback=fallback)


def _consume_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    if rate_limiter.hit(key, limit=limit, window_seconds=window_seconds):
        return
    raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.")


def _reset_rate_limit(key: str) -> None:
    rate_limiter.reset(key)


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.resolved_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=max(settings.session_hours, 1) * 3600,
        path="/",
    )


def _set_trusted_device_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.mfa_trusted_device_cookie_name,
        token,
        httponly=True,
        secure=settings.resolved_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=max(settings.mfa_trusted_device_days, 1) * 24 * 3600,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")


def _clear_trusted_device_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.mfa_trusted_device_cookie_name, path="/")


def _request_token(request: Request, x_auth_token: str | None) -> str | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token and settings.allow_header_auth:
        token = x_auth_token
    return token


def _request_trusted_device_token(request: Request) -> str | None:
    return request.cookies.get(get_settings().mfa_trusted_device_cookie_name)


def _finalize_login_response(response: Response, login_response: LoginResponse) -> LoginResponse:
    if login_response.token:
        _set_session_cookie(response, login_response.token)
    if login_response.trusted_device_token:
        _set_trusted_device_cookie(response, login_response.trusted_device_token)
    login_response.token = None
    login_response.trusted_device_token = None
    return login_response


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, request: Request, db: DbSession) -> LoginResponse:
    settings = get_settings()
    client_ip = _client_identity(request)
    user_agent = request.headers.get("user-agent")
    normalized_email = payload.email.strip().lower()
    rate_limit_key = f"login:{client_ip}:{normalized_email}"
    try:
        _consume_rate_limit(
            rate_limit_key,
            limit=settings.login_rate_limit_attempts,
            window_seconds=settings.login_rate_limit_window_seconds,
        )
        login_response = authenticate_login(
            db,
            payload.email,
            payload.password,
            trusted_device_token=_request_trusted_device_token(request),
        )
    except HTTPException as exc:
        if exc.status_code == 429:
            record_rate_limit_attack(
                db,
                client_ip=client_ip,
                email=normalized_email,
                user_agent=user_agent,
                path=str(request.url.path),
                rate_limit_key=rate_limit_key,
            )
            db.commit()
        elif exc.status_code == 401:
            record_auth_failure(
                db,
                client_ip=client_ip,
                email=normalized_email,
                user_agent=user_agent,
                reason="invalid_credentials",
                path=str(request.url.path),
            )
            db.commit()
        raise
    _reset_rate_limit(rate_limit_key)
    authenticated_user = db.get(User, login_response.user.id)
    alert_on_foreign_access(
        db,
        client_ip=client_ip,
        user_agent=user_agent,
        email=normalized_email,
        user=authenticated_user,
        login_status=login_response.status,
    )
    db.commit()
    return _finalize_login_response(response, login_response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: DbSession,
    request: Request,
    response: Response,
    current_user: CurrentUser,
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
) -> Response:
    auth_token = _request_token(request, x_auth_token)
    trusted_device_token = _request_trusted_device_token(request)
    if not auth_token:
        raise HTTPException(status_code=401, detail="Sessao nao informada")
    revoke_session(db, auth_token, current_user)
    if trusted_device_token:
        revoke_mfa_trusted_device(db, trusted_device_token, current_user)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    _clear_session_cookie(response)
    _clear_trusted_device_cookie(response)
    return response


@router.get("/me", response_model=AuthUserRead)
def me(current_user: CurrentUser) -> AuthUserRead:
    return serialize_user(current_user)


@router.patch("/me/credentials", response_model=AuthUserRead)
def update_my_credentials(payload: UserCredentialsUpdate, db: DbSession, current_user: CurrentUser) -> AuthUserRead:
    user = update_current_user_credentials(
        db,
        actor_user=current_user,
        email=payload.email,
        password=payload.password,
    )
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.post("/mfa/verify", response_model=LoginResponse)
def verify_mfa(
    payload: MfaVerifyRequest,
    response: Response,
    request: Request,
    db: DbSession,
) -> LoginResponse:
    settings = get_settings()
    client_ip = _client_identity(request)
    user_agent = request.headers.get("user-agent")
    rate_limit_key = f"mfa:{client_ip}"
    try:
        _consume_rate_limit(
            rate_limit_key,
            limit=settings.mfa_rate_limit_attempts,
            window_seconds=settings.mfa_rate_limit_window_seconds,
        )
        login_response = verify_login_mfa(
            db,
            payload.pending_token,
            payload.code,
            remember_device=payload.remember_device,
            trusted_device_user_agent=user_agent,
        )
    except HTTPException as exc:
        if exc.status_code == 429:
            record_rate_limit_attack(
                db,
                client_ip=client_ip,
                email=None,
                user_agent=user_agent,
                path=str(request.url.path),
                rate_limit_key=rate_limit_key,
            )
            db.commit()
        elif exc.status_code == 401:
            record_auth_failure(
                db,
                client_ip=client_ip,
                email="mfa-login",
                user_agent=user_agent,
                reason="invalid_mfa_code",
                path=str(request.url.path),
            )
            db.commit()
        raise
    _reset_rate_limit(rate_limit_key)
    db.commit()
    if not payload.remember_device:
        _clear_trusted_device_cookie(response)
    return _finalize_login_response(response, login_response)


@router.get("/mfa/status", response_model=MfaStatusRead)
def read_mfa_status(current_user: CurrentUser) -> MfaStatusRead:
    return get_mfa_status(current_user)


@router.post("/mfa/enroll/start", response_model=MfaSetupRead)
def begin_mfa_enrollment(db: DbSession, current_user: CurrentUser) -> MfaSetupRead:
    setup = start_mfa_enrollment(db, current_user)
    db.commit()
    return setup


@router.post("/mfa/enroll/confirm", response_model=MfaStatusRead)
def confirm_session_mfa_enrollment(
    payload: MfaEnrollConfirmRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> MfaStatusRead:
    result = confirm_mfa_enrollment(db, code=payload.code, actor_user=current_user)
    db.commit()
    if isinstance(result, LoginResponse):  # pragma: no cover - defensive branch
        raise HTTPException(status_code=500, detail="Resposta de MFA inesperada")
    return result


@router.post("/mfa/enroll/complete", response_model=LoginResponse)
def complete_login_mfa_enrollment(
    payload: MfaEnrollConfirmRequest,
    response: Response,
    request: Request,
    db: DbSession,
) -> LoginResponse:
    settings = get_settings()
    client_ip = _client_identity(request)
    user_agent = request.headers.get("user-agent")
    rate_limit_key = f"mfa-setup:{client_ip}"
    try:
        _consume_rate_limit(
            rate_limit_key,
            limit=settings.mfa_rate_limit_attempts,
            window_seconds=settings.mfa_rate_limit_window_seconds,
        )
        if not payload.pending_token:
            raise HTTPException(status_code=400, detail="Desafio de autenticacao nao informado")
        result = confirm_mfa_enrollment(
            db,
            code=payload.code,
            pending_token=payload.pending_token,
            remember_device=payload.remember_device,
            trusted_device_user_agent=user_agent,
        )
    except HTTPException as exc:
        if exc.status_code == 429:
            record_rate_limit_attack(
                db,
                client_ip=client_ip,
                email=None,
                user_agent=user_agent,
                path=str(request.url.path),
                rate_limit_key=rate_limit_key,
            )
            db.commit()
        elif exc.status_code == 401:
            record_auth_failure(
                db,
                client_ip=client_ip,
                email="mfa-setup",
                user_agent=user_agent,
                reason="invalid_mfa_setup_code",
                path=str(request.url.path),
            )
            db.commit()
        raise
    _reset_rate_limit(rate_limit_key)
    db.commit()
    if not isinstance(result, LoginResponse):  # pragma: no cover - defensive branch
        raise HTTPException(status_code=500, detail="Resposta de MFA inesperada")
    if not payload.remember_device:
        _clear_trusted_device_cookie(response)
    return _finalize_login_response(response, result)


@router.post("/mfa/reset", response_model=AuthUserRead)
def reset_user_mfa(payload: MfaResetRequest, db: DbSession, current_user: CurrentUser) -> AuthUserRead:
    require_role(current_user, {"admin"})
    user = reset_mfa(db, user_id=payload.user_id, actor_user=current_user)
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.get("/users", response_model=list[AuthUserRead])
def get_users(db: DbSession, current_user: CurrentUser) -> list[AuthUserRead]:
    require_role(current_user, {"admin"})
    company = get_current_company(db)
    return [serialize_user(user) for user in list_users(db, company.id)]


@router.post("/users", response_model=AuthUserRead, status_code=status.HTTP_201_CREATED)
def create_local_user(payload: UserCreate, db: DbSession, current_user: CurrentUser) -> AuthUserRead:
    require_role(current_user, {"admin"})
    company = get_current_company(db)
    user = create_user(
        db,
        company_id=company.id,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        actor_user=current_user,
    )
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.delete("/users/{user_id}", response_model=AuthUserRead)
def disable_local_user(user_id: str, db: DbSession, current_user: CurrentUser) -> AuthUserRead:
    require_role(current_user, {"admin"})
    user = deactivate_user(db, user_id, current_user)
    db.commit()
    db.refresh(user)
    return serialize_user(user)
