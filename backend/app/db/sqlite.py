from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import make_url


def sqlite_database_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return None

    database = url.database or ""
    if database in {"", ":memory:"}:
        return None

    return Path(database).expanduser()


def ensure_sqlite_database_parent(database_url: str) -> None:
    database_path = sqlite_database_path(database_url)
    if database_path is None:
        return

    database_path.parent.mkdir(parents=True, exist_ok=True)
