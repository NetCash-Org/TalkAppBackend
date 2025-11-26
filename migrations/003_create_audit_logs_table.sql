-- Create audit_logs table for tracking user actions
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL CHECK (action IN ('login', 'logout', 'create', 'update', 'delete', 'file_upload')),
    route TEXT NOT NULL,
    http_method VARCHAR(10) NOT NULL,
    status INTEGER,
    ip_address INET,
    device_info JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index for efficient querying
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON public.audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON public.audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON public.audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_route ON public.audit_logs(route);

-- Enable RLS (Row Level Security)
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Service role can insert audit logs" ON public.audit_logs;
DROP POLICY IF EXISTS "Admins can read audit logs" ON public.audit_logs;

-- Policy: Only service role can insert logs
CREATE POLICY "Service role can insert audit logs" ON public.audit_logs
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

-- Policy: Only admins can read audit logs
CREATE POLICY "Admins can read audit logs" ON public.audit_logs
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM auth.users
            WHERE id = auth.uid()
            AND raw_app_meta_data->>'role' = 'admin'
        )
    );

-- Grant permissions
GRANT USAGE ON SCHEMA public TO service_role;
GRANT INSERT ON public.audit_logs TO service_role;
GRANT SELECT ON public.audit_logs TO authenticated;

-- Create function to safely insert audit logs
CREATE OR REPLACE FUNCTION public.insert_audit_log(
    p_action VARCHAR(50),
    p_route TEXT,
    p_http_method VARCHAR(10),
    p_user_id UUID DEFAULT NULL,
    p_status INTEGER DEFAULT NULL,
    p_ip_address INET DEFAULT NULL,
    p_device_info JSONB DEFAULT NULL,
    p_error_message TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    log_id UUID;
BEGIN
    -- Validate action
    IF p_action NOT IN ('login', 'logout', 'create', 'update', 'delete', 'file_upload') THEN
        RAISE EXCEPTION 'Invalid action: %', p_action;
    END IF;

    -- Insert log
    INSERT INTO public.audit_logs (
        user_id, action, route, http_method, status, ip_address, device_info, error_message
    ) VALUES (
        p_user_id, p_action, p_route, p_http_method, p_status, p_ip_address, p_device_info, p_error_message
    )
    RETURNING id INTO log_id;

    RETURN log_id;
END;
$$;

-- Grant execute permission to service role
GRANT EXECUTE ON FUNCTION public.insert_audit_log(VARCHAR, TEXT, VARCHAR, UUID, INTEGER, INET, JSONB, TEXT) TO service_role;

-- Create function to safely query audit logs (admin only)
CREATE OR REPLACE FUNCTION public.get_audit_logs_admin(
    p_user_id UUID DEFAULT NULL,
    p_action VARCHAR(50) DEFAULT NULL,
    p_start_date TIMESTAMPTZ DEFAULT NULL,
    p_end_date TIMESTAMPTZ DEFAULT NULL,
    p_limit INTEGER DEFAULT 100,
    p_offset INTEGER DEFAULT 0
)
RETURNS TABLE (
    id UUID,
    "timestamp" TIMESTAMPTZ,
    user_id UUID,
    action VARCHAR(50),
    route TEXT,
    http_method VARCHAR(10),
    status INTEGER,
    ip_address INET,
    device_info JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        al.id,
        al."timestamp",
        al.user_id,
        al.action,
        al.route,
        al.http_method,
        al.status,
        al.ip_address,
        al.device_info,
        al.error_message,
        al.created_at
    FROM public.audit_logs al
    WHERE (p_user_id IS NULL OR al.user_id = p_user_id)
      AND (p_action IS NULL OR al.action = p_action)
      AND (p_start_date IS NULL OR al."timestamp" >= p_start_date)
      AND (p_end_date IS NULL OR al."timestamp" <= p_end_date)
    ORDER BY al."timestamp" DESC
    LIMIT p_limit
    OFFSET p_offset;
END;
$$;

-- Create function to get audit logs count
CREATE OR REPLACE FUNCTION public.get_audit_logs_count_admin(
    p_user_id UUID DEFAULT NULL,
    p_action VARCHAR(50) DEFAULT NULL,
    p_start_date TIMESTAMPTZ DEFAULT NULL,
    p_end_date TIMESTAMPTZ DEFAULT NULL
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    log_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO log_count
    FROM public.audit_logs al
    WHERE (p_user_id IS NULL OR al.user_id = p_user_id)
      AND (p_action IS NULL OR al.action = p_action)
      AND (p_start_date IS NULL OR al."timestamp" >= p_start_date)
      AND (p_end_date IS NULL OR al."timestamp" <= p_end_date);

    RETURN log_count;
END;
$$;

-- Grant execute permission to service role
GRANT EXECUTE ON FUNCTION public.get_audit_logs_admin(UUID, VARCHAR, TIMESTAMPTZ, TIMESTAMPTZ, INTEGER, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_audit_logs_count_admin(UUID, VARCHAR, TIMESTAMPTZ, TIMESTAMPTZ) TO service_role;

-- Clear PostgREST cache
NOTIFY pgrst, 'reload schema';