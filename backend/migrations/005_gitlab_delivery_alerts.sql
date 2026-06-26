CREATE TABLE IF NOT EXISTS gitlab_delivery_alerts (
    id VARCHAR(36) PRIMARY KEY,
    tracked_issue_id VARCHAR(36) NOT NULL REFERENCES gitlab_tracked_issues(id),
    delivery_issue_iid VARCHAR(120) NOT NULL,
    delivery_title VARCHAR(500) NOT NULL,
    delivery_url TEXT,
    target_url TEXT,
    alert_kind VARCHAR(40) NOT NULL,
    message TEXT NOT NULL,
    changes JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gitlab_delivery_alerts_created_at ON gitlab_delivery_alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gitlab_delivery_alerts_tracked_issue ON gitlab_delivery_alerts (tracked_issue_id);
CREATE INDEX IF NOT EXISTS idx_gitlab_delivery_alerts_delivery_issue_iid ON gitlab_delivery_alerts (delivery_issue_iid);

CREATE TABLE IF NOT EXISTS gitlab_delivery_alert_reads (
    id VARCHAR(36) PRIMARY KEY,
    alert_id VARCHAR(36) NOT NULL REFERENCES gitlab_delivery_alerts(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_gitlab_delivery_alert_read UNIQUE (alert_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_gitlab_delivery_alert_reads_user ON gitlab_delivery_alert_reads (user_id, read_at DESC);
CREATE INDEX IF NOT EXISTS idx_gitlab_delivery_alert_reads_alert ON gitlab_delivery_alert_reads (alert_id);
