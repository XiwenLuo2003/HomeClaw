BEGIN;

CREATE TABLE IF NOT EXISTS workflow_task (
    task_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    status TEXT NOT NULL,
    current_node TEXT NOT NULL,
    revision BIGINT NOT NULL DEFAULT 0,
    deadline_at TIMESTAMPTZ,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_checkpoint (
    task_id TEXT NOT NULL REFERENCES workflow_task(task_id) ON DELETE CASCADE,
    revision BIGINT NOT NULL,
    node TEXT NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (task_id, revision)
);

CREATE TABLE IF NOT EXISTS action_attempt (
    command_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES workflow_task(task_id) ON DELETE CASCADE,
    action_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    request JSONB NOT NULL,
    evidence JSONB,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_outbox (
    message_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES workflow_task(task_id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS workflow_outbox_pending_idx
    ON workflow_outbox(created_at) WHERE published_at IS NULL;

COMMIT;
