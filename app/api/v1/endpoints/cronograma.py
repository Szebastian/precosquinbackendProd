from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel

from app.core.deps import get_current_user, require_role, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


# ─── Pydantic Models ───────────────────────────────

class PresentationResponse(BaseModel):
    id: str
    order: int
    time: Optional[str]
    category: str
    subcategory: str
    participantName: str
    groupName: Optional[str]
    stage: Optional[str]
    day: Optional[str]
    observations: Optional[str]
    status: str
    createdAt: str
    updatedAt: str


class PresentationListResponse(BaseModel):
    data: List[PresentationResponse]
    total: int


class PresentationCreate(BaseModel):
    order: int = 0
    time: Optional[str] = None
    category: str = ""
    subcategory: str = ""
    participantName: str = ""
    groupName: Optional[str] = None
    stage: Optional[str] = None
    day: Optional[str] = None
    observations: Optional[str] = None
    status: str = "published"


class AgendaEventResponse(BaseModel):
    id: str
    time: Optional[str]
    title: str
    description: Optional[str]
    location: Optional[str]
    eventType: str
    day: Optional[str]
    status: str
    createdAt: str
    updatedAt: str


class AgendaListResponse(BaseModel):
    data: List[AgendaEventResponse]
    total: int


class AgendaEventCreate(BaseModel):
    time: Optional[str] = None
    title: str = ""
    description: Optional[str] = None
    location: Optional[str] = None
    eventType: str = "other"
    day: Optional[str] = None
    status: str = "published"


# ─── Helpers ───────────────────────────────────────

def _map_presentation(row: dict) -> PresentationResponse:
    return PresentationResponse(
        id=row["id"],
        order=row.get("display_order", 0),
        time=row.get("time"),
        category=row.get("category", ""),
        subcategory=row.get("subcategory", ""),
        participantName=row.get("participant_name", ""),
        groupName=row.get("group_name"),
        stage=row.get("stage"),
        day=row.get("day"),
        observations=row.get("observations"),
        status=row.get("status", "published"),
        createdAt=row.get("created_at", ""),
        updatedAt=row.get("updated_at", ""),
    )


def _map_agenda_event(row: dict) -> AgendaEventResponse:
    return AgendaEventResponse(
        id=row["id"],
        time=row.get("time"),
        title=row.get("title", ""),
        description=row.get("description"),
        location=row.get("location"),
        eventType=row.get("event_type", "other"),
        day=row.get("day"),
        status=row.get("status", "published"),
        createdAt=row.get("created_at", ""),
        updatedAt=row.get("updated_at", ""),
    )


# ─── Public Endpoints (no auth required) ──────────

@router.get("/presentations", response_model=PresentationListResponse)
async def list_presentations(
    search: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    stage: Optional[str] = None,
    day: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    db = get_supabase()
    query = db.table("presentations").select("*").eq("status", "published")

    if search:
        term = f"%{search}%"
        query = query.or_(
            f"participant_name.ilike.{term},"
            f"group_name.ilike.{term},"
            f"category.ilike.{term},"
            f"subcategory.ilike.{term}"
        )
    if category:
        query = query.eq("category", category)
    if subcategory:
        query = query.eq("subcategory", subcategory)
    if stage:
        query = query.eq("stage", stage)
    if day:
        query = query.eq("day", day)

    count_result = query.execute()
    total = len(count_result.data) if count_result.data else 0

    offset = (page - 1) * page_size
    result = query.order("display_order").range(offset, offset + page_size - 1).execute()

    return PresentationListResponse(
        data=[_map_presentation(row) for row in (result.data or [])],
        total=total,
    )


@router.get("/presentations/{presentation_id}", response_model=PresentationResponse)
async def get_presentation(presentation_id: str):
    db = get_supabase()
    result = db.table("presentations").select("*").eq("id", presentation_id).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Presentación no encontrada")

    return _map_presentation(result.data)


@router.get("/agenda", response_model=AgendaListResponse)
async def list_agenda(
    search: Optional[str] = None,
    day: Optional[str] = None,
    event_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    db = get_supabase()
    query = db.table("agenda_events").select("*").eq("status", "published")

    if search:
        term = f"%{search}%"
        query = query.or_(
            f"title.ilike.{term},"
            f"description.ilike.{term},"
            f"location.ilike.{term}"
        )
    if day:
        query = query.eq("day", day)
    if event_type:
        query = query.eq("event_type", event_type)

    count_result = query.execute()
    total = len(count_result.data) if count_result.data else 0

    offset = (page - 1) * page_size
    result = query.order("time").range(offset, offset + page_size - 1).execute()

    return AgendaListResponse(
        data=[_map_agenda_event(row) for row in (result.data or [])],
        total=total,
    )


@router.get("/agenda/{event_id}", response_model=AgendaEventResponse)
async def get_agenda_event(event_id: str):
    db = get_supabase()
    result = db.table("agenda_events").select("*").eq("id", event_id).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Evento de agenda no encontrado")

    return _map_agenda_event(result.data)


# ─── Admin Endpoints (auth required) ──────────────

@router.post("/presentations", response_model=PresentationResponse, status_code=201)
async def create_presentation(
    data: PresentationCreate,
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff")),
):
    db = get_supabase()
    result = db.table("presentations").insert({
        "display_order": data.order,
        "time": data.time,
        "category": data.category,
        "subcategory": data.subcategory,
        "participant_name": data.participantName,
        "group_name": data.groupName,
        "stage": data.stage,
        "day": data.day,
        "observations": data.observations,
        "status": data.status,
    }).execute()

    return _map_presentation(result.data[0])


@router.patch("/presentations/{presentation_id}", response_model=PresentationResponse)
async def update_presentation(
    presentation_id: str,
    data: PresentationCreate,
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff")),
):
    db = get_supabase()
    result = db.table("presentations").update({
        "display_order": data.order,
        "time": data.time,
        "category": data.category,
        "subcategory": data.subcategory,
        "participant_name": data.participantName,
        "group_name": data.groupName,
        "stage": data.stage,
        "day": data.day,
        "observations": data.observations,
        "status": data.status,
    }).eq("id", presentation_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Presentación no encontrada")

    return _map_presentation(result.data[0])


@router.delete("/presentations/{presentation_id}")
async def delete_presentation(
    presentation_id: str,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    result = db.table("presentations").delete().eq("id", presentation_id).execute()
    return {"message": "Presentación eliminada correctamente"}


@router.post("/agenda", response_model=AgendaEventResponse, status_code=201)
async def create_agenda_event(
    data: AgendaEventCreate,
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff")),
):
    db = get_supabase()
    result = db.table("agenda_events").insert({
        "time": data.time,
        "title": data.title,
        "description": data.description,
        "location": data.location,
        "event_type": data.eventType,
        "day": data.day,
        "status": data.status,
    }).execute()

    return _map_agenda_event(result.data[0])


@router.patch("/agenda/{event_id}", response_model=AgendaEventResponse)
async def update_agenda_event(
    event_id: str,
    data: AgendaEventCreate,
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff")),
):
    db = get_supabase()
    result = db.table("agenda_events").update({
        "time": data.time,
        "title": data.title,
        "description": data.description,
        "location": data.location,
        "event_type": data.eventType,
        "day": data.day,
        "status": data.status,
    }).eq("id", event_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Evento de agenda no encontrado")

    return _map_agenda_event(result.data[0])


@router.delete("/agenda/{event_id}")
async def delete_agenda_event(
    event_id: str,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    result = db.table("agenda_events").delete().eq("id", event_id).execute()
    return {"message": "Evento de agenda eliminado correctamente"}
