import base64
import hashlib
import re
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.db.session import get_supabase

router = APIRouter()

GALLERY_IMAGES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "api" / "static" / "gallery"
GALLERY_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


# --- Helpers ---

def _is_base64_image(data: str) -> bool:
    return data.startswith("data:image/")


def _convert_base64_to_file(base64_data: str) -> str:
    match = re.match(r"data:(image/\w+);base64,(.+)", base64_data)
    if not match:
        return base64_data

    mime_type = match.group(1)
    base64_str = match.group(2)

    data_hash = hashlib.md5(base64_str.encode()).hexdigest()
    ext = mime_type.split("/")[-1]
    if ext == "jpeg":
        ext = "jpg"

    filename = f"{data_hash}.{ext}"
    filepath = GALLERY_IMAGES_DIR / filename

    if not filepath.exists():
        try:
            image_bytes = base64.b64decode(base64_str)
            filepath.write_bytes(image_bytes)
        except Exception:
            return base64_data

    return f"/v1/gallery/images/{filename}"


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
    supabase = get_supabase()
    rows = []
    for item in payload.items:
        db_data = _response_to_db_row(item.model_dump())
        if _is_base64_image(db_data.get("image", "")):
            db_data["image"] = _convert_base64_to_file(db_data["image"])
        rows.append(db_data)

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
        db_data["image"] = _convert_base64_to_file(db_data["image"])

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
        update_data["image"] = _convert_base64_to_file(update_data["image"])

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
        .delete()
        .eq("id", item_id)
        .execute()
    )
    return {"message": "Gallery item deleted", "id": item_id}


@router.get("/images/{filename}")
async def get_gallery_image(filename: str):
    filepath = GALLERY_IMAGES_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    ext = filepath.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")

    response = FileResponse(filepath, media_type=media_type)
    response.headers.update({"Cache-Control": "public, max-age=86400"})
    return response
