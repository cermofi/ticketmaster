CREATE TABLE IF NOT EXISTS gitlab_issue_manual_mappings (
    id VARCHAR(36) PRIMARY KEY,
    delivery_project_id VARCHAR(120) NOT NULL,
    delivery_issue_iid VARCHAR(120) NOT NULL,
    target_url TEXT NOT NULL,
    target_project_id VARCHAR(120) NULL,
    target_project_name VARCHAR(255) NULL,
    target_issue_iid VARCHAR(120) NULL,
    created_by_user_id VARCHAR(36) NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_gitlab_issue_manual_mapping UNIQUE (delivery_project_id, delivery_issue_iid)
);

CREATE INDEX IF NOT EXISTS idx_gitlab_issue_manual_mappings_project_iid
    ON gitlab_issue_manual_mappings (delivery_project_id, delivery_issue_iid);

CREATE TABLE IF NOT EXISTS gitlab_tracked_issues (
    id VARCHAR(36) PRIMARY KEY,
    delivery_project_id VARCHAR(120) NOT NULL,
    delivery_issue_id VARCHAR(120) NULL,
    delivery_issue_iid VARCHAR(120) NOT NULL,
    delivery_title VARCHAR(500) NOT NULL,
    delivery_url TEXT NOT NULL,
    delivery_state VARCHAR(40) NOT NULL,
    delivery_labels JSONB NULL,
    delivery_created_at TIMESTAMPTZ NULL,
    delivery_updated_at TIMESTAMPTZ NULL,
    delivery_closed_at TIMESTAMPTZ NULL,
    moved_to_id VARCHAR(120) NULL,
    resolution_source VARCHAR(40) NOT NULL DEFAULT 'none',
    target_missing BOOLEAN NOT NULL DEFAULT FALSE,
    target_project_id VARCHAR(120) NULL,
    target_project_name VARCHAR(255) NULL,
    target_team_name VARCHAR(255) NULL,
    target_issue_id VARCHAR(120) NULL,
    target_issue_iid VARCHAR(120) NULL,
    target_url TEXT NULL,
    target_state VARCHAR(40) NULL,
    target_labels JSONB NULL,
    target_assignees JSONB NULL,
    target_updated_at TIMESTAMPTZ NULL,
    sync_status VARCHAR(40) NOT NULL DEFAULT 'pending',
    sync_error TEXT NULL,
    manual_mapping_id VARCHAR(36) NULL REFERENCES gitlab_issue_manual_mappings(id),
    last_synced_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_gitlab_tracked_issue UNIQUE (delivery_project_id, delivery_issue_iid)
);

CREATE INDEX IF NOT EXISTS idx_gitlab_tracked_issues_status
    ON gitlab_tracked_issues (sync_status);

CREATE INDEX IF NOT EXISTS idx_gitlab_tracked_issues_target_team
    ON gitlab_tracked_issues (target_team_name);

CREATE INDEX IF NOT EXISTS idx_gitlab_tracked_issues_target_state
    ON gitlab_tracked_issues (target_state);

CREATE INDEX IF NOT EXISTS idx_gitlab_tracked_issues_target_missing
    ON gitlab_tracked_issues (target_missing);

CREATE INDEX IF NOT EXISTS idx_gitlab_tracked_issues_target_updated
    ON gitlab_tracked_issues (target_updated_at);

CREATE INDEX IF NOT EXISTS idx_gitlab_tracked_issues_delivery_updated
    ON gitlab_tracked_issues (delivery_updated_at);

CREATE TABLE IF NOT EXISTS gitlab_issue_sync_runs (
    id VARCHAR(36) PRIMARY KEY,
    status VARCHAR(40) NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    total_issues INTEGER NOT NULL DEFAULT 0,
    resolved_targets INTEGER NOT NULL DEFAULT 0,
    missing_targets INTEGER NOT NULL DEFAULT 0,
    failed_targets INTEGER NOT NULL DEFAULT 0,
    manual_mappings_used INTEGER NOT NULL DEFAULT 0,
    moved_to_resolutions INTEGER NOT NULL DEFAULT 0,
    note_resolutions INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_gitlab_issue_sync_runs_started_at
    ON gitlab_issue_sync_runs (started_at DESC);
