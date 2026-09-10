-- Farmily AI 콘텐츠 생성 — 작물 지식 테이블
-- 농식품우리누리 크롤링 데이터 저장

-- =========================
-- 5-1. crop_knowledge
-- =========================
CREATE TABLE crop_knowledge (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    crop_name         TEXT        NOT NULL UNIQUE,
    category          TEXT,
    season_month      INT,
    harvest_months    INT[],
    production_period TEXT,
    origin_region     TEXT,
    cooking_method    TEXT,
    storage_method    TEXT,
    nutrition_brief   TEXT,
    effect_brief      TEXT,
    purchase_tip      TEXT,
    source_url        TEXT        NOT NULL,
    crawled_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_crop_knowledge_name    ON crop_knowledge (crop_name);
CREATE INDEX idx_crop_knowledge_season  ON crop_knowledge (season_month);
CREATE INDEX idx_crop_knowledge_harvest ON crop_knowledge USING GIN (harvest_months);
