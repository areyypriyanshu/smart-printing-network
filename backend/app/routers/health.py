from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_storage
from app.gateways.storage import Storage

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(db: Session = Depends(get_db), storage: Storage = Depends(get_storage)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except OperationalError:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "error", "storage": "unknown"},
        )
    storage_ok = False
    try:
        storage_ok = storage.health()
    except Exception:
        storage_ok = False
    if not storage_ok:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "ok", "storage": "error"},
        )
    return JSONResponse(
        status_code=200, content={"status": "ok", "database": "ok", "storage": "ok"}
    )
