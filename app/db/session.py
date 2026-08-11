import os
from pathlib import Path
from dotenv import load_dotenv
import structlog

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path, override=True)

from supabase import create_client, Client

_supabase_client: Client | None = None
logger = structlog.get_logger(__name__)


async def init_db() -> None:
    global _supabase_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key or url.startswith("eyJ"):
        logger.warning("Invalid Supabase config", url_prefix=url[:30], key_prefix=key[:10])
        _supabase_client = None
        return

    try:
        _supabase_client = create_client(url, key)
        logger.info("Supabase client initialized", url=url)
    except Exception as e:
        logger.warning("Could not connect to Supabase", error=str(e))
        _supabase_client = None


async def close_db() -> None:
    global _supabase_client
    _supabase_client = None


def get_supabase() -> Client:
    if _supabase_client is None:
        raise RuntimeError("Supabase client not initialized. Call init_db() first.")
    return _supabase_client


async def get_db():
    db = get_supabase()
    try:
        yield db
    finally:
        pass
