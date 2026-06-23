-- Audit list filters and default ordering (changed_at DESC).
CREATE INDEX IF NOT EXISTS idx_audit_logs_changed_at_desc ON audit_logs (changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action_changed ON audit_logs (action, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_source_changed ON audit_logs (source, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_type_changed ON audit_logs (entity_type, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_id_changed ON audit_logs (entity_id, changed_at DESC);

-- Ticket dashboard filters combined with created_at ordering.
CREATE INDEX IF NOT EXISTS idx_tickets_status_created ON tickets (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_priority_created ON tickets (priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_type_created ON tickets (type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_resolver_team_created ON tickets (resolver_team, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_internal_created ON tickets (internal, created_at DESC);
