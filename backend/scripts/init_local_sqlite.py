from __future__ import annotations

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.db.sqlite import ensure_sqlite_database_parent, sqlite_database_path
from app.services.bootstrap import ensure_company_security, ensure_default_company
from app.services.db_schema import ensure_schema_updates


def main() -> None:
    settings = get_settings()
    if not settings.is_sqlite:
        raise SystemExit("init_local_sqlite deve ser usado apenas com DATABASE_URL sqlite.")
    if settings.is_server_mode:
        raise SystemExit("init_local_sqlite nao deve ser usado em APP_MODE=server.")

    ensure_sqlite_database_parent(settings.database_url)
    ensure_schema_updates(engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        company = ensure_default_company(db)
        ensure_company_security(db, company)
        db.commit()

    database_path = sqlite_database_path(settings.database_url)
    if database_path is not None:
        print(f"SQLite local pronto em: {database_path.resolve()}")
    else:
        print("SQLite local em memoria pronto.")


if __name__ == "__main__":
    main()
