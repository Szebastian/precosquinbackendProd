from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import base64
import hashlib
import re
from pathlib import Path

from app.core.deps import require_role, CurrentUser, get_db
from app.core.constants import UserRole

router = APIRouter()

# Paths for image files (Base64 conversion)
NEWS_IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "news"
NEWS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Cache headers
CACHE_HEADERS = {"Cache-Control": "no-cache, must-revalidate"}


# --- Pydantic schemas ---

class NewsItemCreate(BaseModel):
    id: Optional[int] = None
    category: str
    title: str
    description: Optional[str] = ""
    image: str
    imagePosition: Optional[str] = "center center"
    thumbType: str  # 'img' | 'icon'
    thumbSrc: str
    thumbBg: str
    sortOrder: Optional[int] = 0
    isActive: Optional[bool] = True


class NewsItemResponse(BaseModel):
    id: int
    category: str
    title: str
    description: Optional[str] = ""
    image: str
    imagePosition: Optional[str] = "center center"
    thumbType: str
    thumbSrc: str
    thumbBg: str
    sortOrder: Optional[int] = 0
    isActive: Optional[bool] = True


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
    filepath = NEWS_IMAGES_DIR / filename

    if not filepath.exists():
        try:
            image_bytes = base64.b64decode(base64_str)
            filepath.write_bytes(image_bytes)
        except Exception:
            return base64_data

    return f"/v1/news/images/{filename}"


def _db_row_to_response(row: dict) -> dict:
    """Convert DB column names to frontend camelCase format."""
    return {
        "id": row["id"],
        "category": row["category"],
        "title": row["title"],
        "description": row.get("description", ""),
        "image": row.get("image", ""),
        "imagePosition": row.get("image_position", "center center"),
        "thumbType": row.get("thumb_type", "img"),
        "thumbSrc": row.get("thumb_src", ""),
        "thumbBg": row.get("thumb_bg", "bg-blue"),
        "sortOrder": row.get("sort_order", 0),
        "isActive": row.get("is_active", True),
    }


def _response_to_db_row(item: dict) -> dict:
    """Convert frontend camelCase to DB snake_case."""
    return {
        "category": item["category"],
        "title": item["title"],
        "description": item.get("description", ""),
        "image": item.get("image", ""),
        "image_position": item.get("imagePosition", "center center"),
        "thumb_type": item.get("thumbType", "img"),
        "thumb_src": item.get("thumbSrc", ""),
        "thumb_bg": item.get("thumbBg", "bg-blue"),
        "sort_order": item.get("sortOrder", 0),
        "is_active": item.get("isActive", True),
    }


def _process_item(item: dict, truncate_description: bool = False) -> dict:
    """Convert Base64 images and optionally truncate description."""
    if _is_base64_image(item.get("image", "")):
        item["image"] = _convert_base64_to_file(item["image"])
    if _is_base64_image(item.get("thumbSrc", "")):
        item["thumbSrc"] = _convert_base64_to_file(item["thumbSrc"])
    if truncate_description and item.get("description"):
        desc = item["description"]
        if len(desc) > 200:
            item["description"] = desc[:200].rsplit(" ", 1)[0] + "..."
    return item


# --- Public endpoints ---

@router.get("/", response_model=List[NewsItemResponse])
async def get_news_list(
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db=Depends(get_db),
):
    query = db.table("noticias").select("*").eq("is_active", True).order("sort_order", desc=False)

    if limit is not None:
        if offset is not None:
            query = query.range(offset, offset + limit - 1)
        else:
            query = query.limit(limit)
    elif offset is not None:
        query = query.offset(offset)

    result = query.execute()

    items = [_db_row_to_response(row) for row in result.data]
    items = [_process_item(item, truncate_description=True) for item in items]

    response = JSONResponse(content=items)
    response.headers.update(CACHE_HEADERS)
    return response


@router.get("/images/{filename}")
async def get_news_image(filename: str):
    filepath = NEWS_IMAGES_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Imagen no encontrada")

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


@router.get("/{news_id}", response_model=NewsItemResponse)
async def get_news_item(news_id: int, db=Depends(get_db)):
    result = db.table("noticias").select("*").eq("id", news_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")

    item = _db_row_to_response(result.data[0])
    item = _process_item(item)

    response = JSONResponse(content=item)
    response.headers.update(CACHE_HEADERS)
    return response


# --- Admin endpoints ---

@router.post("/", response_model=NewsItemResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_news(
    item: NewsItemCreate,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF)),
    db=Depends(get_db),
):
    item_data = item.model_dump(exclude_unset=True)

    # Convert camelCase to snake_case for DB
    db_data = {}
    field_map = {
        "imagePosition": "image_position",
        "thumbType": "thumb_type",
        "thumbSrc": "thumb_src",
        "thumbBg": "thumb_bg",
        "sortOrder": "sort_order",
        "isActive": "is_active",
    }
    for key, value in item_data.items():
        db_key = field_map.get(key, key)
        db_data[db_key] = value

    # Process Base64 images
    if _is_base64_image(db_data.get("image", "")):
        db_data["image"] = _convert_base64_to_file(db_data["image"])
    if _is_base64_image(db_data.get("thumb_src", "")):
        db_data["thumb_src"] = _convert_base64_to_file(db_data["thumb_src"])

    if item.id:
        # Update existing
        result = db.table("noticias").update(db_data).eq("id", item.id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Noticia no encontrada")
        return NewsItemResponse(**_db_row_to_response(result.data[0]))
    else:
        # Create new
        result = db.table("noticias").insert(db_data).execute()
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al crear la noticia",
            )
        return NewsItemResponse(**_db_row_to_response(result.data[0]))


@router.delete("/{news_id}", status_code=status.HTTP_200_OK)
async def delete_news(
    news_id: int,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN)),
    db=Depends(get_db),
):
    result = db.table("noticias").delete().eq("id", news_id).execute()

    return {"message": "Noticia eliminada correctamente"}
