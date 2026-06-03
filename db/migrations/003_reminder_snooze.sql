-- Snooze/ignore table: suppress cron reminders for a vehicle+field
-- snoozed_until NULL means "ignore indefinitely"
CREATE TABLE IF NOT EXISTS reminder_snooze (
    id           SERIAL PRIMARY KEY,
    vehicle_id   INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    expiry_field VARCHAR(50) NOT NULL,
    snoozed_until DATE,          -- NULL = permanent ignore
    reason       TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   TEXT,           -- user_id (platform:id)
    UNIQUE (vehicle_id, expiry_field)
);

CREATE INDEX IF NOT EXISTS reminder_snooze_vehicle_field
    ON reminder_snooze (vehicle_id, expiry_field);
