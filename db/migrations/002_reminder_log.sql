CREATE TABLE IF NOT EXISTS reminder_log (
    id             BIGSERIAL PRIMARY KEY,
    vehicle_id     BIGINT NOT NULL REFERENCES vehicles(id),
    expiry_field   TEXT NOT NULL,
    expiry_date    DATE NOT NULL,
    trigger_offset INT NOT NULL,
    sent_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (vehicle_id, expiry_field, expiry_date, trigger_offset)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         BIGSERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created
    ON chat_messages (user_id, created_at);

CREATE TABLE IF NOT EXISTS chat_summary (
    user_id    TEXT PRIMARY KEY,
    summary    TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
