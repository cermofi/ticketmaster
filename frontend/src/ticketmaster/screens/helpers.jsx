import React, { useLayoutEffect } from 'react';
import { Alert } from 'reactstrap';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

let loadingStateMounts = 0;

export function ErrorBanner({ error }) {
  if (!error) return null;
  return (
    <Alert color="danger" className="tm-alert" role="alert">
      {error}
    </Alert>
  );
}

export function Loading() {
  useLayoutEffect(() => {
    loadingStateMounts += 1;
    document.body.classList.add('tm-route-loading');
    return () => {
      loadingStateMounts = Math.max(loadingStateMounts - 1, 0);
      if (loadingStateMounts === 0) {
        document.body.classList.remove('tm-route-loading');
      }
    };
  }, []);

  return (
    <div className="tm-screen tm-loading-state" aria-live="polite">
      <span className="tm-loading-ring" aria-hidden="true" />
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

export function AbsoluteTimeCell({ value }) {
  if (!value) return <span className="tm-muted">-</span>;
  return <span>{formatAbsoluteDateTime(value)}</span>;
}

export function MarkdownText({ content, renderedHtml = '', className = '', emptyMessage = '' }) {
  const text = typeof content === 'string' ? content : '';
  const html = normalizeRenderedHtml(renderedHtml);
  const normalizedText = text.replace(/\r\n?/g, '\n');
  const normalizedClassName = className.trim();
  if (html) {
    // GitLab markdown API output is already sanitized and safe to render as HTML.
    return <div className={normalizedClassName} dangerouslySetInnerHTML={{ __html: html }} />;
  }
  if (!normalizedText.trim()) {
    if (!emptyMessage) return null;
    const emptyClassName = normalizedClassName ? `${normalizedClassName} tm-muted` : 'tm-muted';
    return <p className={emptyClassName}>{emptyMessage}</p>;
  }
  return (
    <ReactMarkdown
      className={normalizedClassName}
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
        table: ({ children, ...props }) => (
          <div className="tm-markdown-table-wrap">
            <table {...props}>{children}</table>
          </div>
        )
      }}
    >
      {normalizedText}
    </ReactMarkdown>
  );
}

function normalizeRenderedHtml(value) {
  const rawHtml = typeof value === 'string' ? value.trim() : '';
  if (!rawHtml) return '';
  if (typeof window === 'undefined' || typeof window.DOMParser !== 'function') return rawHtml;
  try {
    const parser = new window.DOMParser();
    const documentRoot = parser.parseFromString(`<div>${rawHtml}</div>`, 'text/html');
    const container = documentRoot.body.firstElementChild;
    if (!container) return rawHtml;
    container.querySelectorAll('a').forEach((link) => {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noreferrer');
    });
    container.querySelectorAll('table').forEach((table) => {
      if (table.parentElement?.classList.contains('tm-markdown-table-wrap')) return;
      const wrapper = documentRoot.createElement('div');
      wrapper.className = 'tm-markdown-table-wrap';
      table.parentNode?.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    });
    return container.innerHTML;
  } catch {
    return rawHtml;
  }
}

export function roleLabel(role) {
  if (role === 'DeliveryManager') return 'Delivery Manager';
  if (role === 'responsible') return 'Responsible';
  if (role === 'technical') return 'Technical';
  return role;
}

export function getInternalRoles(user) {
  if (!user || user.kind !== 'internal') return [];
  if (Array.isArray(user.internal_roles) && user.internal_roles.length) return user.internal_roles;
  if (user.internal_role) return [user.internal_role];
  return [];
}

export function hasInternalRole(user, role) {
  return getInternalRoles(user).includes(role);
}

export function hasAnyInternalRole(user, roles) {
  return roles.some((role) => hasInternalRole(user, role));
}

export function formatInternalRoles(user) {
  return getInternalRoles(user).map((role) => roleLabel(role)).join(', ');
}

export function apiError(err) {
  const data = err?.response?.data;
  if (typeof data?.message === 'string' && data.message) return data.message;
  if (typeof data?.detail === 'string' && data.detail) return data.detail;
  if (Array.isArray(data?.detail)) return 'Request validation failed';
  return err?.message || 'Unexpected error';
}

export function normalizeApiPath(path) {
  if (typeof path !== 'string') return path;
  if (path.startsWith('/api/')) return path.slice(4);
  return path;
}

export function downloadResponse(response, fallbackName) {
  const disposition = response.headers?.['content-disposition'] || '';
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || fallbackName;
  const blob = new Blob([response.data], { type: response.headers?.['content-type'] || 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function exportError(err) {
  if (err.response?.data instanceof Blob) {
    const text = await err.response.data.text();
    try {
      const parsed = JSON.parse(text);
      return parsed.message || parsed.detail || text;
    } catch {
      return text || 'Export could not be created.';
    }
  }
  return apiError(err);
}

export function ScreenBody({ loading, error, loadingFallback = null, children }) {
  return (
    <>
      <ErrorBanner error={error} />
      {loading ? (loadingFallback || <Loading />) : children}
    </>
  );
}

export function formatAttachmentSize(size) {
  if (!size) return '0 B';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
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
  if (value === 'Queued') return 'queued';
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

export function formatAbsoluteDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Prague',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).formatToParts(date);

  const get = (type) => parts.find((part) => part.type === type)?.value ?? '';
  return `${get('day')}.${get('month')}.${get('year')} ${get('hour')}:${get('minute')}:${get('second')}`;
}
