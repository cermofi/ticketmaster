CREATE INDEX IF NOT EXISTS idx_tickets_fulltext_simple
ON tickets
USING gin (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(description, '')));

CREATE INDEX IF NOT EXISTS idx_comments_body_fulltext_simple
ON comments
USING gin (to_tsvector('simple', coalesce(body, '')))
WHERE deleted_at IS NULL AND visibility = 'comment';
