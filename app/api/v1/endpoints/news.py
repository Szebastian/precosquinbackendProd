from fastapi import APIRouter, HTTPException, Depends, status, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import base64
import hashlib
import re
from pathlib import Path

from app.core.deps import require_role, CurrentUser

router = APIRouter()

# Paths
NEWS_FILE = Path(__file__).resolve().parent.parent.parent / "news.json"
NEWS_IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "news"
NEWS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Cache headers
CACHE_HEADERS = {"Cache-Control": "public, max-age=300, stale-while-revalidate=60"}


class NewsItem(BaseModel):
    id: Optional[int] = None
    category: str
    title: str
    description: Optional[str] = ""
    image: str
    imagePosition: Optional[str] = "center center"
    thumbType: str  # 'img' | 'icon'
    thumbSrc: str
    thumbBg: str


# Default news items as fallback
DEFAULT_NEWS = [
    {
        "id": 1,
        "category": "FESTIVAL 2026",
        "title": "Se abren las inscripciones para el certamen Nuevos Valores",
        "description": "El Pre Cosquín Puerto Pirámides abre sus puertas a nuevos talentos del folklore argentino. El certamen Nuevos Valores está dirigido a artistas emergentes que buscan dar a conocer su arte en uno de los escenarios más importantes del folklorismo patagónico. Las inscripciones están abiertas para los rubros de Música y Danza, con categorías que incluyen solistas, dúos, conjuntos y más. No perdás la oportunidad de formar parte de esta experiencia única.",
        "image": "assets/home-background.jpg",
        "thumbType": "img",
        "thumbSrc": "assets/img/cruzBaila.png",
        "thumbBg": "bg-blue"
    },
    {
        "id": 2,
        "category": "JURADO",
        "title": "Capacitación para el jurado de danza en el Hotel Rayentray",
        "description": "Los integrantes del jurado de la categoría Danza se reunieron en el Hotel Rayentray de Puerto Madryn para una jornada de capacitación y puesta en común. El encuentro contó con la presencia de reconocidos bailarines y coreógrafos folclóricos que compartieron sus experiencias y criterios de evaluación. Esta preparación garantiza un análisis justo y profesional de todas las presentaciones del certamen.",
        "image": "assets/rayentray.png",
        "thumbType": "img",
        "thumbSrc": "assets/img/cruzBaila.png",
        "thumbBg": "bg-blue"
    },
    {
        "id": 3,
        "category": "REGLAMENTO",
        "title": "Modificación en el reglamento del rubro 'Solista Vocal'",
        "description": "Se realizó una actualización importante en el reglamento correspondiente al rubro Solista Vocal. Los cambios incluyen la posibilidad de incluir acompañamiento instrumental acústico, la ampliación del tiempo máximo de presentación a 12 minutos y la obligatoriedad de incluir al menos una obra de autor regional. Estas modificaciones buscan enriquecer la calidad artística del certamen y valorar la producción local.",
        "image": "assets/hidro.jpeg",
        "thumbType": "icon",
        "thumbSrc": '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/></svg>',
        "thumbBg": "bg-gold"
    },
    {
        "id": 4,
        "category": "CRONOGRAMA",
        "title": "Cronograma oficial de la primera ronda clasificatoria",
        "description": "Se dio a conocer el cronograma completo de la primera ronda clasificatoria del Pre Cosquín 2026. Las presentaciones comenzarán el sábado 5 de septiembre a las 10:00 horas en el stage principal de Puerto Pirámides. Los rubros de Música se presentarán por la mañana y los de Danza por la tarde. Se recuerda a los participantes presentarse 30 minutos antes de su horario asignado para la revisión de documentación.",
        "image": "assets/home-background.jpg",
        "thumbType": "icon",
        "thumbSrc": '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
        "thumbBg": "bg-gray"
    }
]


def _is_base64_image(data: str) -> bool:
    """Check if a string is a Base64-encoded image data URL."""
    return data.startswith("data:image/")


def _convert_base64_to_file(base64_data: str) -> str:
    """Convert a Base64 data URL to a file and return the URL path."""
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


def _process_news_item(item: dict, truncate_description: bool = False) -> dict:
    """Convert Base64 images to file URLs in a news item."""
    processed = dict(item)
    if _is_base64_image(processed.get("image", "")):
        processed["image"] = _convert_base64_to_file(processed["image"])
    if _is_base64_image(processed.get("thumbSrc", "")):
        processed["thumbSrc"] = _convert_base64_to_file(processed["thumbSrc"])
    if truncate_description and "description" in processed and processed["description"]:
        desc = processed["description"]
        if len(desc) > 200:
            processed["description"] = desc[:200].rsplit(" ", 1)[0] + "..."
    return processed


def load_news() -> List[dict]:
    if not NEWS_FILE.exists():
        with open(NEWS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_NEWS, f, ensure_ascii=False, indent=2)
        return DEFAULT_NEWS
    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_NEWS


def save_news(news_list: List[dict]):
    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)


@router.get("/", response_model=List[NewsItem])
async def get_news_list(
    limit: Optional[int] = None,
    offset: Optional[int] = None,
):
    news_list = load_news()

    if limit is not None:
        news_list = news_list[offset:offset + limit] if offset else news_list[:limit]
    elif offset is not None:
        news_list = news_list[offset:]

    processed = [_process_news_item(item, truncate_description=True) for item in news_list]
    response = JSONResponse(content=processed)
    response.headers.update(CACHE_HEADERS)
    return response


@router.get("/images/{filename}")
async def get_news_image(filename: str):
    """Serve a news image file."""
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


@router.get("/{news_id}", response_model=NewsItem)
async def get_news_item(news_id: int):
    news_list = load_news()
    for item in news_list:
        if item.get("id") == news_id:
            processed = _process_news_item(item)
            response = JSONResponse(content=processed)
            response.headers.update(CACHE_HEADERS)
            return response
    raise HTTPException(status_code=404, detail="Noticia no encontrada")


@router.post("/", response_model=NewsItem, status_code=status.HTTP_201_CREATED)
async def create_or_update_news(
    item: NewsItem,
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff"))
):
    news_list = load_news()

    item_dict = item.model_dump()
    if _is_base64_image(item_dict.get("image", "")):
        item_dict["image"] = _convert_base64_to_file(item_dict["image"])
    if _is_base64_image(item_dict.get("thumbSrc", "")):
        item_dict["thumbSrc"] = _convert_base64_to_file(item_dict["thumbSrc"])

    if item.id:
        for idx, existing in enumerate(news_list):
            if existing.get("id") == item.id:
                news_list[idx] = item_dict
                save_news(news_list)
                return item
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    else:
        next_id = max([x.get("id", 0) for x in news_list]) + 1 if news_list else 1
        item_dict["id"] = next_id
        news_list.append(item_dict)
        save_news(news_list)
        return NewsItem(**item_dict)


@router.delete("/{news_id}", status_code=status.HTTP_200_OK)
async def delete_news(
    news_id: int,
    current_user: CurrentUser = Depends(require_role("organizador", "admin"))
):
    news_list = load_news()
    filtered = [x for x in news_list if x.get("id") != news_id]
    if len(filtered) == len(news_list):
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    save_news(filtered)
    return {"message": "Noticia eliminada correctamente"}
