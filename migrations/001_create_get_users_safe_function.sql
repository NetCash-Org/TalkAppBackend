DROP FUNCTION IF EXISTS public.get_users_safe(jsonb);
DROP FUNCTION IF EXISTS public.get_users_admin(jsonb);

CREATE FUNCTION public.get_users_safe(params jsonb DEFAULT NULL)
RETURNS TABLE (
    id uuid,
    email text,
    phone text,
    created_at timestamptz,
    last_sign_in_at timestamptz,
    confirmed_at timestamptz,
    is_anonymous boolean,
    raw_app_meta_data jsonb,
    raw_user_meta_data jsonb
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.id,
        u.email,
        u.phone,
        u.created_at,
        u.last_sign_in_at,
        u.confirmed_at,
        u.is_anonymous,
        u.raw_app_meta_data,
        u.raw_user_meta_data
    FROM auth.users u
    WHERE u.deleted_at IS NULL;  -- Exclude soft-deleted users
END;
$$;

-- Grant execute permission to authenticated users
GRANT EXECUTE ON FUNCTION public.get_users_safe(jsonb) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_users_safe(jsonb) TO service_role;

CREATE FUNCTION public.get_users_admin(params jsonb DEFAULT NULL)
RETURNS TABLE (
    instance_id uuid,
    id uuid,
    aud text,
    role text,
    email text,
    email_confirmed_at timestamptz,
    invited_at timestamptz,
    confirmation_token text,
    confirmation_sent_at timestamptz,
    recovery_token text,
    recovery_sent_at timestamptz,
    email_change_token_new text,
    email_change text,
    email_change_sent_at timestamptz,
    last_sign_in_at timestamptz,
    raw_app_meta_data jsonb,
    raw_user_meta_data jsonb,
    is_super_admin boolean,
    created_at timestamptz,
    updated_at timestamptz,
    phone text,
    phone_confirmed_at timestamptz,
    phone_change text,
    phone_change_token text,
    phone_change_sent_at timestamptz,
    confirmed_at timestamptz,
    email_change_token_current text,
    email_change_confirm_status integer,
    banned_until timestamptz,
    reauthentication_token text,
    reauthentication_sent_at timestamptz,
    is_sso_user boolean,
    deleted_at timestamptz,
    is_anonymous boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.instance_id,
        u.id,
        u.aud,
        u.role,
        u.email,
        u.email_confirmed_at,
        u.invited_at,
        u.confirmation_token,
        u.confirmation_sent_at,
        u.recovery_token,
        u.recovery_sent_at,
        u.email_change_token_new,
        u.email_change,
        u.email_change_sent_at,
        u.last_sign_in_at,
        u.raw_app_meta_data,
        u.raw_user_meta_data,
        u.is_super_admin,
        u.created_at,
        u.updated_at,
        u.phone,
        u.phone_confirmed_at,
        u.phone_change,
        u.phone_change_token,
        u.phone_change_sent_at,
        u.confirmed_at,
        u.email_change_token_current,
        u.email_change_confirm_status,
        u.banned_until,
        u.reauthentication_token,
        u.reauthentication_sent_at,
        u.is_sso_user,
        u.deleted_at,
        u.is_anonymous
    FROM auth.users u;
END;
$$;

-- Grant execute permission to service role only (admin access)
GRANT EXECUTE ON FUNCTION public.get_users_admin(jsonb) TO service_role;