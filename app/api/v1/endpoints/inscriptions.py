import structlog
from fastapi import APIRouter, HTTPException, status, Query, Depends, UploadFile, File, Form
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
import uuid

from app.core.deps import get_current_user, require_role, CurrentUser
from app.db.session import get_supabase

logger = structlog.get_logger(__name__)

router = APIRouter()


class InscriptionCreate(BaseModel):
    email: EmailStr
    phone: str
    category: str
    subcategory: str
    full_name: str
    stage_name: Optional[str] = None
    dni: Optional[str] = None
    birth_date: Optional[str] = None
    age: Optional[int] = None
    address: Optional[str] = None
    locality: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    experience_years: Optional[int] = None
    bio: Optional[str] = None
    technical_needs: Optional[str] = None
    proposal_name: Optional[str] = None
    choreographer_name: Optional[str] = None
    style: Optional[str] = None
    dance_list: Optional[str] = None
    themes: Optional[list] = None
    members: Optional[list] = None
    website: Optional[str] = None
    instagram: Optional[str] = None
    youtube: Optional[str] = None
    spotify: Optional[str] = None


class InscriptionResponse(BaseModel):
    id: str
    email: str
    phone: str
    category: str
    subcategory: str
    full_name: str
    stage_name: Optional[str] = None
    status: str
    created_at: str
    updated_at: str
    dni: Optional[str] = None
    birth_date: Optional[str] = None
    age: Optional[int] = None
    address: Optional[str] = None
    locality: Optional[str] = None
    province: Optional[str] = None
    bio: Optional[str] = None
    technical_needs: Optional[str] = None
    proposal_name: Optional[str] = None
    choreographer_name: Optional[str] = None
    style: Optional[str] = None
    dance_list: Optional[str] = None
    themes: Optional[list] = None
    members: Optional[list] = None


class InscriptionListResponse(BaseModel):
    data: List[InscriptionResponse]
    total: int
    page: int
    page_size: int


@router.get("/", response_model=InscriptionListResponse)
async def list_inscriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff", "jurado")),
):
    db = get_supabase()

    query = db.table("inscriptions").select("*", count="exact")

    if category:
        query = query.eq("category", category)
    if subcategory:
        query = query.eq("subcategory", subcategory)
    if status_filter:
        query = query.eq("status", status_filter)

    offset = (page - 1) * page_size
    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return InscriptionListResponse(
        data=[InscriptionResponse(**item) for item in result.data],
        total=result.count or 0,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=InscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_inscription(inscription: InscriptionCreate):
    try:
        db = get_supabase()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Base de datos no disponible: {str(e)}",
        )

    try:
        existing = db.table("inscriptions").select("id").eq("email", inscription.email).eq("status", "PENDIENTE").execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error consultando inscripciones: {str(e)}",
        )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una inscripción pendiente con este email",
        )

    insert_data = {k: v for k, v in inscription.model_dump().items() if v is not None}
    insert_data["status"] = "PENDIENTE"

    try:
        result = db.table("inscriptions").insert(insert_data).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear inscripción en base de datos: {str(e)}",
        )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear inscripción",
        )

    return InscriptionResponse(**result.data[0])


@router.get("/{inscription_id}", response_model=InscriptionResponse)
async def get_inscription(
    inscription_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_supabase()
    result = db.table("inscriptions").select("*").eq("id", inscription_id).single().execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inscripción no encontrada",
        )

    return InscriptionResponse(**result.data)


@router.patch("/{inscription_id}/status")
async def update_inscription_status(
    inscription_id: str,
    new_status: str,
    reason: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "jurado")),
):
    valid_statuses = ["PENDIENTE", "EN_REVISION", "APROBADA", "RECHAZADA", "CONTRATO_FIRMADO"]
    if new_status not in valid_statuses:
        logger.warning("Invalid status update attempt", inscription_id=inscription_id, new_status=new_status, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estado inválido. Debe ser uno de: {', '.join(valid_statuses)}",
        )

    try:
        db = get_supabase()
    except RuntimeError as e:
        logger.error("Supabase client not initialized", error=str(e), inscription_id=inscription_id, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Base de datos no disponible: {str(e)}",
        )

    try:
        existing = db.table("inscriptions").select("id, status").eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("Error fetching inscription for status update", inscription_id=inscription_id, error=str(e), user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener la inscripción: {str(e)}",
        )

    if not existing.data:
        logger.warning("Inscription not found for status update", inscription_id=inscription_id, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inscripción no encontrada",
        )

    from_status = existing.data[0].get("status")

    update_data = {
        "status": new_status,
    }

    if reason:
        update_data["rejection_reason"] = reason

    try:
        result = db.table("inscriptions").update(update_data).eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("Error updating inscription status", inscription_id=inscription_id, new_status=new_status, error=str(e), user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el estado de la inscripción: {str(e)}",
        )

    logger.info("Inscription update result", inscription_id=inscription_id, result_data=result.data if hasattr(result, 'data') else "no data attr")

    try:
        db.table("inscription_audit").insert({
            "inscription_id": inscription_id,
            "action": f"status_changed_to_{new_status}",
            "from_status": from_status,
            "to_status": new_status,
            "reason": reason,
        }).execute()
    except Exception as e:
        logger.warning("Audit log failed (non-blocking)", inscription_id=inscription_id, error=str(e))

    logger.info("Inscription status updated successfully", inscription_id=inscription_id, from_status=from_status, to_status=new_status, user_id=current_user.id)
    return {"message": f"Inscripción actualizada a {new_status}"}


@router.post("/upload/{inscription_id}")
async def upload_inscription_file(
    inscription_id: str,
    file_type: str = Query(..., description="dni_front, dni_back, promo_photo, lyrics, score"),
    file: UploadFile = File(...),
):
    try:
        db = get_supabase()
    except RuntimeError as e:
        logger.error("Supabase client not initialized", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Base de datos no disponible: {str(e)}",
        )

    try:
        existing = db.table("inscriptions").select("id").eq("id", inscription_id).single().execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Inscripción no encontrada")
    except Exception as e:
        logger.error("Error checking inscription existence", error=str(e), inscription_id=inscription_id)
        raise HTTPException(status_code=500, detail=f"Error al consultar inscripción: {str(e)}")

    allowed_types = {
        "dni_front": ["image/jpeg", "image/png"],
        "dni_back": ["image/jpeg", "image/png"],
        "promo_photo": ["image/jpeg", "image/png"],
        "lyrics": ["application/pdf", "text/plain", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        "score": ["application/pdf", "image/jpeg", "image/png"],
    }

    if file_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo inválido: {file_type}")

    if file.content_type not in allowed_types[file_type]:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no permitido para {file_type}: {file.content_type}")

    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
    path = f"inscriptions/{inscription_id}/{file_type}.{ext}"

    try:
        content = await file.read()
        logger.info("Read file content successfully", size_bytes=len(content), file_type=file_type, filename=file.filename)
    except Exception as e:
        logger.error("Error reading uploaded file", error=str(e), file_type=file_type, filename=file.filename)
        raise HTTPException(status_code=500, detail=f"Error al leer el archivo: {str(e)}")

    try:
        logger.info("Attempting to upload to Supabase Storage", path=path, content_type=file.content_type)
        db.storage.from_("inscriptions").upload(
            path,
            content,
            file_options={"content-type": file.content_type},
        )
        logger.info("File uploaded successfully", path=path)
    except Exception as e:
        logger.error("Error uploading file to Supabase Storage", error=str(e), path=path, file_type=file_type)
        raise HTTPException(status_code=500, detail=f"Error al subir archivo: {str(e)}")

    column_map = {
        "dni_front": "dni_front_url",
        "dni_back": "dni_back_url",
        "promo_photo": "promo_photo_url",
        "lyrics": "lyrics_url",
        "score": "score_url",
    }

    try:
        logger.info("Updating inscriptions table", inscription_id=inscription_id, column=column_map[file_type], path=path)
        db.table("inscriptions").update({column_map[file_type]: path}).eq("id", inscription_id).execute()
        logger.info("Database update successful")
    except Exception as e:
        logger.error("Error updating inscription record with file path", error=str(e), inscription_id=inscription_id, column=column_map[file_type])
        raise HTTPException(status_code=500, detail=f"Error al actualizar la inscripción: {str(e)}")

    return {"path": path, "message": "Archivo subido correctamente"}