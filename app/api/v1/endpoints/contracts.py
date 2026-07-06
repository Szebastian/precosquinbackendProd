from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel

from app.core.deps import get_current_user, require_role, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


class ContractGenerate(BaseModel):
    template_id: str
    artist_ids: List[str]


class ContractResponse(BaseModel):
    id: str
    artist_id: str
    status: str
    created_at: str


@router.get("/")
async def list_contracts(
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    query = db.table("artist_contracts").select("*")

    if status:
        query = query.eq("status", status)

    result = query.order("created_at", desc=True).execute()
    return result.data


@router.post("/generate", status_code=201)
async def generate_contracts(
    request: ContractGenerate,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    contracts = []

    for artist_id in request.artist_ids:
        result = db.table("artist_contracts").insert({
            "template_id": request.template_id,
            "artist_id": artist_id,
            "status": "draft",
            "created_by": current_user.id,
        }).execute()
        contracts.append(result.data[0]["id"])

    return {"message": f"{len(contracts)} contratos generados", "contract_ids": contracts}


@router.post("/{contract_id}/send")
async def send_contract(
    contract_id: str,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    import secrets
    import hashlib

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    result = db.table("artist_contracts").update({
        "status": "sent",
        "token_hash": token_hash,
        "sent_at": "now()",
    }).eq("id", contract_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    return {"message": "Contrato enviado", "signing_link": f"/firmar/{token}"}


@router.post("/verify/{token}")
async def verify_contract_token(token: str):
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    db = get_supabase()
    result = db.table("artist_contracts").select("*").eq("token_hash", token_hash).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Token inválido")

    contract = result.data
    if contract["status"] != "sent":
        raise HTTPException(status_code=400, detail="Contrato ya fue procesado")

    return contract


@router.post("/{contract_id}/sign")
async def sign_contract(
    contract_id: str,
    signature_data: dict,
):
    db = get_supabase()
    import hashlib

    result = db.table("artist_contracts").update({
        "status": "signed",
        "signed_at": "now()",
        "signed_by_ip": signature_data.get("ip"),
    }).eq("id", contract_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    return {"message": "Contrato firmado correctamente"}