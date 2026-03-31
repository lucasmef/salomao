from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.security import User
from app.db.session import get_db
from app.services.auth import get_user_from_token

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    request: Request,
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
) -> User:
    settings = get_settings()
    auth_token = request.cookies.get(settings.session_cookie_name)
    if not auth_token and settings.allow_header_auth:
        auth_token = x_auth_token
    if not auth_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacao obrigatoria")
    user = get_user_from_token(db, auth_token)
    db.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(user: User, allowed_roles: set[str]) -> None:
    if user.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissao para esta acao")
