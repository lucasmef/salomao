from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get("")
def healthcheck() -> dict[str, str]:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
