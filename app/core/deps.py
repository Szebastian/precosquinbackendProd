import os
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt  # type: ignore
from jose.backends.ecdsa_backend import ECDSAECKey  # type: ignore
from typing import Optional, Any
from pydantic import BaseModel
import httpx

from app.db.session import get_supabase

logger = structlog.get_logger(__name__)

security = HTTPBearer()


def get_db():
    """Dependency that yields an initialized Supabase database client or raises HTTP 503."""
    try:
        return get_supabase()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Base de datos no disponible: {str(e)}",
        )


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

        metadata = payload.get("user_metadata", {}) or {}
        role = metadata.get("role") or (payload.get("role") if payload.get("role") not in ("authenticated",) else None) or "staff"
        org_id = metadata.get("organization_id") or payload.get("org_id")

        return TokenPayload(
            sub=payload.get("sub", ""),
            email=payload.get("email", ""),
            role=role,
            org_id=org_id,
            exp=payload.get("exp", 0),
        )
    except HTTPException:
        raise
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Any = Depends(get_db),
) -> CurrentUser:
    token = credentials.credentials
    payload = decode_token(token)

    try:
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
        logger.warning("Profile lookup failed, falling back to JWT", error=str(e), sub=payload.sub, email=payload.email, jwt_role=payload.role)
        return CurrentUser(
            id=payload.sub,
            email=payload.email or "",
            role=payload.role or "staff",
            org_id=payload.org_id,
            permissions=[],
        )

    logger.warning("User profile not found in Supabase", sub=payload.sub, email=payload.email)
    return CurrentUser(
        id=payload.sub,
        email=payload.email or "",
        role=payload.role or "staff",
        org_id=payload.org_id,
        permissions=[],
    )


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
