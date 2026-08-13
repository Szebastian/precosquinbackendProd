"""
Upstash Redis REST API client for chatbot caching.
Uses HTTP requests instead of TCP connections.
"""
import json
import httpx
from typing import Any, Optional
import structlog

from app.core.config import settings

logger = structlog.get_logger()


class UpstashRedis:
    """Minimal Upstash Redis REST API client."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=5.0,
        )

    async def _exec(self, *args: Any) -> Any:
        """Execute a Redis command via Upstash REST API."""
        command = args[0].upper()
        path_parts = [command] + [str(a) for a in args[1:]]
        path = "/".join(path_parts)
        try:
            resp = await self.client.post(f"{self.url}/{path}")
            resp.raise_for_status()
            data = resp.json()
            return data.get("result")
        except Exception as e:
            logger.warning("upstash_exec_error", error=str(e), command=command)
            return None

    async def get(self, key: str) -> Optional[str]:
        return await self._exec("GET", key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        if ex:
            result = await self._exec("SET", key, value, "EX", str(ex))
        else:
            result = await self._exec("SET", key, value)
        return result == "OK"

    async def setex(self, key: str, ex: int, value: str) -> bool:
        result = await self._exec("SETEX", key, str(ex), value)
        return result == "OK"

    async def incr(self, key: str) -> Optional[int]:
        result = await self._exec("INCR", key)
        return int(result) if result else None

    async def expire(self, key: str, ex: int) -> bool:
        result = await self._exec("EXPIRE", key, str(ex))
        return result == 1

    async def delete(self, *keys: str) -> Optional[int]:
        result = await self._exec("DEL", *keys)
        return int(result) if result else None

    async def exists(self, key: str) -> bool:
        result = await self._exec("EXISTS", key)
        return result == 1

    async def close(self):
        await self.client.aclose()


# Global singleton
_upstash_client: Optional[UpstashRedis] = None


def get_upstash() -> Optional[UpstashRedis]:
    """Get the Upstash Redis client. Returns None if not configured."""
    global _upstash_client
    if _upstash_client is None:
        if settings.UPSTASH_REDIS_REST_URL and settings.UPSTASH_REDIS_REST_TOKEN:
            _upstash_client = UpstashRedis(
                url=settings.UPSTASH_REDIS_REST_URL,
                token=settings.UPSTASH_REDIS_REST_TOKEN,
            )
        else:
            return None
    return _upstash_client
