from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel, EmailStr
import secrets
import string

from app.core.deps import require_role, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


def generate_temp_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(length))


class UserInvite(BaseModel):
    email: EmailStr
    full_name: str
    role: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class EventConfigUpdate(BaseModel):
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    cupos: Optional[dict] = None
    reglas: Optional[dict] = None
    inscription_open: Optional[bool] = None


@router.get("/users")
async def list_users(
    role: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    db = get_supabase()
    query = db.table("profiles").select("*")

    if role:
        query = query.eq("role", role)

    result = query.order("created_at", desc=True).execute()
    return result.data


@router.post("/users/invite", status_code=201)
async def invite_user(
    user: UserInvite,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    valid_roles = ["jurado", "organizador", "admin", "staff"]
    if user.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Rol inválido. Debe ser uno de: {', '.join(valid_roles)}",
        )

    db = get_supabase()
    temp_password = generate_temp_password()

    try:
        auth_result = db.auth.admin.create_user({
            "email": user.email,
            "password": temp_password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": user.full_name,
                "role": user.role,
            }
        })

        if not auth_result.user:
            raise HTTPException(status_code=400, detail="Error al crear usuario en auth")

        user_id = auth_result.user.id

        db.table("profiles").insert({
            "id": user_id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": True,
        }).execute()

        db.table("audit_logs").insert({
            "actor_id": current_user.id,
            "action": "user_invited",
            "target_id": user_id,
            "metadata": {"email": user.email, "role": user.role},
        }).execute()

        return {
            "id": user_id,
            "email": user.email,
            "temp_password": temp_password,
            "message": f"Invitación enviada a {user.email}",
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "already" in error_msg or "already exists" in error_msg:
            raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")
        raise HTTPException(status_code=500, detail=f"Error al crear usuario: {str(e)}")


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    user: UserUpdate,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    db = get_supabase()
    update_data = {k: v for k, v in user.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")

    result = db.table("profiles").update(update_data).eq("id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db.table("audit_logs").insert({
        "actor_id": current_user.id,
        "action": "user_updated",
        "target_id": user_id,
        "metadata": update_data,
    }).execute()

    return {"message": "Usuario actualizado correctamente"}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")

    db = get_supabase()
    result = db.table("profiles").update({"is_active": False}).eq("id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db.table("audit_logs").insert({
        "actor_id": current_user.id,
        "action": "user_deactivated",
        "target_id": user_id,
    }).execute()

    return {"message": "Usuario desactivado correctamente"}


@router.get("/event-config")
async def get_event_config(current_user: CurrentUser = Depends(require_role("admin"))):
    db = get_supabase()
    result = db.table("event_config").select("*").single().execute()
    return result.data or {}


@router.patch("/event-config")
async def update_event_config(
    config: EventConfigUpdate,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    db = get_supabase()
    update_data = {k: v for k, v in config.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")

    result = db.table("event_config").upsert({
        "id": 1,
        **update_data,
        "updated_at": "now()",
    }).execute()

    db.table("audit_logs").insert({
        "actor_id": current_user.id,
        "action": "event_config_updated",
        "metadata": update_data,
    }).execute()

    return {"message": "Configuración actualizada correctamente"}


@router.get("/capacities")
async def get_capacities(current_user: CurrentUser = Depends(require_role("admin"))):
    db = get_supabase()
    result = db.table("edition_capacities").select("*").execute()
    return result.data


@router.patch("/capacities")
async def update_capacities(
    capacities: List[dict],
    current_user: CurrentUser = Depends(require_role("admin")),
):
    db = get_supabase()

    for cap in capacities:
        db.table("edition_capacities").upsert(cap).execute()

    return {"message": "Cupos actualizados correctamente"}


@router.get("/audit-logs")
async def list_audit_logs(
    action: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_role("admin")),
):
    db = get_supabase()
    query = db.table("audit_logs").select("*")

    if action:
        query = query.eq("action", action)

    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data