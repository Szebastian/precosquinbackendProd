import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path, override=True)

from supabase import create_client, Client

_supabase_client: Client | None = None


async def init_db() -> None:
    global _supabase_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key or url.startswith("eyJ"):
        print(f"WARNING: Invalid Supabase config. URL={url[:30]}... Key={key[:10]}...")
        _supabase_client = None
        return

    try:
        _supabase_client = create_client(url, key)
        print(f"OK: Supabase client initialized for {url}")
    except Exception as e:
        print(f"WARNING: Could not connect to Supabase: {e}")
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
