-- Tabla email_jobs para almacenar emails programados
CREATE TABLE IF NOT EXISTS email_jobs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  sender_id UUID REFERENCES auth.users(id),
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  template TEXT,
  recipients JSONB DEFAULT '[]'::jsonb,
  scheduled_at TIMESTAMPTZ,
  status TEXT DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED', 'SENDING', 'COMPLETED', 'FAILED')),
  total INT DEFAULT 0,
  sent INT DEFAULT 0,
  failed INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices útiles
CREATE INDEX IF NOT EXISTS idx_email_jobs_status ON email_jobs(status);
CREATE INDEX IF NOT EXISTS idx_email_jobs_scheduled_at ON email_jobs(scheduled_at);

-- Columna recipient_email en communications_log (si no existe)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'communications_log' AND column_name = 'recipient_email'
  ) THEN
    ALTER TABLE communications_log ADD COLUMN recipient_email TEXT;
  END IF;
END $$;
