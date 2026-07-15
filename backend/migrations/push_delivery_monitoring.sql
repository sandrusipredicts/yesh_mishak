-- E05-04: Database-side push-delivery aggregation for admin monitoring.
-- Safe to re-run. Apply after backend/migrations/push_delivery_attempts.sql.

-- Index for windowed aggregation on terminal rows by created_at.
CREATE INDEX IF NOT EXISTS idx_pda_created_at
    ON public.push_delivery_attempts(created_at);

-- RPC: aggregate push-delivery outcomes for a time window.
CREATE OR REPLACE FUNCTION public.get_push_delivery_metrics(
    window_start timestamptz,
    window_end timestamptz
)
RETURNS TABLE (
    attempted_count bigint,
    accepted_count bigint,
    failed_count bigint,
    invalid_token_count bigint
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT
        count(*) FILTER (
            WHERE status IN ('delivered', 'failed_permanent', 'abandoned')
        )::bigint AS attempted_count,
        count(*) FILTER (
            WHERE status = 'delivered'
        )::bigint AS accepted_count,
        count(*) FILTER (
            WHERE (status = 'failed_permanent' AND (last_error_type IS NULL OR last_error_type NOT IN ('INVALID_TOKEN', 'TOKEN_INVALIDATED')))
               OR status = 'abandoned'
        )::bigint AS failed_count,
        count(*) FILTER (
            WHERE status = 'failed_permanent' AND last_error_type IN ('INVALID_TOKEN', 'TOKEN_INVALIDATED')
        )::bigint AS invalid_token_count
    FROM public.push_delivery_attempts
    WHERE created_at >= window_start
      AND created_at < window_end;
$$;

GRANT EXECUTE ON FUNCTION public.get_push_delivery_metrics(timestamptz, timestamptz) TO service_role;
