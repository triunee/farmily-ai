-- Farmily AI 콘텐츠 생성 — pgvector 확장 + RAG 벡터 테이블
-- 레시피 벡터 저장 (Bedrock KB 대체)
-- trend_insights 는 미정으로 제외

-- =========================
-- 6-1. pgvector 확장 활성화
-- =========================
CREATE EXTENSION IF NOT EXISTS vector;

-- =========================
-- 6-2. recipe_embeddings
-- =========================
CREATE TABLE recipe_embeddings (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    crop_name    TEXT        NOT NULL,
    dish_name    TEXT,                       -- 핵심 요리명 (tag 기반: 우엉조림, 시금치무침)
    recipe_name  TEXT        NOT NULL,       -- 블로그형 레시피 제목
    source       TEXT        NOT NULL,       -- '10000recipe' | 'greenpeace_pdf' | 'korean_recipe_pdf'
    servings     TEXT,                       -- 인분 (4인분)
    cook_time    TEXT,                       -- 조리시간 (30분 이내)
    ingredients  TEXT,                       -- 재료 목록 (콤마 구분 문자열)
    instructions TEXT,                       -- 조리 단계 (공백 구분 문자열)
    main_crops   TEXT[],                     -- 주재료 배열 ['우엉', '당근']
    content      TEXT        NOT NULL,       -- RAG용 통합 텍스트 (임베딩 대상)
    embedding    vector(1024),               -- Bedrock Titan V2 (기본 1024차원)
    source_url   TEXT,                       -- 출처 URL
    crawled_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_recipe UNIQUE (crop_name, recipe_name, source)
);

CREATE INDEX idx_recipe_crop   ON recipe_embeddings (crop_name);
CREATE INDEX idx_recipe_dish   ON recipe_embeddings (dish_name);
CREATE INDEX idx_recipe_source ON recipe_embeddings (source);
