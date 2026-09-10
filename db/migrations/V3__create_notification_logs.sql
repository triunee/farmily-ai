CREATE TABLE notification_logs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    sent_date   DATE NOT NULL,
    UNIQUE (user_id, kind, sent_date)
);
CREATE INDEX idx_notif_log_user ON notification_logs (user_id);

-- 영농일지 리마인드 전용 컬럼 추가
ALTER TABLE notification_settings
    ADD COLUMN diary_reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE;
