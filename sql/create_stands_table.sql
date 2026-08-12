-- Create stands table for stand/solicitude management
CREATE TABLE IF NOT EXISTS stands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT DEFAULT 'PENDIENTE' NOT NULL,
  person JSONB NOT NULL,
  info JSONB NOT NULL,
  dates JSONB NOT NULL,
  equipment JSONB NOT NULL,
  electricity JSONB NOT NULL,
  gastronomy JSONB,
  commercial JSONB,
  personnel JSONB,
  logistics JSONB,
  docs JSONB,
  observations TEXT,
  stand_number TEXT,
  location_sector TEXT,
  location_size TEXT,
  admin_notes TEXT,
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_stands_status ON stands(status);
CREATE INDEX IF NOT EXISTS idx_stands_created_at ON stands(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stands_person_email ON stands USING gin((person->>'email'));

-- Enable RLS
ALTER TABLE stands ENABLE ROW LEVEL SECURITY;

-- Public can insert (stand form submission)
CREATE POLICY "Public can insert stands" ON stands
  FOR INSERT WITH CHECK (true);

-- Authenticated users (admin/org/staff) can read
CREATE POLICY "Admin can read stands" ON stands
  FOR SELECT USING (
    auth.role() = 'authenticated'
  );

-- Authenticated users can update status and location
CREATE POLICY "Admin can update stands" ON stands
  FOR UPDATE USING (
    auth.role() = 'authenticated'
  );

-- Admin only can delete
CREATE POLICY "Admin can delete stands" ON stands
  FOR DELETE USING (
    auth.role() = 'service_role' OR auth.jwt() ->> 'role' = 'admin'
  );
