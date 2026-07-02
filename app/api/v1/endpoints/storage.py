from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import Optional

from app.core.deps import get_current_user, CurrentUser
from app.core.config import settings
from app.db.session import get_supabase

router = APIRouter()


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
    result = db.storage.from_(bucket).upload(path, content, file_options={"content-type": file.content_type})

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