-- Create messages table for contact form
CREATE TABLE IF NOT EXISTS messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  subject TEXT NOT NULL,
  message TEXT NOT NULL,
  inscription_id UUID,
  is_read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_messages_is_read ON messages(is_read);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);

-- Enable RLS
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- Public can insert (contact form)
CREATE POLICY "Public can insert messages" ON messages
  FOR INSERT WITH CHECK (true);

-- Authenticated users with admin/org/staff roles can read
CREATE POLICY "Admin can read messages" ON messages
  FOR SELECT USING (
    auth.role() = 'authenticated'
  );

-- Authenticated users can mark as read
CREATE POLICY "Admin can update messages" ON messages
  FOR UPDATE USING (
    auth.role() = 'authenticated'
  );

-- Authenticated users can delete
CREATE POLICY "Admin can delete messages" ON messages
  FOR DELETE USING (
    auth.role() = 'authenticated'
  );
