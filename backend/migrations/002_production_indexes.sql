CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_tickets_updated_at_desc ON tickets (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_created_at_desc ON tickets (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_status_updated ON tickets (status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_priority_updated ON tickets (priority, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_type_updated ON tickets (type, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_resolver_team_updated ON tickets (resolver_team, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_partner_updated ON tickets (partner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_owner_updated ON tickets (owner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_assignee_updated ON tickets (assignee_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_internal_updated ON tickets (internal, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_title_trgm ON tickets USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tickets_description_trgm ON tickets USING gin (description gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_comments_ticket_created ON comments (ticket_id, created_at);
CREATE INDEX IF NOT EXISTS idx_comments_author_created ON comments (author_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attachments_ticket_created ON attachments (ticket_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_changed ON audit_logs (entity_type, entity_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_changed ON audit_logs (changed_by_user_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_status_created ON notifications (status, created_at);
CREATE INDEX IF NOT EXISTS idx_gitlab_links_ticket_main ON gitlab_links (ticket_id, is_main);
