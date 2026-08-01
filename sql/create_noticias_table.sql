-- Create noticias table for hero carousel / news feed
CREATE TABLE IF NOT EXISTS noticias (
  id SERIAL PRIMARY KEY,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  image TEXT NOT NULL DEFAULT '',
  image_position TEXT DEFAULT 'center center',
  thumb_type TEXT NOT NULL DEFAULT 'img' CHECK (thumb_type IN ('img', 'icon')),
  thumb_src TEXT NOT NULL DEFAULT '',
  thumb_bg TEXT NOT NULL DEFAULT 'bg-blue',
  sort_order INTEGER DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_noticias_is_active ON noticias(is_active);
CREATE INDEX IF NOT EXISTS idx_noticias_sort_order ON noticias(sort_order);
CREATE INDEX IF NOT EXISTS idx_noticias_created_at ON noticias(created_at DESC);

-- Enable RLS
ALTER TABLE noticias ENABLE ROW LEVEL SECURITY;

-- Public can read active news (hero carousel, public pages)
CREATE POLICY "Public can read active noticias" ON noticias
  FOR SELECT USING (is_active = TRUE);

-- Authenticated users with organizer/admin roles can do everything
CREATE POLICY "Organizador can manage noticias" ON noticias
  FOR ALL USING (
    auth.role() = 'authenticated'
  );

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_noticias_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_noticias_updated_at
  BEFORE UPDATE ON noticias
  FOR EACH ROW
  EXECUTE FUNCTION update_noticias_updated_at();
