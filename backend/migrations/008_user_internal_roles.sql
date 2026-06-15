ALTER TABLE users ADD COLUMN IF NOT EXISTS internal_roles JSONB;

UPDATE users
SET internal_roles = jsonb_build_array(internal_role)
WHERE internal_role IS NOT NULL
  AND internal_roles IS NULL;
