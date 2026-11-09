BEGIN;

CREATE TABLE IF NOT EXISTS home_registry (
    home_id TEXT PRIMARY KEY,
    version BIGINT NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS room_registry (
    home_id TEXT NOT NULL REFERENCES home_registry(home_id) ON DELETE CASCADE,
    room_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (home_id, room_id)
);

CREATE TABLE IF NOT EXISTS device_registry (
    home_id TEXT NOT NULL REFERENCES home_registry(home_id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    room_id TEXT,
    name TEXT NOT NULL,
    online BOOLEAN NOT NULL DEFAULT FALSE,
    version BIGINT NOT NULL DEFAULT 1,
    state_version TEXT,
    state_observed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (home_id, device_id),
    FOREIGN KEY (home_id, room_id) REFERENCES room_registry(home_id, room_id)
);

CREATE TABLE IF NOT EXISTS capability_registry (
    home_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    capability TEXT NOT NULL,
    schema JSONB NOT NULL,
    idempotency_class TEXT NOT NULL,
    risk TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    PRIMARY KEY (home_id, device_id, tool_name),
    FOREIGN KEY (home_id, device_id) REFERENCES device_registry(home_id, device_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS topology_edge (
    home_id TEXT NOT NULL REFERENCES home_registry(home_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    target_id TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    version BIGINT NOT NULL DEFAULT 1,
    PRIMARY KEY (home_id, source_id, relation, target_id)
);

COMMIT;
