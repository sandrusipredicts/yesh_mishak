-- Push delivery attempts: tracks FCM push delivery with retry/backoff support.
-- Each row represents a delivery attempt for one notification to one device token.

CREATE TABLE IF NOT EXISTS public.push_delivery_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_id uuid NOT NULL
        REFERENCES public.notifications(id) ON DELETE CASCADE,
    push_token_id uuid
        REFERENCES public.push_tokens(id) ON DELETE SET NULL,
    token_hash text NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    push_data jsonb,
    status text NOT NULL DEFAULT 'processing'
        CHECK (status IN (
            'processing', 'delivered',
            'failed_retryable', 'failed_permanent', 'abandoned'
        )),
    attempt_count integer NOT NULL DEFAULT 1
        CHECK (attempt_count >= 0 AND attempt_count <= 20),
    max_attempts integer NOT NULL DEFAULT 5
        CHECK (max_attempts >= 1 AND max_attempts <= 20),
    lease_id uuid NOT NULL DEFAULT gen_random_uuid(),
    lease_expires_at timestamptz NOT NULL
        DEFAULT now() + interval '300 seconds',
    last_error_type text
        CHECK (last_error_type IS NULL OR length(last_error_type) <= 120),
    last_error_message text
        CHECK (last_error_message IS NULL OR length(last_error_message) <= 500),
    last_http_status integer,
    next_retry_at timestamptz,
    processing_started_at timestamptz NOT NULL DEFAULT now(),
    last_attempted_at timestamptz,
    delivered_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (status = 'delivered' AND delivered_at IS NOT NULL)
        OR (status != 'delivered')
    )
);

-- Idempotency: one delivery attempt per notification per active token
CREATE UNIQUE INDEX IF NOT EXISTS idx_pda_notification_token_unique
    ON public.push_delivery_attempts(notification_id, push_token_id)
    WHERE push_token_id IS NOT NULL;

-- Retry worker: find eligible rows
CREATE INDEX IF NOT EXISTS idx_pda_retry_eligible
    ON public.push_delivery_attempts(next_retry_at NULLS FIRST, created_at)
    WHERE status = 'failed_retryable';

-- Lease recovery: find stale processing rows
CREATE INDEX IF NOT EXISTS idx_pda_processing_lease
    ON public.push_delivery_attempts(lease_expires_at)
    WHERE status = 'processing';

-- Staleness: find old rows to abandon
CREATE INDEX IF NOT EXISTS idx_pda_staleness
    ON public.push_delivery_attempts(created_at)
    WHERE status = 'failed_retryable';

-- Sibling invalidation: find retryable rows by token
CREATE INDEX IF NOT EXISTS idx_pda_token_retryable
    ON public.push_delivery_attempts(push_token_id, status)
    WHERE push_token_id IS NOT NULL AND status = 'failed_retryable';

-- Observability
CREATE INDEX IF NOT EXISTS idx_pda_notification_id
    ON public.push_delivery_attempts(notification_id);

-- RLS + Grants
ALTER TABLE public.push_delivery_attempts ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE ON public.push_delivery_attempts TO service_role;


-- RPC: Atomically insert and claim an initial push delivery attempt.
-- Returns the inserted row if this caller owns the claim, or empty if a row already exists.
CREATE OR REPLACE FUNCTION public.claim_initial_push_delivery(
    p_notification_id uuid,
    p_push_token_id uuid,
    p_token_hash text,
    p_title text,
    p_body text,
    p_push_data jsonb DEFAULT NULL,
    p_max_attempts integer DEFAULT 5,
    p_lease_duration_seconds integer DEFAULT 300
)
RETURNS SETOF public.push_delivery_attempts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_lease integer;
BEGIN
    v_lease := LEAST(GREATEST(p_lease_duration_seconds, 60), 3600);

    RETURN QUERY
    INSERT INTO public.push_delivery_attempts (
        notification_id, push_token_id, token_hash,
        title, body, push_data,
        status, attempt_count, max_attempts,
        lease_id, lease_expires_at, processing_started_at
    ) VALUES (
        p_notification_id, p_push_token_id, p_token_hash,
        p_title, p_body, p_push_data,
        'processing', 1, LEAST(GREATEST(p_max_attempts, 1), 20),
        gen_random_uuid(),
        now() + make_interval(secs => v_lease),
        now()
    )
    ON CONFLICT (notification_id, push_token_id)
        WHERE push_token_id IS NOT NULL
    DO NOTHING
    RETURNING *;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.claim_initial_push_delivery(uuid, uuid, text, text, text, jsonb, integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_initial_push_delivery(uuid, uuid, text, text, text, jsonb, integer, integer) TO service_role;


-- RPC: Claim a batch of retryable push delivery attempts for processing.
CREATE OR REPLACE FUNCTION public.claim_push_delivery_retries(
    p_batch_size integer DEFAULT 50,
    p_staleness_cutoff_seconds integer DEFAULT 7200,
    p_lease_duration_seconds integer DEFAULT 300
)
RETURNS SETOF public.push_delivery_attempts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_batch_size integer;
    v_staleness integer;
    v_lease integer;
BEGIN
    v_batch_size := LEAST(GREATEST(p_batch_size, 1), 200);
    v_staleness := LEAST(GREATEST(p_staleness_cutoff_seconds, 300), 86400);
    v_lease := LEAST(GREATEST(p_lease_duration_seconds, 60), 3600);

    -- Step 1: Abandon stale rows (created too long ago)
    UPDATE public.push_delivery_attempts
    SET status = 'abandoned',
        last_error_type = COALESCE(last_error_type, 'STALENESS_CUTOFF'),
        updated_at = now()
    WHERE status = 'failed_retryable'
      AND created_at < now() - make_interval(secs => v_staleness);

    -- Step 2: Abandon exhausted rows (attempt_count >= max_attempts still in failed_retryable)
    UPDATE public.push_delivery_attempts
    SET status = 'abandoned',
        last_error_type = COALESCE(last_error_type, 'MAX_ATTEMPTS_EXHAUSTED'),
        updated_at = now()
    WHERE status = 'failed_retryable'
      AND attempt_count >= max_attempts;

    -- Step 3: Recover expired processing leases
    UPDATE public.push_delivery_attempts
    SET status = CASE
            WHEN attempt_count >= max_attempts THEN 'abandoned'
            ELSE 'failed_retryable'
        END,
        last_error_type = COALESCE(last_error_type, 'LEASE_EXPIRED'),
        updated_at = now()
    WHERE status = 'processing'
      AND lease_expires_at <= now();

    -- Step 4: Mark orphaned rows (token deleted) as permanent failure
    UPDATE public.push_delivery_attempts
    SET status = 'failed_permanent',
        last_error_type = 'TOKEN_DELETED',
        updated_at = now()
    WHERE status = 'failed_retryable'
      AND push_token_id IS NULL;

    -- Step 5: Atomically claim eligible rows with new lease
    RETURN QUERY
    UPDATE public.push_delivery_attempts
    SET status = 'processing',
        attempt_count = attempt_count + 1,
        processing_started_at = now(),
        lease_id = gen_random_uuid(),
        lease_expires_at = now() + make_interval(secs => v_lease),
        updated_at = now()
    WHERE id IN (
        SELECT id
        FROM public.push_delivery_attempts
        WHERE status = 'failed_retryable'
          AND (next_retry_at IS NULL OR next_retry_at <= now())
          AND push_token_id IS NOT NULL
          AND attempt_count < max_attempts
        ORDER BY next_retry_at NULLS FIRST, created_at
        LIMIT v_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.claim_push_delivery_retries(integer, integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_push_delivery_retries(integer, integer, integer) TO service_role;
