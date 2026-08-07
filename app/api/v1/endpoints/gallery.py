import base64
import hashlib
import io
import re
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.db.session import get_supabase

router = APIRouter()

GALLERY_BUCKET = "gallery"


# --- Helpers ---

def _is_base64_image(data: str) -> bool:
    return data.startswith("data:image/")


def _convert_base64_to_webp(base64_data: str) -> tuple[bytes, str]:
    match = re.match(r"data:(image/\w+);base64,(.+)", base64_data)
    if not match:
        return b"", ""

    base64_str = match.group(2)
    mime_ext = match.group(1).split("/")[-1]
    if mime_ext == "jpeg":
        mime_ext = "jpg"
    data_hash = hashlib.md5(base64_str.encode()).hexdigest()

    try:
        from PIL import Image
        image_bytes = base64.b64decode(base64_str)
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=80, method=6)
        return buf.getvalue(), f"{data_hash}.webp"
    except Exception:
        try:
            image_bytes = base64.b64decode(base64_str)
            return image_bytes, f"{data_hash}.{mime_ext}"
        except Exception:
            return b"", ""


def _ensure_bucket(supabase):
    try:
        supabase.storage.create_bucket(GALLERY_BUCKET, options={"public": True})
    except Exception:
        pass


def _upload_to_storage(supabase, filename: str, data: bytes) -> str:
    _ensure_bucket(supabase)
    ext = Path(filename).suffix.lower()
    content_type = {
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")
    import structlog
    logger = structlog.get_logger()
    logger.info("gallery_upload_start", filename=filename, size=len(data), content_type=content_type)
    try:
        supabase.storage.from_(GALLERY_BUCKET).upload(
            filename, data, file_options={"content-type": content_type, "upsert": True}
        )
        url = _get_public_url(supabase, filename)
        logger.info("gallery_upload_ok", url=url)
        return url
    except Exception as e:
        logger.error("gallery_upload_failed", error=str(e), filename=filename)
        raise


def _get_public_url(supabase, filename: str) -> str:
    result = supabase.storage.from_(GALLERY_BUCKET).get_public_url(filename)
    return result


def _delete_from_storage(supabase, filename: str):
    try:
        supabase.storage.from_(GALLERY_BUCKET).remove([filename])
    except Exception:
        pass


def _extract_storage_filename(image_url: str) -> str:
    if "/gallery/" in image_url:
        return image_url.split("/gallery/")[-1]
    return ""


def _db_row_to_response(row: dict) -> dict:
    return {
        "id": row["id"],
        "image": row.get("image", ""),
        "title": row.get("title", ""),
        "category": row.get("category", "general"),
        "sortOrder": row.get("sort_order", 0),
        "isActive": row.get("is_active", True),
    }


def _response_to_db_row(item: dict) -> dict:
    return {
        "image": item.get("image", ""),
        "title": item.get("title", ""),
        "category": item.get("category", "general"),
        "sort_order": item.get("sortOrder", 0),
        "is_active": item.get("isActive", True),
    }


# --- Schemas ---

class GalleryItemResponse(BaseModel):
    id: int
    image: str
    title: str
    category: str
    sortOrder: int = 0
    isActive: bool = True


class GalleryItemCreate(BaseModel):
    image: str
    title: str = ""
    category: str = "general"
    sortOrder: int = 0
    isActive: bool = True


class GalleryBulkCreate(BaseModel):
    items: List[GalleryItemCreate]


class GalleryItemUpdate(BaseModel):
    image: Optional[str] = None
    title: Optional[str] = None
    category: Optional[str] = None
    sortOrder: Optional[int] = None
    isActive: Optional[bool] = None


# --- Endpoints ---

@router.get("/", response_model=List[GalleryItemResponse])
async def get_gallery():
    supabase = get_supabase()
    result = (
        supabase.table("gallery_items")
        .select("*")
        .order("sort_order")
        .execute()
    )
    return [_db_row_to_response(row) for row in result.data]


@router.post("/bulk", response_model=List[GalleryItemResponse])
async def bulk_create_gallery_items(payload: GalleryBulkCreate):
    import structlog
    logger = structlog.get_logger()
    supabase = get_supabase()
    rows = []
    for item in payload.items:
        try:
            db_data = _response_to_db_row(item.model_dump())
            if _is_base64_image(db_data.get("image", "")):
                webp_data, filename = _convert_base64_to_webp(db_data["image"])
                if webp_data:
                    db_data["image"] = _upload_to_storage(supabase, filename, webp_data)
                else:
                    logger.error("gallery_convert_failed", title=item.title)
                    raise HTTPException(status_code=500, detail="Failed to convert image")
            rows.append(db_data)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("gallery_item_error", error=str(e), title=item.title)
            raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")

    result = supabase.table("gallery_items").insert(rows).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create gallery items")
    return [_db_row_to_response(row) for row in result.data]


@router.get("/{item_id}", response_model=GalleryItemResponse)
async def get_gallery_item(item_id: int):
    supabase = get_supabase()
    result = (
        supabase.table("gallery_items")
        .select("*")
        .eq("id", item_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Gallery item not found")
    return _db_row_to_response(result.data[0])


@router.post("/", response_model=GalleryItemResponse)
async def create_gallery_item(item: GalleryItemCreate):
    supabase = get_supabase()
    db_data = _response_to_db_row(item.model_dump())
    if _is_base64_image(db_data.get("image", "")):
        webp_data, filename = _convert_base64_to_webp(db_data["image"])
        if webp_data:
            db_data["image"] = _upload_to_storage(supabase, filename, webp_data)

    result = supabase.table("gallery_items").insert(db_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create gallery item")
    return _db_row_to_response(result.data[0])


@router.put("/{item_id}", response_model=GalleryItemResponse)
async def update_gallery_item(item_id: int, item: GalleryItemUpdate):
    supabase = get_supabase()
    raw = item.model_dump(exclude_unset=True)
    _FIELD_MAP = {"image": "image", "title": "title", "category": "category", "sortOrder": "sort_order", "isActive": "is_active"}
    update_data = {_FIELD_MAP[k]: v for k, v in raw.items() if k in _FIELD_MAP}

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "image" in update_data and _is_base64_image(update_data["image"]):
        webp_data, filename = _convert_base64_to_webp(update_data["image"])
        if webp_data:
            update_data["image"] = _upload_to_storage(supabase, filename, webp_data)

    result = (
        supabase.table("gallery_items")
        .update(update_data)
        .eq("id", item_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Gallery item not found")
    return _db_row_to_response(result.data[0])


@router.delete("/{item_id}")
async def delete_gallery_item(item_id: int):
    supabase = get_supabase()

    result = (
        supabase.table("gallery_items")
        .select("image")
        .eq("id", item_id)
        .execute()
    )
    if result.data:
        filename = _extract_storage_filename(result.data[0].get("image", ""))
        if filename:
            _delete_from_storage(supabase, filename)

    supabase.table("gallery_items").delete().eq("id", item_id).execute()
    return {"message": "Gallery item deleted", "id": item_id}


@router.get("/images/{filename}")
async def get_gallery_image(filename: str):
    supabase = get_supabase()
    try:
        result = supabase.storage.from_(GALLERY_BUCKET).download(filename)
        ext = Path(filename).suffix.lower()
        media_type = {
            ".webp": "image/webp",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
        }.get(ext, "application/octet-stream")
        response = Response(content=result, media_type=media_type)
        response.headers.update({"Cache-Control": "public, max-age=31536000, immutable"})
        return response
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")
