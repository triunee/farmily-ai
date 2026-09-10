-- Farmily 초기 스키마. DB_SCHEMA.md §1~17 기반.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- =========================
-- 1. users
-- =========================
CREATE TABLE users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kakao_id      TEXT UNIQUE NOT NULL,
    name          TEXT,
    phone_enc     BYTEA,
    email         CITEXT,
    handle        CITEXT,
    plan          TEXT NOT NULL DEFAULT 'FREE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ,
    onboarded_at  TIMESTAMPTZ
);
CREATE INDEX idx_users_kakao_id ON users (kakao_id);
CREATE UNIQUE INDEX uq_users_handle_alive ON users (handle) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_email ON users (email);

-- =========================
-- 2. farm_profiles
-- =========================
CREATE TABLE farm_profiles (
    user_id              BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    farm_name            TEXT,
    region               TEXT,
    farming_method       TEXT,
    background_image_key TEXT,
    avatar_image_key     TEXT,
    story_text           TEXT,
    story_image_keys     TEXT[],
    story_video_key      TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================
-- 3. profile_blocks
-- =========================
CREATE TABLE profile_blocks (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    block_type  TEXT NOT NULL,
    sort_order  INT NOT NULL,
    visible     BOOLEAN NOT NULL DEFAULT TRUE,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, sort_order) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX idx_profile_blocks_user ON profile_blocks (user_id);

-- =========================
-- 4. sales_channels
-- =========================
CREATE TABLE sales_channels (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel     TEXT NOT NULL,
    url         TEXT NOT NULL,
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, channel)
);

-- =========================
-- 5. crops
-- =========================
CREATE TABLE crops (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    color_hex   TEXT NOT NULL DEFAULT '#2BA651',
    stage       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_crops_user_name_alive ON crops (user_id, name) WHERE deleted_at IS NULL;
CREATE INDEX idx_crops_user ON crops (user_id);

-- =========================
-- 6. farm_locations
-- =========================
CREATE TABLE farm_locations (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label       TEXT NOT NULL,
    address     TEXT NOT NULL,
    lat         NUMERIC(9,6),
    lng         NUMERIC(9,6),
    kma_grid_x  INT,
    kma_grid_y  INT,
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_farm_locations_user ON farm_locations (user_id);

-- =========================
-- 7. farm_diaries
-- =========================
CREATE TABLE farm_diaries (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    farm_location_id  BIGINT REFERENCES farm_locations(id) ON DELETE SET NULL,
    diary_date        DATE NOT NULL,
    crop_id           BIGINT NOT NULL REFERENCES crops(id),
    weather_main      TEXT,
    temp_max          NUMERIC(4,1),
    temp_min          NUMERIC(4,1),
    precipitation_mm  NUMERIC(5,1),
    humidity_pct      INT,
    weather_source    TEXT NOT NULL DEFAULT 'AUTO',
    memo              TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ
);
CREATE INDEX idx_diaries_user_date ON farm_diaries (user_id, diary_date DESC) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_diaries_user_loc_date_alive
    ON farm_diaries (user_id, farm_location_id, diary_date)
    WHERE deleted_at IS NULL;

-- =========================
-- 8. diary_work_blocks
-- =========================
CREATE TABLE diary_work_blocks (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    diary_id    BIGINT NOT NULL REFERENCES farm_diaries(id) ON DELETE CASCADE,
    work_type   TEXT NOT NULL,
    detail      TEXT,
    sort_order  INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_work_blocks_diary ON diary_work_blocks (diary_id);

-- =========================
-- 9. diary_photos
-- =========================
CREATE TABLE diary_photos (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    diary_id    BIGINT NOT NULL REFERENCES farm_diaries(id) ON DELETE CASCADE,
    s3_key      TEXT NOT NULL,
    size_bytes  INT NOT NULL,
    sort_order  INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_photos_diary ON diary_photos (diary_id);

-- =========================
-- 10. content_jobs
-- =========================
CREATE TABLE content_jobs (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform          TEXT NOT NULL,
    crop_id           BIGINT NOT NULL REFERENCES crops(id),
    diary_ids         BIGINT[],
    keywords          TEXT,
    extra_photo_keys  TEXT[],
    status            TEXT NOT NULL DEFAULT 'QUEUED',
    progress_pct      SMALLINT NOT NULL DEFAULT 0,
    failure_reason    TEXT,
    regenerated_from  BIGINT REFERENCES content_jobs(id),
    credit_charged    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    done_at           TIMESTAMPTZ
);
CREATE INDEX idx_jobs_user_created ON content_jobs (user_id, created_at DESC);

-- =========================
-- 11. content_results
-- =========================
CREATE TABLE content_results (
    job_id           BIGINT PRIMARY KEY REFERENCES content_jobs(id) ON DELETE CASCADE,
    card_image_keys  TEXT[] NOT NULL,
    caption          TEXT,
    hashtags         TEXT[],
    meta             JSONB
);

-- =========================
-- 12. subscriptions
-- =========================
CREATE TABLE subscriptions (
    user_id                 BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    plan                    TEXT NOT NULL DEFAULT 'FREE',
    status                  TEXT NOT NULL DEFAULT 'ACTIVE',
    billing_key             TEXT,
    started_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_period_start    TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_period_end      TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '30 days'),
    credits_used            INT NOT NULL DEFAULT 0,
    credits_limit_period    INT NOT NULL DEFAULT 5,
    credits_reset_at        TIMESTAMPTZ NOT NULL DEFAULT (date_trunc('month', now()) + INTERVAL '1 month'),
    grace_started_at        TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================
-- 13. payments
-- =========================
CREATE TABLE payments (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id),
    plan            TEXT NOT NULL,
    amount          INT NOT NULL,
    pg              TEXT NOT NULL,
    pg_payment_id   TEXT,
    merchant_uid    TEXT UNIQUE,
    status          TEXT NOT NULL,
    paid_at         TIMESTAMPTZ,
    receipt_url     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_payments_user ON payments (user_id);

-- =========================
-- 14. notification_settings
-- =========================
CREATE TABLE notification_settings (
    user_id                  BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    push_enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    trend_push_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    marketing_push_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================
-- 15. push_tokens
-- =========================
CREATE TABLE push_tokens (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform      TEXT NOT NULL,
    token         TEXT UNIQUE NOT NULL,
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_push_tokens_user ON push_tokens (user_id);

-- =========================
-- 16. deletion_requests
-- =========================
CREATE TABLE deletion_requests (
    user_id       BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    purge_at      TIMESTAMPTZ NOT NULL,
    canceled_at   TIMESTAMPTZ
);

-- =========================
-- 17. auth_sessions (refresh token whitelist)
-- =========================
CREATE TABLE auth_sessions (
    id                   UUID PRIMARY KEY,
    user_id              BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash   TEXT NOT NULL,
    user_agent           TEXT,
    ip                   INET,
    issued_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at           TIMESTAMPTZ NOT NULL,
    revoked_at           TIMESTAMPTZ
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions (user_id);
CREATE INDEX idx_auth_sessions_hash ON auth_sessions (refresh_token_hash);

-- =========================
-- 18. ai_regenerations (재생성 메타: AI-006)
-- =========================
CREATE TABLE ai_regenerations (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    root_job_id     BIGINT NOT NULL REFERENCES content_jobs(id),
    new_job_id      BIGINT NOT NULL REFERENCES content_jobs(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_regen_root ON ai_regenerations (root_job_id);
