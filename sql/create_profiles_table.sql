-- =====================================================
-- Tabla profiles: perfiles de usuario del panel admin
-- =====================================================
-- Cada usuario autenticado en Supabase Auth tiene un
-- perfil en esta tabla con su rol y estado.
-- =====================================================

CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT DEFAULT '',
    role TEXT DEFAULT 'staff',
    is_active BOOLEAN DEFAULT TRUE,
    organization_id UUID,
    permissions JSONB DEFAULT '[]'::jsonb,
    avatar_url TEXT,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- RLS: los usuarios solo ven su propio perfil, los admin ven todos
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Policy: cada usuario puede leer su propio perfil
CREATE POLICY "Users can read own profile"
    ON profiles FOR SELECT
    USING (auth.uid() = id);

-- Policy: los admin pueden leer todos los perfiles
CREATE POLICY "Admins can read all profiles"
    ON profiles FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- Policy: los admin pueden insertar perfiles
CREATE POLICY "Admins can insert profiles"
    ON profiles FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- Policy: los admin pueden actualizar perfiles
CREATE POLICY "Admins can update profiles"
    ON profiles FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- Policy: los admin pueden eliminar perfiles
CREATE POLICY "Admins can delete profiles"
    ON profiles FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- Index para búsquedas por email
CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles (email);

-- Index para búsquedas por role
CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles (role);

-- Trigger para actualizar updated_at
CREATE OR REPLACE FUNCTION update_profiles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_profiles_updated_at ON profiles;
CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_profiles_updated_at();
