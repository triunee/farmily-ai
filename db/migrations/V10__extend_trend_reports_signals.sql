-- 트렌드 검색 고도화: 리포트 청킹 + 하이브리드(pg_trgm + pgvector) 검색

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1) 조각·태그 컬럼 추가 (기존 행은 default 적용, 영향 없음)
ALTER TABLE trend_reports ADD COLUMN IF NOT EXISTS chunk_idx  INT    NOT NULL DEFAULT 0;
ALTER TABLE trend_reports ADD COLUMN IF NOT EXISTS crops      TEXT[] DEFAULT '{}';
ALTER TABLE trend_reports ADD COLUMN IF NOT EXISTS keywords   TEXT[] DEFAULT '{}';
ALTER TABLE trend_reports ADD COLUMN IF NOT EXISTS change_pct NUMERIC;

-- 2) 하루 1행 제약 완화 → (날짜,소스,조각)로 다행 허용
ALTER TABLE trend_reports DROP CONSTRAINT IF EXISTS trend_reports_report_date_source_key;
ALTER TABLE trend_reports ADD  CONSTRAINT trend_reports_date_source_chunk_key
      UNIQUE (report_date, source, chunk_idx);

-- 3) 레거시 프로즈 blob 임베딩 제거 → 검색 오염 방지
--    (WHERE embedding IS NOT NULL 이 자동으로 프로즈 행을 배제하게 됨)
UPDATE trend_reports SET embedding = NULL WHERE source = 'summary';

-- 4) 문자매칭 인덱스 (트라이그램 GIN) — 한국어 부분매칭/조사변형에 강함
CREATE INDEX IF NOT EXISTS idx_trend_reports_content_trgm
    ON trend_reports USING gin (content gin_trgm_ops);
