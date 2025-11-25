-- Verification script for get_users_safe and get_users_admin functions
-- Run this after executing 001_create_get_users_safe_function.sql

-- 1. Check if functions exist in the database
SELECT
    routine_name,
    routine_schema,
    data_type as return_type
FROM information_schema.routines
WHERE routine_name IN ('get_users_safe', 'get_users_admin')
AND routine_schema = 'public'
ORDER BY routine_name;

-- 2. Check function parameters
SELECT
    routine_name,
    parameter_name,
    data_type,
    parameter_default
FROM information_schema.parameters
WHERE specific_name IN (
    SELECT specific_name FROM information_schema.routines
    WHERE routine_name IN ('get_users_safe', 'get_users_admin')
    AND routine_schema = 'public'
)
ORDER BY routine_name, ordinal_position;

-- 3. Check permissions granted on the functions
SELECT
    grantee,
    privilege_type,
    routine_name
FROM information_schema.role_routine_grants
WHERE routine_name IN ('get_users_safe', 'get_users_admin')
AND routine_schema = 'public'
ORDER BY routine_name, grantee;

-- 4. Test get_users_safe function (should return data if users exist)
-- Call with explicit NULL parameter to avoid ambiguity
SELECT COUNT(*) as user_count FROM get_users_safe(NULL::jsonb);

-- 5. Test get_users_admin function (should return data if users exist)
-- Call with explicit NULL parameter to avoid ambiguity
SELECT COUNT(*) as admin_user_count FROM get_users_admin(NULL::jsonb);

-- 6. Clear PostgREST cache (run this after creating functions)
NOTIFY pgrst, 'reload schema';

-- 7. Optional: Get a sample of data from get_users_safe
-- SELECT id, email, created_at FROM get_users_safe(NULL::jsonb) LIMIT 5;

-- 8. Optional: Get a sample of data from get_users_admin
-- SELECT id, email, role, created_at FROM get_users_admin(NULL::jsonb) LIMIT 5;