import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import Optional
import structlog

from app.core.deps import get_current_user, CurrentUser
from app.core.config import settings
from app.db.session import get_supabase

logger = structlog.get_logger()
router = APIRouter()

PUBLIC_BUCKETS = {"logos", "inscriptions", "sorteo_avistaje"}


def _ensure_bucket(db, bucket: str):
    """Create or update bucket to be public using httpx REST API."""
    if bucket not in PUBLIC_BUCKETS:
        return

    import httpx
    supabase_url = os.environ.get("SUPABASE_URL", "")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        logger.warning("bucket_ensure_skip_no_config", bucket=bucket)
        return

    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "application/json",
    }
    base = f"{supabase_url}/storage/v1"

    # Check if bucket exists
    try:
        resp = httpx.get(f"{base}/bucket", headers=headers, timeout=10)
        if resp.status_code == 200:
            buckets = resp.json()
            names = [b.get("name", "") for b in buckets] if isinstance(buckets, list) else []
            if bucket in names:
                logger.info("bucket_already_exists", bucket=bucket)
                # Make sure it's public
                httpx.post(f"{base}/bucket/{bucket}", headers=headers, json={"public": True}, timeout=10)
                return
    except Exception as e:
        logger.warning("bucket_list_failed", error=str(e))

    # Create bucket
    try:
        resp = httpx.post(
            f"{base}/bucket",
            headers=headers,
            json={"id": bucket, "name": bucket, "public": True, "file_size_limit": 10485760},
            timeout=10,
        )
        if resp.status_code in (200, 201, 409):
            logger.info("bucket_created", bucket=bucket, status=resp.status_code)
            if resp.status_code == 409:
                httpx.post(f"{base}/bucket/{bucket}", headers=headers, json={"public": True}, timeout=10)
        else:
            logger.warning("bucket_create_failed", bucket=bucket, status=resp.status_code, body=resp.text[:200])
    except Exception as e:
        logger.warning("bucket_create_error", bucket=bucket, error=str(e))


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


@router.get("/public-url/{bucket}/{path:path}")
async def get_public_url(
    bucket: str,
    path: str,
):
    db = get_supabase()
    _ensure_bucket(db, bucket)
    result = db.storage.from_(bucket).get_public_url(path)
    return {"public_url": result}