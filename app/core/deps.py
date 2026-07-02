import os
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from jose.backends.ecdsa_backend import ECDSAECKey
from typing import Optional
from pydantic import BaseModel
import httpx

from app.db.session import get_supabase

logger = structlog.get_logger(__name__)


security = HTTPBearer()


class TokenPayload(BaseModel):
    sub: str
    email: str
    role: Optional[str] = None
    org_id: Optional[str] = None
    exp: int


class CurrentUser(BaseModel):
    id: str
    email: str
    role: str
    org_id: Optional[str] = None
    permissions: list[str] = []


_jwks_cache: dict = {}


def _get_supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def _get_supabase_jwks() -> dict:
    if _jwks_cache:
        return _jwks_cache
    url = _get_supabase_url()
    if not url or url.startswith("eyJ"):
        return {}
    try:
        resp = httpx.get(f"{url}/auth/v1/.well-known/jwks.json", timeout=5)
        _jwks_cache.update(resp.json())
        return _jwks_cache
    except Exception:
        return {}


def decode_token(token: str) -> TokenPayload:
    try:
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg", "HS256")

        if alg == "ES256":
            jwks = _get_supabase_jwks()
            kid = unverified_header.get("kid")
            key = None
            for k in jwks.get("keys", []):
                if k.get("kid") == kid:
                    key = ECDSAECKey(k, "ES256")
                    break

            if key is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No se pudo encontrar la clave JWT",
                )

            payload = jwt.decode(
                token,
                key,
                algorithms=["ES256"],
                options={"verify_aud": False},
            )
        else:
            jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "")
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )

        return TokenPayload(**payload)
    except HTTPException:
        raise
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    token = credentials.credentials
    payload = decode_token(token)

    try:
        db = get_supabase()
        result = db.table("profiles").select("*").eq("id", payload.sub).single().execute()

        if result.data:
            profile = result.data
            if not profile.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Usuario desactivado",
                )
            return CurrentUser(
                id=profile["id"],
                email=profile["email"],
                role=profile.get("role", "staff"),
                org_id=profile.get("organization_id"),
                permissions=profile.get("permissions", []),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching user profile from Supabase", exc_info=e, sub=payload.sub)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor",
        )

    # No profile found - deny access
    logger.warning("User profile not found in Supabase", sub=payload.sub, email=payload.email)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Perfil de usuario no encontrado. Contacte al administrador.",
    )


async def get_current_active_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    return current_user


def require_role(*roles: str):
    async def role_checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de estos roles: {', '.join(roles)}",
            )
        return current_user
    return role_checker


def require_permission(permission: str):
    async def permission_checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if permission not in current_user.permissions and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere el permiso: {permission}",
            )
        return current_user
    return permission_checker
