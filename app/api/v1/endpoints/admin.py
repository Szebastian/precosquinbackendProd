import os
import httpx
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel, EmailStr

from app.core.deps import require_role, CurrentUser, get_db
from app.core.constants import UserRole
from app.core.utils import generate_temp_password, exclude_none, log_audit

router = APIRouter()


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
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    query = db.table("profiles").select("*")

    if role:
        query = query.eq("role", role)

    result = query.order("created_at", desc=True).execute()
    return result.data


@router.post("/users/sync", status_code=200)
async def sync_auth_users(
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    async with httpx.AsyncClient(timeout=15) as client:
        auth_resp = await client.get(
            f"{supabase_url}/auth/v1/admin/users",
            headers={
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key,
            },
        )

    if auth_resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Error al obtener usuarios de auth")

    auth_users = auth_resp.json().get("users", [])

    existing = db.table("profiles").select("id").execute()
    existing_ids = {p["id"] for p in (existing.data or [])}

    synced = []
    for u in auth_users:
        uid = u.get("id")
        if uid and uid not in existing_ids:
            meta = u.get("user_metadata") or {}
            db.table("profiles").insert({
                "id": uid,
                "email": u.get("email", ""),
                "full_name": meta.get("full_name", u.get("email", "")),
                "role": meta.get("role", "staff"),
                "is_active": True,
            }).execute()
            synced.append(u.get("email"))

    return {"synced": len(synced), "emails": synced}


@router.post("/users/invite", status_code=201)
async def invite_user(
    user: UserInvite,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    valid_roles = [r.value for r in UserRole]
    if user.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Rol inválido. Debe ser uno de: {', '.join(valid_roles)}",
        )

    temp_password = generate_temp_password()

    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            auth_resp = await client.post(
                f"{supabase_url}/auth/v1/admin/users",
                headers={
                    "Authorization": f"Bearer {supabase_key}",
                    "apikey": supabase_key,
                    "Content-Type": "application/json",
                },
                json={
                    "email": user.email,
                    "password": temp_password,
                    "email_confirm": True,
                    "user_metadata": {
                        "full_name": user.full_name,
                        "role": user.role,
                    },
                },
            )

        if auth_resp.status_code not in (200, 201):
            error_detail = auth_resp.json() if auth_resp.headers.get("content-type", "").startswith("application/json") else {"message": auth_resp.text}
            error_msg = str(error_detail).lower()
            if "already" in error_msg or "already exists" in error_msg or auth_resp.status_code == 409:
                raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")
            raise HTTPException(
                status_code=500,
                detail=f"Error al crear usuario en auth: {error_detail}",
            )

        user_id = auth_resp.json().get("id")
        if not user_id:
            raise HTTPException(status_code=400, detail="Error al crear usuario en auth: sin ID")

        db.table("profiles").insert({
            "id": user_id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": True,
        }).execute()

        log_audit(
            db=db,
            actor_id=current_user.id,
            action="user_invited",
            target_id=user_id,
            metadata={"email": user.email, "role": user.role},
        )

        return {
            "id": user_id,
            "email": user.email,
            "temp_password": temp_password,
            "message": f"Invitación enviada a {user.email}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear usuario: {str(e)}")


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    user: UserUpdate,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    update_data = exclude_none(user)

    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")

    result = db.table("profiles").update(update_data).eq("id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="user_updated",
        target_id=user_id,
        metadata=update_data,
    )

    return {"message": "Usuario actualizado correctamente"}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")

    result = db.table("profiles").update({"is_active": False}).eq("id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="user_deactivated",
        target_id=user_id,
    )

    return {"message": "Usuario desactivado correctamente"}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes resetear tu propia contraseña desde aquí")

    profile = db.table("profiles").select("id, email, full_name").eq("id", user_id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    temp_password = generate_temp_password()

    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            auth_resp = await client.put(
                f"{supabase_url}/auth/v1/admin/users/{user_id}",
                headers={
                    "Authorization": f"Bearer {supabase_key}",
                    "apikey": supabase_key,
                    "Content-Type": "application/json",
                },
                json={
                    "password": temp_password,
                },
            )

        if auth_resp.status_code not in (200,):
            raise HTTPException(
                status_code=500,
                detail=f"Error al resetear contraseña en auth: {auth_resp.text}",
            )

        log_audit(
            db=db,
            actor_id=current_user.id,
            action="user_password_reset",
            target_id=user_id,
            metadata={"email": profile.data["email"]},
        )

        return {
            "id": user_id,
            "email": profile.data["email"],
            "full_name": profile.data["full_name"],
            "temp_password": temp_password,
            "message": f"Contraseña reseteada para {profile.data['email']}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al resetear contraseña: {str(e)}")


@router.get("/event-config")
async def get_event_config(
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    result = db.table("event_config").select("*").single().execute()
    return result.data or {}


@router.patch("/event-config")
async def update_event_config(
    config: EventConfigUpdate,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    update_data = exclude_none(config)

    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")

    db.table("event_config").upsert({
        "id": 1,
        **update_data,
        "updated_at": "now()",
    }).execute()

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="event_config_updated",
        metadata=update_data,
    )

    return {"message": "Configuración actualizada correctamente"}


@router.get("/capacities")
async def get_capacities(
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    result = db.table("edition_capacities").select("*").execute()
    return result.data


@router.patch("/capacities")
async def update_capacities(
    capacities: List[dict],
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    for cap in capacities:
        db.table("edition_capacities").upsert(cap).execute()

    return {"message": "Cupos actualizados correctamente"}


@router.get("/audit-logs")
async def list_audit_logs(
    action: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    query = db.table("audit_logs").select("*")

    if action:
        query = query.eq("action", action)

    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data