CREATE TABLE IF NOT EXISTS partners (
    id VARCHAR(36) PRIMARY KEY,
    key VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    internal_role VARCHAR(40),
    partner_id VARCHAR(36) REFERENCES partners(id),
    partner_role VARCHAR(40),
    password_hash TEXT,
    invitation_token VARCHAR(120) UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_partner_id ON users(partner_id);

CREATE TABLE IF NOT EXISTS clients (
    id VARCHAR(36) PRIMARY KEY,
    key VARCHAR(80) NOT NULL UNIQUE,
    partner_id VARCHAR(36) NOT NULL REFERENCES partners(id),
    name VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_clients_partner_id ON clients(partner_id);

CREATE TABLE IF NOT EXISTS client_assignments (
    id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES clients(id),
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_assignment UNIQUE (client_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_client_assignments_client_id ON client_assignments(client_id);
CREATE INDEX IF NOT EXISTS ix_client_assignments_user_id ON client_assignments(user_id);

CREATE TABLE IF NOT EXISTS tickets (
    id VARCHAR(36) PRIMARY KEY,
    partner_id VARCHAR(36) REFERENCES partners(id),
    client_id VARCHAR(36) REFERENCES clients(id),
    owner_id VARCHAR(36) REFERENCES users(id),
    created_by_id VARCHAR(36) NOT NULL REFERENCES users(id),
    internal BOOLEAN NOT NULL DEFAULT FALSE,
    type VARCHAR(80) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'New',
    resolver_team VARCHAR(20),
    assignee_id VARCHAR(36) REFERENCES users(id),
    title VARCHAR(240) NOT NULL,
    description TEXT NOT NULL,
    gitlab_error_overridden BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tickets_partner_id ON tickets(partner_id);
CREATE INDEX IF NOT EXISTS ix_tickets_client_id ON tickets(client_id);
CREATE INDEX IF NOT EXISTS ix_tickets_owner_id ON tickets(owner_id);
CREATE INDEX IF NOT EXISTS ix_tickets_internal ON tickets(internal);
CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS ix_tickets_resolver_team ON tickets(resolver_team);
CREATE INDEX IF NOT EXISTS ix_tickets_assignee_id ON tickets(assignee_id);

CREATE TABLE IF NOT EXISTS ticket_participants (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id),
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ticket_participant UNIQUE (ticket_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_ticket_participants_ticket_id ON ticket_participants(ticket_id);
CREATE INDEX IF NOT EXISTS ix_ticket_participants_user_id ON ticket_participants(user_id);

CREATE TABLE IF NOT EXISTS ticket_watchers (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id),
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_ticket_watcher UNIQUE (ticket_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_ticket_watchers_ticket_id ON ticket_watchers(ticket_id);
CREATE INDEX IF NOT EXISTS ix_ticket_watchers_user_id ON ticket_watchers(user_id);

CREATE TABLE IF NOT EXISTS comments (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id),
    author_id VARCHAR(36) NOT NULL REFERENCES users(id),
    visibility VARCHAR(30) NOT NULL DEFAULT 'comment',
    body TEXT NOT NULL,
    deleted_at TIMESTAMPTZ,
    edited_at TIMESTAMPTZ,
    changed_by_user_id VARCHAR(36) REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_comments_ticket_id ON comments(ticket_id);

CREATE TABLE IF NOT EXISTS comment_revisions (
    id VARCHAR(36) PRIMARY KEY,
    comment_id VARCHAR(36) NOT NULL REFERENCES comments(id),
    body TEXT NOT NULL,
    action VARCHAR(40) NOT NULL,
    changed_by_user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_comment_revisions_comment_id ON comment_revisions(comment_id);

CREATE TABLE IF NOT EXISTS attachments (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id),
    comment_id VARCHAR(36) REFERENCES comments(id),
    uploaded_by_id VARCHAR(36) NOT NULL REFERENCES users(id),
    filename VARCHAR(260) NOT NULL,
    content_type VARCHAR(160) NOT NULL,
    size_bytes INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_attachments_ticket_id ON attachments(ticket_id);

CREATE TABLE IF NOT EXISTS gitlab_links (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id),
    is_main BOOLEAN NOT NULL DEFAULT TRUE,
    project_id VARCHAR(120) NOT NULL,
    issue_iid VARCHAR(120) NOT NULL,
    issue_id VARCHAR(120),
    web_url TEXT NOT NULL,
    issue_state VARCHAR(40) NOT NULL DEFAULT 'opened',
    board_list VARCHAR(80),
    status VARCHAR(40) NOT NULL DEFAULT 'Open',
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_gitlab_main_ticket UNIQUE (ticket_id, is_main)
);
CREATE INDEX IF NOT EXISTS ix_gitlab_links_ticket_id ON gitlab_links(ticket_id);

CREATE TABLE IF NOT EXISTS gitlab_sync_events (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id),
    action VARCHAR(80) NOT NULL,
    status VARCHAR(40) NOT NULL,
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_gitlab_sync_events_ticket_id ON gitlab_sync_events(ticket_id);

CREATE TABLE IF NOT EXISTS notifications (
    id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) REFERENCES tickets(id),
    event VARCHAR(80) NOT NULL,
    recipient_email VARCHAR(320) NOT NULL,
    subject VARCHAR(240) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_notifications_ticket_id ON notifications(ticket_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    entity_type VARCHAR(80) NOT NULL,
    entity_id VARCHAR(80) NOT NULL,
    action VARCHAR(100) NOT NULL,
    old_value JSONB,
    new_value JSONB,
    changed_by_user_id VARCHAR(36) REFERENCES users(id),
    source VARCHAR(40) NOT NULL DEFAULT 'ui',
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_type ON audit_logs(entity_type);
CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_id ON audit_logs(entity_id);
