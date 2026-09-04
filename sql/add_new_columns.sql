-- ============================================
-- Migración: Agregar columnas nuevas para typeform completo
-- Pre-Cosquín 2026-2027 - Typeform Flow
-- Ejecutar en Supabase SQL Editor
-- ============================================

-- Datos personales
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS first_name VARCHAR(100) DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS last_name VARCHAR(100) DEFAULT NULL;

-- Reglamento
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS accept_regulations BOOLEAN DEFAULT FALSE;

-- Solista instrumental
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS accept_purely_instrumental BOOLEAN DEFAULT FALSE;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS accept_one_instrument BOOLEAN DEFAULT FALSE;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS accept_no_prerecorded BOOLEAN DEFAULT FALSE;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS accept_no_instrument_change BOOLEAN DEFAULT FALSE;

-- Propuesta artística
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS presentation TEXT DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS artistic_name VARCHAR(200) DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS songs_list TEXT DEFAULT NULL;

-- ============================================
-- Verificación
-- ============================================
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'inscriptions'
AND column_name IN (
  'first_name', 'last_name', 'accept_regulations',
  'accept_purely_instrumental', 'accept_one_instrument',
  'accept_no_prerecorded', 'accept_no_instrument_change',
  'presentation', 'artistic_name', 'songs_list'
)
ORDER BY column_name;
