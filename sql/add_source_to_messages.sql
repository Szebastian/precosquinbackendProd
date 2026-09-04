-- Add source column to messages table to distinguish between web form and email
-- Run this in Supabase SQL Editor

ALTER TABLE messages ADD COLUMN IF NOT EXISTS source text DEFAULT 'web';
