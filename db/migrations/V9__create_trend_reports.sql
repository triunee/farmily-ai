CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS trend_reports (
    id          SERIAL PRIMARY KEY,
    report_date DATE        NOT NULL,
    source      TEXT        NOT NULL DEFAULT 'summary',
    content     TEXT        NOT NULL,
    embedding   vector(1024),
    meta        JSONB,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (report_date, source)
);

CREATE INDEX IF NOT EXISTS idx_trend_reports_date
    ON trend_reports (report_date DESC);
