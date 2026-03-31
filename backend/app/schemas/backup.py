from datetime import datetime

from pydantic import BaseModel


class BackupRead(BaseModel):
    filename: str
    created_at: datetime
    size_bytes: int
    storage_mode: str = "local-file"
    encrypted: bool = False


class BackupResult(BaseModel):
    message: str
    backup: BackupRead
