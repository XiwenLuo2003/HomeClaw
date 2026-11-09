BEGIN;

CREATE TABLE IF NOT EXISTS registry_outbox (
    message_id TEXT PRIMARY KEY,
    home_id TEXT NOT NULL REFERENCES home_registry(home_id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS registry_outbox_pending_idx
    ON registry_outbox(created_at) WHERE published_at IS NULL;

COMMIT;
