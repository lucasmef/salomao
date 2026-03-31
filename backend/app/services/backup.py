from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.schemas.backup import BackupRead


def _supports_local_backups() -> bool:
    return get_settings().is_sqlite


def _sqlite_path() -> Path:
    if not _supports_local_backups():
        raise HTTPException(status_code=400, detail="Backup local disponivel apenas para SQLite")
    database_url = get_settings().database_url
    if not database_url.startswith("sqlite:///"):
        raise HTTPException(status_code=400, detail="Backup automatico disponivel apenas para SQLite local")
    raw_path = database_url.replace("sqlite:///", "", 1)
    return Path(raw_path).resolve()


def _backup_dir() -> Path:
    backup_dir = _sqlite_path().parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def _slugify_reason(reason: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-")
    return normalized or "manual"


def _backup_to_read(path: Path) -> BackupRead:
    stat = path.stat()
    return BackupRead(
        filename=path.name,
        created_at=datetime.fromtimestamp(stat.st_mtime),
        size_bytes=stat.st_size,
        storage_mode="local-file",
        encrypted=False,
    )


def _latest_backup_path(reason: str | None = None) -> Path | None:
    candidates = sorted(
        _backup_dir().glob("*.sqlite3"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if reason is None:
        return candidates[0] if candidates else None

    prefix = f"gestor-financeiro-{_slugify_reason(reason)}-"
    for candidate in candidates:
        if candidate.name.startswith(prefix):
            return candidate
    return None


def _create_sqlite_backup(source: Path, target: Path) -> None:
    source_connection = sqlite3.connect(source)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()


def cleanup_old_backups() -> int:
    if not _supports_local_backups():
        return 0
    settings = get_settings()
    now = datetime.now()
    backups = sorted(
        _backup_dir().glob("*.sqlite3"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    removed = 0
    for index, path in enumerate(backups):
        age = now - datetime.fromtimestamp(path.stat().st_mtime)
        should_remove = index >= settings.backup_retention_max_files or age > timedelta(days=settings.backup_retention_days)
        if not should_remove:
            continue
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def create_backup_file(reason: str = "manual") -> BackupRead:
    if not _supports_local_backups():
        raise HTTPException(status_code=400, detail="Use o backup operacional do PostgreSQL no modo servidor")
    source = _sqlite_path()
    if not source.exists():
        raise HTTPException(status_code=404, detail="Banco de dados local nao encontrado")

    slug = _slugify_reason(reason)
    target = _backup_dir() / f"gestor-financeiro-{slug}-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
    _create_sqlite_backup(source, target)
    cleanup_old_backups()
    return _backup_to_read(target)


def ensure_timed_backup(reason: str, min_interval: timedelta) -> BackupRead | None:
    if not _supports_local_backups():
        return None
    source = _sqlite_path()
    if not source.exists():
        return None

    latest = _latest_backup_path(reason)
    if latest is not None:
        latest_age = datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)
        if latest_age < min_interval:
            cleanup_old_backups()
            return None

    return create_backup_file(reason=reason)


def ensure_startup_backup() -> BackupRead | None:
    settings = get_settings()
    if not _supports_local_backups():
        return None
    if not settings.backup_on_startup:
        return None
    return ensure_timed_backup(
        reason="startup",
        min_interval=timedelta(hours=max(settings.backup_startup_min_hours, 1)),
    )


def ensure_pre_import_backup(source_type: str) -> BackupRead | None:
    settings = get_settings()
    if not _supports_local_backups():
        return None
    if not settings.backup_before_imports:
        return None
    return ensure_timed_backup(
        reason=f"pre-import-{source_type}",
        min_interval=timedelta(minutes=max(settings.backup_import_min_minutes, 1)),
    )


def list_backups() -> list[BackupRead]:
    if not _supports_local_backups():
        return []
    items: list[BackupRead] = []
    for path in sorted(_backup_dir().glob("*.sqlite3"), key=lambda item: item.stat().st_mtime, reverse=True):
        items.append(_backup_to_read(path))
    return items


def validate_backup_file(path: Path) -> None:
    if not _supports_local_backups():
        raise HTTPException(status_code=400, detail="Restauracao por arquivo disponivel apenas para SQLite")
    try:
        with sqlite3.connect(path) as connection:
            cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='companies'")
            if cursor.fetchone() is None:
                raise HTTPException(status_code=400, detail="Arquivo informado nao parece ser um backup valido do sistema")
    except sqlite3.DatabaseError as error:
        raise HTTPException(status_code=400, detail="Arquivo de backup invalido") from error


def restore_backup_file(engine: Engine, uploaded_path: Path) -> BackupRead:
    if not _supports_local_backups():
        raise HTTPException(status_code=400, detail="Restauracao por arquivo disponivel apenas para SQLite")
    validate_backup_file(uploaded_path)
    destination = _sqlite_path()
    engine.dispose()
    shutil.copy2(uploaded_path, destination)
    return _backup_to_read(destination)
