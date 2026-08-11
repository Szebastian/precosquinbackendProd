from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel, EmailStr
import secrets
import string
import os
import structlog
import httpx

from app.core.deps import get_current_user, require_role, CurrentUser
from app.core.email import EmailMessage, get_email_sender
from app.db.session import get_supabase
from app.api.v1.endpoints.admin import _send_invite_email

logger = structlog.get_logger(__name__)

router = APIRouter()


def _get_supabase_creds():
    return (
        os.environ.get("SUPABASE_URL", "").rstrip("/"),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
    )


def _auth_headers(supabase_key):
    return {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
        "Content-Type": "application/json",
    }


async def _rest_insert(supabase_url, supabase_key, table, data):
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{supabase_url}/rest/v1/{table}",
            headers={**_auth_headers(supabase_key), "Prefer": "return=representation"},
            json=data,
        )
    if resp.status_code in (200, 201, 204):
        data_out = resp.json()
        return data_out[0] if isinstance(data_out, list) and data_out else data_out
    return None


async def _rest_update(supabase_url, supabase_key, table, data, filters):
    query = "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    url = f"{supabase_url}/rest/v1/{table}?{query}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            url,
            headers={**_auth_headers(supabase_key), "Prefer": "return=representation"},
            json=data,
        )
    if resp.status_code in (200, 204):
        data_out = resp.json()
        return data_out[0] if isinstance(data_out, list) and data_out else data_out
    return None


def generate_temp_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(length))


class JuryInvite(BaseModel):
    email: EmailStr
    full_name: str


class EvaluationCreate(BaseModel):
    artist_id: str
    assignment_id: str
    rubric_id: str
    scores: dict
    comments: dict


class EvaluationResponse(BaseModel):
    id: str
    artist_id: str
    jury_id: str
    status: str
    total_score: Optional[float]
    submitted_at: Optional[str]


@router.get("/members")
async def list_jury_members(
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    result = db.table("profiles").select("*").eq("role", "jurado").order("created_at", desc=True).execute()
    return result.data


@router.post("/members/invite", status_code=201)
async def invite_jury_member(
    member: JuryInvite,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    temp_password = generate_temp_password()
    supabase_url, supabase_key = _get_supabase_creds()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            auth_resp = await client.post(
                f"{supabase_url}/auth/v1/admin/users",
                headers=_auth_headers(supabase_key),
                json={
                    "email": member.email,
                    "password": temp_password,
                    "email_confirm": True,
                    "user_metadata": {
                        "full_name": member.full_name,
                        "role": "jurado",
                    },
                },
            )

        if auth_resp.status_code not in (200, 201):
            error_detail = auth_resp.json() if auth_resp.headers.get("content-type", "").startswith("application/json") else {"message": auth_resp.text}
            error_msg = str(error_detail).lower()
            if "already" in error_msg or "already exists" in error_msg or auth_resp.status_code == 409:
                raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")
            raise HTTPException(status_code=500, detail=f"Error al crear usuario en auth: {error_detail}")

        user_id = auth_resp.json().get("id")
        if not user_id:
            raise HTTPException(status_code=400, detail="Error al crear usuario en auth: sin ID")

        await _rest_insert(supabase_url, supabase_key, "profiles", {
            "id": user_id,
            "email": member.email,
            "full_name": member.full_name,
            "role": "jurado",
            "is_active": True,
        })

        db = get_supabase()
        db.table("audit_logs").insert({
            "actor_id": current_user.id,
            "action": "jury_invited",
            "target_id": user_id,
            "metadata": {"email": member.email},
        }).execute()

        _send_invite_email(member.email, member.full_name, temp_password, "jurado")

        return {
            "id": user_id,
            "email": member.email,
            "full_name": member.full_name,
            "temp_password": temp_password,
            "message": f"Invitación enviada a {member.email}",
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "already" in error_msg or "already exists" in error_msg:
            raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")
        raise HTTPException(status_code=500, detail=f"Error al crear jurado: {str(e)}")


@router.delete("/members/{member_id}")
async def remove_jury_member(
    member_id: str,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    supabase_url, supabase_key = _get_supabase_creds()
    result = await _rest_update(supabase_url, supabase_key, "profiles", {"is_active": False, "role": "staff"}, {"id": member_id})

    if not result:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    db = get_supabase()
    db.table("audit_logs").insert({
        "actor_id": current_user.id,
        "action": "jury_removed",
        "target_id": member_id,
    }).execute()

    return {"message": "Miembro removido del jurado"}


@router.get("/assignments")
async def list_assignments(current_user: CurrentUser = Depends(require_role("jurado", "organizador", "admin"))):
    db = get_supabase()
    result = db.table("jury_assignments").select("*").eq("jury_id", current_user.id).execute()
    return result.data


@router.get("/rubrics/{subcategory_id}")
async def get_rubric(subcategory_id: str, current_user: CurrentUser = Depends(get_current_user)):
    db = get_supabase()
    result = db.table("rubrics").select("*").eq("subcategory_id", subcategory_id).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Rúbrica no encontrada")

    return result.data


@router.post("/evaluations", status_code=201)
async def create_evaluation(
    evaluation: EvaluationCreate,
    current_user: CurrentUser = Depends(require_role("jurado")),
):
    db = get_supabase()
    result = db.table("evaluations").insert({
        **evaluation.model_dump(),
        "jury_id": current_user.id,
        "status": "DRAFT",
    }).execute()

    return EvaluationResponse(**result.data[0])


@router.patch("/evaluations/{evaluation_id}/submit")
async def submit_evaluation(
    evaluation_id: str,
    current_user: CurrentUser = Depends(require_role("jurado")),
):
    db = get_supabase()
    result = db.table("evaluations").update({
        "status": "SUBMITTED",
        "submitted_at": "now()",
    }).eq("id", evaluation_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    return {"message": "Evaluación enviada correctamente"}


@router.get("/evaluations/{evaluation_id}")
async def get_evaluation(evaluation_id: str, current_user: CurrentUser = Depends(get_current_user)):
    db = get_supabase()
    result = db.table("evaluations").select("*").eq("id", evaluation_id).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    return result.data


@router.get("/results/{subcategory_id}")
async def get_results(
    subcategory_id: str,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    result = db.table("evaluations").select("*").eq("subcategory_id", subcategory_id).eq("status", "SUBMITTED").execute()
    return result.data
