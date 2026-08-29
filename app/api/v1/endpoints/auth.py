from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import httpx
import os
import structlog

from app.core.deps import get_current_user, CurrentUser, get_db
from app.core.constants import UserRole

logger = structlog.get_logger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{supabase_url}/auth/v1/token?grant_type=password",
                json={"email": request.email, "password": request.password},
                headers={"apikey": supabase_key, "Content-Type": "application/json"},
                timeout=30,
            )

        if resp.status_code != 200:
            detail = "Credenciales inválidas"
            try:
                body = resp.json()
                msg = (body.get("msg") or body.get("error_description") or "").lower()
                if "email not confirmed" in msg:
                    detail = "Email no confirmado. Desactive la confirmación de email en Supabase Dashboard > Auth > Providers > Email."
                elif "invalid" in msg or "credentials" in msg:
                    detail = "Credenciales inválidas"
            except Exception:
                pass
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

        data = resp.json()
        return LoginResponse(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=data.get("expires_in", 3600),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Error de autenticación: {str(e)}",
        )


@router.post("/register", response_model=LoginResponse)
async def register(request: RegisterRequest):
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{supabase_url}/auth/v1/signup",
                json={
                    "email": request.email,
                    "password": request.password,
                    "data": {
                        "full_name": request.full_name,
                        "role": UserRole.STAFF.value,
                    },
                },
                headers={"apikey": supabase_key, "Content-Type": "application/json"},
                timeout=30,
            )

        if resp.status_code == 200:
            data = resp.json()
            if data.get("session"):
                return LoginResponse(
                    access_token=data["session"]["access_token"],
                    refresh_token=data["session"]["refresh_token"],
                    expires_in=data["session"].get("expires_in", 3600),
                )
        elif resp.status_code == 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            msg = str(body.get("msg", body.get("error_description", ""))).lower()
            if "already registered" in msg or "user already exists" in msg:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un usuario con ese email")
            if "rate limit" in msg:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Demasiadas solicitudes. Espere un momento.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error de registro: {msg or 'error'}")

        raise HTTPException(status_code=status.HTTP_201_CREATED, detail="Usuario creado. Verifique su email para confirmar.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error de registro: {str(e)}")


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(request: RefreshRequest):
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{supabase_url}/auth/v1/token?grant_type=refresh_token",
                json={"refresh_token": request.refresh_token},
                headers={"apikey": supabase_key, "Content-Type": "application/json"},
                timeout=30,
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de refresco inválido")

        data = resp.json()
        return LoginResponse(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=data.get("expires_in", 3600),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Error al refrescar token: {str(e)}")


@router.post("/logout")
async def logout():
    return {"message": "Sesión cerrada correctamente"}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not supabase_url or not supabase_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuración de Supabase incompleta",
        )

    async with httpx.AsyncClient() as client:
        verify_resp = await client.post(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            json={"email": current_user.email, "password": request.current_password},
            headers={"apikey": supabase_key},
            timeout=10,
        )

        if verify_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La contraseña actual es incorrecta",
            )

        update_resp = await client.put(
            f"{supabase_url}/auth/v1/user",
            json={"password": request.new_password},
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {verify_resp.json().get('access_token', '')}",
            },
            timeout=10,
        )

        if update_resp.status_code not in (200, 204):
            detail = update_resp.json().get("msg", "Error al actualizar contraseña")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=detail,
            )

    return {"message": "Contraseña actualizada correctamente"}


class ProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    organization_id: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    permissions: list[str] = []
    last_login_at: Optional[str] = None


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        result = db.table("profiles").select("*").eq("id", current_user.id).single().execute()

        if result.data:
            p = result.data
            return ProfileResponse(
                id=p["id"],
                email=p["email"],
                full_name=p.get("full_name", ""),
                role=p.get("role", UserRole.STAFF.value),
                organization_id=p.get("organization_id"),
                avatar_url=p.get("avatar_url"),
                is_active=p.get("is_active", True),
                permissions=p.get("permissions", []),
                last_login_at=p.get("last_login_at"),
            )
    except Exception as e:
        logger.warning("Profile query failed, using JWT fallback", error=str(e), user_id=current_user.id)

    return ProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name="",
        role=current_user.role,
        organization_id=current_user.org_id,
        avatar_url=None,
        is_active=True,
        permissions=current_user.permissions or [],
        last_login_at=None,
    )
