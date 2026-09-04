"""Verify faqs table exists in Supabase."""
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env", override=True)

from supabase import create_client
from app.core.config import settings

client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

# Try to query the faqs table
try:
    result = client.table("faqs").select("id").limit(1).execute()
    print(f"✅ Table 'faqs' exists. Rows: {len(result.data)}")
except Exception as e:
    error_msg = str(e)
    if "Could not find the table" in error_msg or "PGRST205" in error_msg:
        print("❌ Table 'faqs' does NOT exist in Supabase.")
        print()
        print("Go to Supabase Dashboard → SQL Editor and run this SQL:")
        print("=" * 60)
        print("""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS faqs (
  id BIGSERIAL PRIMARY KEY,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'general',
  keywords TEXT[] DEFAULT '{}',
  embedding VECTOR(3072),
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS faqs_embedding_idx
  ON faqs USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 10);

CREATE INDEX IF NOT EXISTS faqs_category_idx ON faqs (category);

CREATE TABLE IF NOT EXISTS chat_logs (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  message TEXT NOT NULL,
  reply TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('faq', 'gemini', 'cache', 'fallback')),
  tokens_used INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chat_logs_session_idx ON chat_logs (session_id);

CREATE OR REPLACE FUNCTION search_faqs(
  query_embedding VECTOR(3072),
  match_threshold FLOAT DEFAULT 0.75,
  match_count INT DEFAULT 3
)
RETURNS TABLE (
  id BIGINT,
  question TEXT,
  answer TEXT,
  category TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    faqs.id,
    faqs.question,
    faqs.answer,
    faqs.category,
    1 - (faqs.embedding <=> query_embedding) AS similarity
  FROM faqs
  WHERE faqs.is_active = true
    AND 1 - (faqs.embedding <=> query_embedding) > match_threshold
  ORDER BY faqs.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
""")
        print("=" * 60)
    else:
        print(f"❌ Unexpected error: {e}")

# Also check stands table exists
try:
    result = client.table("stands").select("id").limit(1).execute()
    print(f"✅ Table 'stands' exists.")
except:
    print("⚠️  Table 'stands' does not exist.")
