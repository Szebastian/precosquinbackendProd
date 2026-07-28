import os
import httpx
from typing import Any, Optional


def _get_config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return url, key


def supabase_insert(table: str, data: dict) -> list[dict]:
    url, key = _get_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    r = httpx.post(f"{url}/rest/v1/{table}", headers=headers, json=data, timeout=30)
    if r.status_code >= 400:
        raise Exception(f"Supabase insert error ({r.status_code}): {r.text}")
    return r.json()


def supabase_select(table: str, columns: str = "*", filters: Optional[dict] = None,
                     order: Optional[str] = None, limit: Optional[int] = None) -> list[dict]:
    url, key = _get_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    params: dict[str, Any] = {"select": columns}
    if filters:
        for k, v in filters.items():
            params[k] = v
    if order:
        params["order"] = order
    if limit:
        params["limit"] = str(limit)
    r = httpx.get(f"{url}/rest/v1/{table}", headers=headers, params=params, timeout=30)
    if r.status_code >= 400:
        raise Exception(f"Supabase select error ({r.status_code}): {r.text}")
    return r.json()


def supabase_update(table: str, data: dict, filters: dict) -> list[dict]:
    url, key = _get_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    params = {}
    for k, v in filters.items():
        params[k] = v
    r = httpx.patch(f"{url}/rest/v1/{table}", headers=headers, json=data, params=params, timeout=30)
    if r.status_code >= 400:
        raise Exception(f"Supabase update error ({r.status_code}): {r.text}")
    return r.json()


def supabase_delete(table: str, filters: dict) -> None:
    url, key = _get_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    params = {}
    for k, v in filters.items():
        params[k] = v
    r = httpx.delete(f"{url}/rest/v1/{table}", headers=headers, params=params, timeout=30)
    if r.status_code >= 400:
        raise Exception(f"Supabase delete error ({r.status_code}): {r.text}")
