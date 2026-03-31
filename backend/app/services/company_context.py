from sqlalchemy.orm import Session

from app.db.models.security import Company
from app.services.bootstrap import ensure_default_company


def get_current_company(db: Session) -> Company:
    return ensure_default_company(db)
