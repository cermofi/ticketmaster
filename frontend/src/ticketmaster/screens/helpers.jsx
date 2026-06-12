import React from 'react';
import { Alert } from 'reactstrap';
import { DateTime, Spinner } from 'asab_webui_components';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function ErrorBanner({ error }) {
  if (!error) return null;
  return (
    <Alert color="danger" className="tm-alert" role="alert">
      {error}
    </Alert>
  );
}

export function Loading() {
  return (
    <div className="tm-screen tm-loading-state" aria-live="polite">
      <Spinner />
      <span className="tm-muted">Načítání...</span>
    </div>
  );
}

export function PageHeader({ title, eyebrow, actions, children }) {
  return (
    <header className="tm-page-header">
      <div className="tm-page-heading">
        {eyebrow && <div className="tm-page-eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {children && <div className="tm-page-subtitle">{children}</div>}
      </div>
      {actions && <div className="tm-page-actions">{actions}</div>}
    </header>
  );
}

export function EmptyState({ icon = 'bi-inbox', title, message }) {
  return (
    <div className="tm-empty-state">
      <i className={`bi ${icon}`} aria-hidden="true" />
      <strong>{title}</strong>
      {message && <span>{message}</span>}
    </div>
  );
}

export function EmptyRow({ colSpan, title, message }) {
  return (
    <tr>
      <td colSpan={colSpan}>
        <EmptyState title={title} message={message} />
      </td>
    </tr>
  );
}

export function StatusPill({ value, priority, tone }) {
  const normalizedTone = tone || (priority === 'Critical' ? 'danger' : statusTone(value));
  const className = `tm-status tm-status-${normalizedTone}`;
  return <span className={className}>{labelValue(value) || 'Bez hodnoty'}</span>;
}

export function TimeCell({ value }) {
  if (!value) return <span className="tm-muted">-</span>;
  return <DateTime value={value} />;
}

export function MarkdownText({ content, className = '', emptyMessage = '' }) {
  const text = typeof content === 'string' ? content : '';
  const normalizedClassName = className.trim();
  if (!text.trim()) {
    if (!emptyMessage) return null;
    const emptyClassName = normalizedClassName ? `${normalizedClassName} tm-muted` : 'tm-muted';
    return <p className={emptyClassName}>{emptyMessage}</p>;
  }
  return (
    <ReactMarkdown
      className={normalizedClassName}
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ ...props }) => <a {...props} target="_blank" rel="noreferrer" />
      }}
    >
      {text}
    </ReactMarkdown>
  );
}

export function roleLabel(role) {
  if (role === 'DeliveryManager') return 'Delivery Manager';
  if (role === 'responsible') return 'Odpovědná osoba';
  if (role === 'technical') return 'Technická osoba';
  return role;
}

export function apiError(err) {
  return err.response?.data?.detail || err.message || 'Neočekávaná chyba';
}

export function asArray(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.results)) return value.results;
  if (Array.isArray(value?.data)) return value.data;
  return [];
}

export function labelValue(value) {
  const labels = {
    Question: 'Dotaz',
    Incident: 'Incident',
    Change: 'Změna',
    'Operational Request': 'Provozní požadavek',
    Normal: 'Normální',
    High: 'Vysoká',
    Critical: 'Kritická',
    Low: 'Nízká',
    Open: 'Otevřený',
    New: 'Nový',
    Queued: 'Ve frontě',
    Assigned: 'Přiřazený',
    'In Progress': 'V řešení',
    'Waiting for Customer': 'Čeká na klienta',
    'Waiting for Partner': 'Čeká na partnera',
    Resolved: 'Vyřešený',
    Closed: 'Uzavřený',
    Rejected: 'Zamítnutý',
    Blocked: 'Blokovaný',
    Done: 'Hotovo',
    Failed: 'Selhalo',
    system: 'Systémový',
    internal: 'Interní',
    partner: 'Partnerský',
    System: 'Systémový',
    Internal: 'Interní'
  };
  return labels[value] || value;
}

function statusTone(value) {
  if (['Closed', 'Resolved', 'Done'].includes(value)) return 'success';
  if (['Rejected', 'Blocked', 'Failed'].includes(value)) return 'danger';
  if (['In Progress', 'Waiting for Customer', 'Waiting for Partner'].includes(value)) return 'warning';
  if (!value) return 'muted';
  return 'neutral';
}
