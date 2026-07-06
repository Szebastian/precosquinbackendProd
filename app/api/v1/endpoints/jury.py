from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel, EmailStr
import secrets
import string

from app.core.deps import get_current_user, require_role, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


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
    db = get_supabase()
    temp_password = generate_temp_password()

    try:
        auth_result = db.auth.admin.create_user({
            "email": member.email,
            "password": temp_password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": member.full_name,
                "role": "jurado",
            }
        })

        if not auth_result.user:
            raise HTTPException(status_code=400, detail="Error al crear usuario en auth")

        user_id = auth_result.user.id

        db.table("profiles").insert({
            "id": user_id,
            "email": member.email,
            "full_name": member.full_name,
            "role": "jurado",
            "is_active": True,
        }).execute()

        db.table("audit_logs").insert({
            "actor_id": current_user.id,
            "action": "jury_invited",
            "target_id": user_id,
            "metadata": {"email": member.email},
        }).execute()

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
    db = get_supabase()
    result = db.table("profiles").update({"is_active": False, "role": "staff"}).eq("id", member_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

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