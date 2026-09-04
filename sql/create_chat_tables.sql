-- ============================================================
-- Chatbot tables for Pre-Cosquín Puerto Pirámides
-- Execute this in Supabase SQL Editor
-- ============================================================

-- 1. Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. FAQs table with embeddings for semantic search
-- Uses 3072 dimensions (gemini-embedding-001 model)
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

-- 3. Index for category filtering
CREATE INDEX IF NOT EXISTS faqs_category_idx ON faqs (category);

-- 4. Chat logs table (for analytics)
CREATE TABLE IF NOT EXISTS chat_logs (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  message TEXT NOT NULL,
  reply TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('faq', 'gemini', 'cache', 'fallback')),
  tokens_used INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Index for session queries
CREATE INDEX IF NOT EXISTS chat_logs_session_idx ON chat_logs (session_id);

-- 6. RPC function for FAQ semantic search
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
