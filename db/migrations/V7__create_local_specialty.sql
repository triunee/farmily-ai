-- Farmily AI — 지역 특산물 RAG 테이블
-- local_specialty_rag.json 기반 (지역N문화 크롤링)

CREATE TABLE local_specialty (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    crop_name   TEXT        NOT NULL,
    local_name  TEXT,                       -- 지역 특산물명 (논산딸기, 고성 참다래)
    region      TEXT,                       -- 생산 지역 (충청남도 논산시)
    source      TEXT        NOT NULL DEFAULT '지역N문화',
    content     TEXT        NOT NULL,       -- RAG용 스토리 본문
    embedding   vector(1024),              -- Bedrock Titan V2
    source_url  TEXT,
    crawled_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_local_specialty UNIQUE (crop_name, region)
);

CREATE INDEX idx_local_specialty_crop   ON local_specialty (crop_name);
CREATE INDEX idx_local_specialty_region ON local_specialty (region);
