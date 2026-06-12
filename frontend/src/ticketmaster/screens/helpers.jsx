import React from 'react';
import { Alert } from 'reactstrap';
import { Spinner } from 'asab_webui_components';
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
      <span className="tm-muted">Loading...</span>
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
  const normalizedTone = tone || (priority ? priorityTone(priority) : statusTone(value));
  const className = `tm-status tm-status-${normalizedTone}`;
  return <span className={className}>{labelValue(value) || 'No value'}</span>;
}

export function TimeCell({ value }) {
  if (!value) return <span className="tm-muted">-</span>;
  return <span>{formatDateTime(value)}</span>;
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
  if (role === 'responsible') return 'Responsible';
  if (role === 'technical') return 'Technical';
  return role;
}

export function apiError(err) {
  return err.response?.data?.detail || err.message || 'Unexpected error';
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
    DeliveryManager: 'Delivery Manager',
    system: 'System',
    internal: 'Internal',
    partner: 'Partner',
    System: 'System',
    Internal: 'Internal'
  };
  return labels[value] || value;
}

function statusTone(value) {
  if (value === 'Resolved') return 'success';
  if (['Rejected', 'Failed'].includes(value)) return 'danger';
  if (['In progress', 'Need more info', 'Assigned'].includes(value)) return 'warning';
  if (['Closed', 'Cancelled', 'Duplicate'].includes(value)) return 'muted';
  if (value === 'New') return 'neutral';
  if (!value) return 'muted';
  return 'soft';
}

function priorityTone(priority) {
  if (priority === 'Critical') return 'danger';
  if (priority === 'High') return 'warning';
  return 'muted';
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const rowDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((today.getTime() - rowDay.getTime()) / 86400000);

  const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' }).format(date);
  if (diffDays === 0) return `Today ${time}`;
  if (diffDays === 1) return `Yesterday ${time}`;
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}
