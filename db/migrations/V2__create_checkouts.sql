CREATE TABLE checkouts (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan            TEXT NOT NULL,
    merchant_uid    TEXT NOT NULL UNIQUE,
    amount          INT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    pg_payment_id   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at    TIMESTAMPTZ
);
CREATE INDEX idx_checkout_user ON checkouts (user_id);
