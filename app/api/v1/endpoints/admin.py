import os
import structlog
import httpx
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel, EmailStr

from app.core.deps import require_role, CurrentUser, get_db
from app.core.constants import UserRole
from app.core.utils import generate_temp_password, exclude_none, log_audit
from app.core.email import EmailMessage, get_email_sender

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


async def _rest_select(supabase_url, supabase_key, table, filters=None, single=False):
    query_parts = []
    if filters:
        for col, val in filters.items():
            query_parts.append(f"{col}=eq.{val}")
    query = "&".join(query_parts) if query_parts else ""
    url = f"{supabase_url}/rest/v1/{table}?select=*"
    if query:
        url += f"&{query}"
    if single:
        url += "&limit=1"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=_auth_headers(supabase_key))
        if resp.status_code == 200:
            data = resp.json()
            return data[0] if single and data else data
    except Exception as e:
        logger.warning("REST select failed", table=table, error=str(e))
    return None if single else []


async def _rest_insert(supabase_url, supabase_key, table, data):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{supabase_url}/rest/v1/{table}",
                headers={**_auth_headers(supabase_key), "Prefer": "return=representation"},
                json=data,
            )
        if resp.status_code in (200, 201, 204):
            data_out = resp.json()
            return data_out[0] if isinstance(data_out, list) and data_out else data_out
    except Exception as e:
        logger.warning("REST insert failed", table=table, error=str(e))
    return None


async def _rest_update(supabase_url, supabase_key, table, data, filters):
    query = "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    url = f"{supabase_url}/rest/v1/{table}?{query}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                url,
                headers={**_auth_headers(supabase_key), "Prefer": "return=representation"},
                json=data,
            )
        if resp.status_code in (200, 204):
            data_out = resp.json()
            return data_out[0] if isinstance(data_out, list) and data_out else data_out
    except Exception as e:
        logger.warning("REST update failed", table=table, error=str(e))
    return None


async def _rest_delete(supabase_url, supabase_key, table, filters):
    query = "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    url = f"{supabase_url}/rest/v1/{table}?{query}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(url, headers=_auth_headers(supabase_key))
        return resp.status_code in (200, 204)
    except Exception as e:
        logger.warning("REST delete failed", table=table, error=str(e))
        return False


async def _rest_delete_by_id(supabase_url, supabase_key, table, row_id):
    return await _rest_delete(supabase_url, supabase_key, table, {"id": row_id})


async def _rest_update_by_id(supabase_url, supabase_key, table, row_id, data):
    return await _rest_update(supabase_url, supabase_key, table, data, {"id": row_id})


async def _get_auth_users(supabase_url, supabase_key):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{supabase_url}/auth/v1/admin/users",
                headers=_auth_headers(supabase_key),
            )
        if resp.status_code == 200:
            return resp.json().get("users", [])
    except Exception as e:
        logger.warning("Failed to fetch auth users", error=str(e))
    return []


async def _get_profile_by_id(supabase_url, supabase_key, user_id):
    return await _rest_select(
        supabase_url, supabase_key, "profiles",
        filters={"id": user_id}, single=True,
    )


def _send_invite_email(email: str, full_name: str, temp_password: str, role: str):
    role_labels = {
        "admin": "Administrador",
        "organizador": "Organizador",
        "jurado": "Jurado",
        "staff": "Staff",
        "sede": "Sede Cosquín",
    }
    role_label = role_labels.get(role, role)
    login_url = "https://precosquinpiramides.com/login"

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">

<!-- HEADER -->
<tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);padding:28px 32px;text-align:center">
  <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:0.02em">Pre-Cosquín 2027</div>
  <div style="font-size:11px;color:rgba(255,255,255,0.7);margin-top:4px">Puerto Pirámides, Chubut</div>
</td></tr>

<!-- ICON + TITLE -->
<tr><td style="padding:32px 32px 0;text-align:center">
  <div style="margin-bottom:16px">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
      <line x1="19" x2="19" y1="8" y2="14"/><line x1="22" x2="16" y1="11" y2="11"/>
    </svg>
  </div>
  <div style="font-size:18px;font-weight:700;color:#1e3a8a;margin-bottom:8px">¡Te invitamos a formar parte del equipo!</div>
  <div style="font-size:13px;color:#1e40af;line-height:1.6;max-width:420px;margin:0 auto">
    Fuiste seleccionado para integrar el equipo del <strong>Pre-Cosquín 2027</strong> como <strong>{role_label}</strong>.
  </div>
</td></tr>

<!-- CREDENTIALS CARD -->
<tr><td style="padding:24px 32px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px">
  <tr><td style="padding:20px 24px">
    <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-bottom:12px">Tus credenciales de acceso</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="padding:8px 0;width:100px;font-size:12px;color:#64748b;font-weight:600">Email</td>
      <td style="padding:8px 0;font-size:13px;color:#0f172a;font-weight:600">{email}</td>
    </tr>
    <tr>
      <td style="padding:8px 0;width:100px;font-size:12px;color:#64748b;font-weight:600">Contraseña</td>
      <td style="padding:8px 0"><code style="font-size:14px;color:#0f172a;background:#e0e7ff;padding:6px 12px;border-radius:6px;font-weight:700;letter-spacing:0.05em">{temp_password}</code></td>
    </tr>
    <tr>
      <td style="padding:8px 0;width:100px;font-size:12px;color:#64748b;font-weight:600">Rol</td>
      <td style="padding:8px 0;font-size:13px;color:#0f172a;font-weight:600">{role_label}</td>
    </tr>
    </table>
  </td></tr>
  </table>
</td></tr>

<!-- BUTTON -->
<tr><td style="padding:0 32px 24px;text-align:center">
  <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto">
  <tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);border-radius:10px">
    <a href="{login_url}" style="display:inline-block;padding:14px 36px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;letter-spacing:0.02em">Iniciar Sesión</a>
  </td></tr>
  </table>
</td></tr>

<!-- FOOTER -->
<tr><td style="padding:20px 32px;border-top:1px solid #e2e8f0;text-align:center">
  <div style="font-size:11px;color:#94a3b8;line-height:1.6">
    Este es un email automático. Si tenés consultas, respondé a este mensaje o contactanos en <span style="color:#3b82f6">contacto@precosquinpiramides.com</span>
  </div>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

    try:
        sender = get_email_sender()
        result = sender.send(EmailMessage(
            to=email,
            subject="Pre-Cosquín — Tus credenciales de acceso",
            html=html_body,
            text=f"Hola {full_name},\n\nTu cuenta fue creada exitosamente.\nEmail: {email}\nContraseña: {temp_password}\nRol: {role_label}\n\nIniciá sesión en: {login_url}",
        ))
        if result.status == "failed":
            logger.warning("invite_email_failed", email=email, error=result.error)
    except Exception as e:
        logger.warning("invite_email_error", email=email, error=str(e))


def _send_reset_email(email: str, full_name: str, temp_password: str):
    login_url = "https://precosquinpiramides.com/login"

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">

<tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);padding:28px 32px;text-align:center">
  <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:0.02em">Pre-Cosquín 2027</div>
  <div style="font-size:11px;color:rgba(255,255,255,0.7);margin-top:4px">Puerto Pirámides, Chubut</div>
</td></tr>

<tr><td style="padding:32px 32px 0;text-align:center">
  <div style="margin-bottom:16px">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  </div>
  <div style="font-size:18px;font-weight:700;color:#1e3a8a;margin-bottom:8px">Tu contraseña fue reseteada</div>
  <div style="font-size:13px;color:#1e40af;line-height:1.6;max-width:420px;margin:0 auto">
    Se generó una nueva contraseña para tu cuenta. Usala para iniciar sesión y recordá cambiarla después.
  </div>
</td></tr>

<tr><td style="padding:24px 32px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px">
  <tr><td style="padding:20px 24px">
    <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-bottom:12px">Nueva contraseña</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="padding:8px 0;width:100px;font-size:12px;color:#64748b;font-weight:600">Email</td>
      <td style="padding:8px 0;font-size:13px;color:#0f172a;font-weight:600">{email}</td>
    </tr>
    <tr>
      <td style="padding:8px 0;width:100px;font-size:12px;color:#64748b;font-weight:600">Contraseña</td>
      <td style="padding:8px 0"><code style="font-size:14px;color:#0f172a;background:#fef3c7;padding:6px 12px;border-radius:6px;font-weight:700;letter-spacing:0.05em">{temp_password}</code></td>
    </tr>
    </table>
  </td></tr>
  </table>
</td></tr>

<tr><td style="padding:0 32px 24px;text-align:center">
  <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto">
  <tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);border-radius:10px">
    <a href="{login_url}" style="display:inline-block;padding:14px 36px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;letter-spacing:0.02em">Iniciar Sesión</a>
  </td></tr>
  </table>
</td></tr>

<tr><td style="padding:20px 32px;border-top:1px solid #e2e8f0;text-align:center">
  <div style="font-size:11px;color:#94a3b8;line-height:1.6">
    Si no solicitaste este cambio, respondé a este mensaje inmediatamente.
  </div>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

    try:
        sender = get_email_sender()
        result = sender.send(EmailMessage(
            to=email,
            subject="Pre-Cosquín — Tu contraseña fue reseteada",
            html=html_body,
            text=f"Hola {full_name},\n\nTu contraseña fue reseteada.\nEmail: {email}\nNueva contraseña: {temp_password}\n\nIniciá sesión en: {login_url}",
        ))
        if result.status == "failed":
            logger.warning("reset_email_failed", email=email, error=result.error)
    except Exception as e:
        logger.warning("reset_email_error", email=email, error=str(e))


class UserInvite(BaseModel):
    email: EmailStr
    full_name: str
    role: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
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
    supabase_url, supabase_key = _get_supabase_creds()

    auth_users = await _get_auth_users(supabase_url, supabase_key)

    all_profiles = await _rest_select(supabase_url, supabase_key, "profiles")
    profiles_map = {p["id"]: p for p in (all_profiles or [])}

    result = []
    for u in auth_users:
        uid = u.get("id")
        if not uid:
            continue
        profile = profiles_map.get(uid)
        meta = u.get("user_metadata") or {}
        user_role = (profile.get("role") if profile else meta.get("role")) or "staff"
        if role and user_role != role:
            continue
        result.append({
            "id": uid,
            "email": u.get("email", ""),
            "full_name": (profile.get("full_name") if profile else None) or meta.get("full_name") or u.get("email", ""),
            "role": user_role,
            "is_active": (profile.get("is_active") if profile else None) if profile is not None else True,
            "created_at": u.get("created_at", ""),
            "has_profile": profile is not None,
        })

    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result


@router.post("/users/sync", status_code=200)
async def sync_auth_users(
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    supabase_url, supabase_key = _get_supabase_creds()

    auth_users = await _get_auth_users(supabase_url, supabase_key)

    all_profiles = await _rest_select(supabase_url, supabase_key, "profiles")
    existing_ids = {p["id"] for p in (all_profiles or [])}

    synced = []
    for u in auth_users:
        uid = u.get("id")
        if uid and uid not in existing_ids:
            meta = u.get("user_metadata") or {}
            result = await _rest_insert(supabase_url, supabase_key, "profiles", {
                "id": uid,
                "email": u.get("email", ""),
                "full_name": meta.get("full_name", u.get("email", "")),
                "role": meta.get("role", "staff"),
                "is_active": True,
            })
            if result:
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
    supabase_url, supabase_key = _get_supabase_creds()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            auth_resp = await client.post(
                f"{supabase_url}/auth/v1/admin/users",
                headers=_auth_headers(supabase_key),
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

        await _rest_insert(supabase_url, supabase_key, "profiles", {
            "id": user_id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": True,
        })

        log_audit(
            db=db,
            actor_id=current_user.id,
            action="user_invited",
            target_id=user_id,
            metadata={"email": user.email, "role": user.role},
        )

        _send_invite_email(user.email, user.full_name, temp_password, user.role)

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

    supabase_url, supabase_key = _get_supabase_creds()

    if "email" in update_data:
        new_email = update_data.pop("email")
        async with httpx.AsyncClient(timeout=15) as client:
            auth_resp = await client.put(
                f"{supabase_url}/auth/v1/admin/users/{user_id}",
                headers=_auth_headers(supabase_key),
                json={"email": new_email},
            )
        if auth_resp.status_code not in (200,):
            raise HTTPException(status_code=500, detail="Error al actualizar email en auth")
        update_data["email"] = new_email

    result = await _rest_update_by_id(supabase_url, supabase_key, "profiles", user_id, update_data)

    if not result:
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

    supabase_url, supabase_key = _get_supabase_creds()
    result = await _rest_update_by_id(supabase_url, supabase_key, "profiles", user_id, {"is_active": False})

    if not result:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="user_deactivated",
        target_id=user_id,
    )

    return {"message": "Usuario desactivado correctamente"}


@router.delete("/users/{user_id}/permanent")
async def delete_user_permanent(
    user_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")

    supabase_url, supabase_key = _get_supabase_creds()

    profile = await _get_profile_by_id(supabase_url, supabase_key, user_id)
    if not profile:
        profile_email = "unknown"
    else:
        profile_email = profile.get("email", "unknown")

    async with httpx.AsyncClient(timeout=15) as client:
        await client.delete(
            f"{supabase_url}/auth/v1/admin/users/{user_id}",
            headers=_auth_headers(supabase_key),
        )

    await _rest_delete_by_id(supabase_url, supabase_key, "profiles", user_id)

    log_audit(
        db=db,
        actor_id=current_user.id,
        action="user_deleted_permanent",
        target_id=user_id,
        metadata={"email": profile_email},
    )

    return {"message": f"Usuario {profile_email} eliminado permanentemente"}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes resetear tu propia contraseña desde aquí")

    supabase_url, supabase_key = _get_supabase_creds()

    profile = await _get_profile_by_id(supabase_url, supabase_key, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    temp_password = generate_temp_password()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            auth_resp = await client.put(
                f"{supabase_url}/auth/v1/admin/users/{user_id}",
                headers=_auth_headers(supabase_key),
                json={"password": temp_password},
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
            metadata={"email": profile.get("email", "")},
        )

        _send_reset_email(profile.get("email", ""), profile.get("full_name", ""), temp_password)

        return {
            "id": user_id,
            "email": profile.get("email", ""),
            "full_name": profile.get("full_name", ""),
            "temp_password": temp_password,
            "message": f"Contraseña reseteada para {profile.get('email', '')}",
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
    supabase_url, supabase_key = _get_supabase_creds()
    result = await _rest_select(
        supabase_url, supabase_key, "event_config",
        filters={"id": "1"}, single=True,
    )
    return result or {}


@router.patch("/event-config")
async def update_event_config(
    config: EventConfigUpdate,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    update_data = exclude_none(config)

    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")

    supabase_url, supabase_key = _get_supabase_creds()
    await _rest_insert(supabase_url, supabase_key, "event_config", {
        "id": 1,
        **update_data,
    })

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
    supabase_url, supabase_key = _get_supabase_creds()
    result = await _rest_select(supabase_url, supabase_key, "edition_capacities")
    return result


@router.patch("/capacities")
async def update_capacities(
    capacities: List[dict],
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    supabase_url, supabase_key = _get_supabase_creds()
    for cap in capacities:
        await _rest_insert(supabase_url, supabase_key, "edition_capacities", cap)

    return {"message": "Cupos actualizados correctamente"}


@router.get("/audit-logs")
async def list_audit_logs(
    action: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    supabase_url, supabase_key = _get_supabase_creds()

    async with httpx.AsyncClient(timeout=15) as client:
        url = f"{supabase_url}/rest/v1/audit_logs?select=*&order=created_at.desc&limit={limit}"
        if action:
            url += f"&action=eq.{action}"
        resp = await client.get(url, headers=_auth_headers(supabase_key))

    if resp.status_code == 200:
        return resp.json()
    return []
