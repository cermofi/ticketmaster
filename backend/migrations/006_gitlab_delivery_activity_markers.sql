ALTER TABLE gitlab_tracked_issues
    ADD COLUMN IF NOT EXISTS activity_source VARCHAR(20),
    ADD COLUMN IF NOT EXISTS activity_description_digest VARCHAR(64),
    ADD COLUMN IF NOT EXISTS activity_comment_count INTEGER;
