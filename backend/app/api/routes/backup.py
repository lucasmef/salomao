from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import CurrentUser, DbSession, require_role
from app.schemas.backup import BackupRead, BackupResult
from app.services.audit import write_audit_log
from app.services.backup import create_backup_file, list_backups, restore_backup_file
from app.services.company_context import get_current_company
from app.db.session import engine

router = APIRouter()


@router.get("", response_model=list[BackupRead])
def get_backups(current_user: CurrentUser) -> list[BackupRead]:
    require_role(current_user, {"admin"})
    return list_backups()


@router.post("", response_model=BackupResult, status_code=status.HTTP_201_CREATED)
def create_backup(db: DbSession, current_user: CurrentUser) -> BackupResult:
    require_role(current_user, {"admin"})
    backup = create_backup_file()
    company = get_current_company(db)
    write_audit_log(
        db,
        action="create_backup",
        entity_name="backup",
        entity_id=backup.filename,
        company_id=company.id,
        actor_user=current_user,
        after_state={"filename": backup.filename},
    )
    db.commit()
    return BackupResult(message="Backup criado com sucesso.", backup=backup)


@router.post("/restore", response_model=BackupResult)
async def restore_backup(
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> BackupResult:
    require_role(current_user, {"admin"})
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".sqlite3") as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(await file.read())
        backup = restore_backup_file(engine, temp_path)
        company = get_current_company(db)
        write_audit_log(
            db,
            action="restore_backup",
            entity_name="backup",
            entity_id=backup.filename,
            company_id=company.id,
            actor_user=current_user,
            after_state={"filename": backup.filename},
        )
        db.commit()
        return BackupResult(message="Backup restaurado com sucesso.", backup=backup)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
