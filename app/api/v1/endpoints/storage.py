from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import Optional
import structlog

from app.core.deps import get_current_user, CurrentUser
from app.core.config import settings
from app.db.session import get_supabase

logger = structlog.get_logger()
router = APIRouter()

PUBLIC_BUCKETS = {"logos", "inscriptions"}


def _ensure_bucket(db, bucket: str):
    """Create a public bucket if it doesn't exist."""
    if bucket not in PUBLIC_BUCKETS:
        return
    try:
        db.storage.create_bucket(bucket, {"public": True})
        logger.info("bucket_created", bucket=bucket)
    except Exception:
        pass


@router.post("/upload/{bucket}/{path:path}")
async def upload_file(
    bucket: str,
    path: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    if file.size and file.size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Archivo excede {settings.MAX_FILE_SIZE_MB}MB")

    if file.content_type not in settings.ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no permitido: {file.content_type}")

    content = await file.read()

    db = get_supabase()
    _ensure_bucket(db, bucket)

    try:
        result = db.storage.from_(bucket).upload(path, content, file_options={"content-type": file.content_type})
    except Exception as e:
        logger.error("storage_upload_failed", bucket=bucket, path=path, error=str(e))
        raise HTTPException(status_code=500, detail=f"Error subiendo archivo: {str(e)}")

    return {"path": f"{bucket}/{path}", "message": "Archivo subido correctamente"}


@router.get("/signed-url/{bucket}/{path:path}")
async def get_signed_url(
    bucket: str,
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_supabase()
    result = db.storage.from_(bucket).create_signed_url(path, 3600)

    return {"signed_url": result.get("signedURL", "")}