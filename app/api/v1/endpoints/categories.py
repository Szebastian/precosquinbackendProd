from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()


class SubcategoryResponse(BaseModel):
    id: str
    name: str
    description: str


class CategoryResponse(BaseModel):
    id: str
    name: str
    type: str
    subcategories: List[SubcategoryResponse]


CATEGORIES = [
    {
        "id": "musica",
        "name": "Música",
        "type": "MUSICA",
        "subcategories": [
            {"id": "solista_vocal", "name": "Solista Vocal", "description": "Artista solista vocal"},
            {"id": "solista_instrumental", "name": "Solista Instrumental", "description": "Artista solista instrumental"},
            {"id": "conjunto_instrumental", "name": "Conjunto Instrumental", "description": "Grupo instrumental"},
            {"id": "conjunto_vocal", "name": "Conjunto Vocal", "description": "Grupo vocal"},
            {"id": "tema_inedito", "name": "Tema Inédito", "description": "Obra inédita original"},
        ],
    },
    {
        "id": "danza",
        "name": "Danza",
        "type": "DANZA",
        "subcategories": [
            {"id": "malambo_masculino", "name": "Solista de Malambo Masculino", "description": "Malambo solista masculino"},
            {"id": "malambo_femenino", "name": "Solista de Malambo Femenino", "description": "Malambo solista femenino"},
            {"id": "pareja_tradicional", "name": "Pareja Tradicional", "description": "Pareja de baile tradicional"},
            {"id": "pareja_estilizada", "name": "Pareja Estilizada", "description": "Pareja de baile estilizada"},
            {"id": "conjunto_malambo", "name": "Conjunto de Malambo", "description": "Grupo de malambo"},
            {"id": "conjunto_baile_folklorico", "name": "Conjunto de Baile Folklórico", "description": "Grupo de baile folklórico"},
        ],
    },
]


@router.get("/", response_model=List[CategoryResponse])
async def list_categories():
    return CATEGORIES


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: str):
    category = next((c for c in CATEGORIES if c["id"] == category_id), None)
    if not category:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return category


@router.get("/{category_id}/subcategories", response_model=List[SubcategoryResponse])
async def get_subcategories(category_id: str):
    category = next((c for c in CATEGORIES if c["id"] == category_id), None)
    if not category:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return category["subcategories"]