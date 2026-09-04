import secrets
import string
from typing import Any, Dict, Optional
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)


def generate_temp_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(length))


def exclude_none(model: BaseModel) -> Dict[str, Any]:
    """Returns a dictionary with non-None fields from a Pydantic model."""
    return {k: v for k, v in model.model_dump().items() if v is not None}


def log_audit(
    db: Any,
    actor_id: str,
    action: str,
    target_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Helper to record audit log entries in Supabase."""
    try:
        payload: Dict[str, Any] = {
            "actor_id": actor_id,
            "action": action,
        }
        if target_id:
            payload["target_id"] = target_id
        if metadata:
            payload["metadata"] = metadata

        db.table("audit_logs").insert(payload).execute()
    except Exception as e:
        logger.warning("Audit log recording failed", action=action, actor_id=actor_id, error=str(e))
