-- ============================================
-- Migración: Agregar columnas faltantes a inscriptions
-- Pre-Cosquín 2026-2027 - Inscripción Typeform
-- ============================================

-- Danza
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS dance_style VARCHAR(50) DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS dance_themes JSONB DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS work_title VARCHAR(255) DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS assistants_count INTEGER DEFAULT NULL;

-- Instrumental
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS instrument_type VARCHAR(20) DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS instrument_name VARCHAR(100) DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS has_accompaniment BOOLEAN DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS accompaniment_instrument VARCHAR(100) DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS accompaniment_musician VARCHAR(200) DEFAULT NULL;

-- Conjunto de baile
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS band_members JSONB DEFAULT NULL;

-- Elegibilidad (Art. 25)
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS accept_no_prior_win BOOLEAN DEFAULT FALSE;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS accept_not_juror_org BOOLEAN DEFAULT FALSE;

-- Equipo técnico (Stage Plot y descripción)
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS equipment_backline JSONB DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS equipment_desc TEXT DEFAULT NULL;
ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS stage_plot_instruments JSONB DEFAULT NULL;

-- ============================================
-- Verificación
-- ============================================
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'inscriptions'
AND column_name IN (
  'dance_style', 'dance_themes', 'work_title', 'assistants_count',
  'instrument_type', 'instrument_name', 'has_accompaniment',
  'accompaniment_instrument', 'accompaniment_musician', 'band_members',
  'accept_no_prior_win', 'accept_not_juror_org',
  'equipment_backline', 'equipment_desc', 'stage_plot_instruments'
)
ORDER BY column_name;