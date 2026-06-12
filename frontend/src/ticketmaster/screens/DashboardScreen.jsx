import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import {
  Button,
  ButtonDropdown,
  DropdownItem,
  DropdownMenu,
  DropdownToggle,
  Form,
  FormGroup,
  Input,
  Label,
  Table
} from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { usePolling, useRefetchOnFocus } from '../hooks/useLiveRefresh.js';
import { EmptyRow, ErrorBanner, Loading, MarkdownText, PageHeader, StatusPill, TimeCell, apiError, asArray, labelValue } from './helpers.jsx';

const EMPTY_FILTERS = { search: '', status: '', priority: '', type: '', resolver_team: '', internal: '' };
const TICKETS_POLL_MS = 30000;
const SEARCH_DEBOUNCE_MS = 320;
const ATTACHMENT_ACCEPT = '.png,.jpg,.jpeg,.pdf,.txt,.log,.zip';
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;
const ALLOWED_ATTACHMENT_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.pdf', '.txt', '.log', '.zip']);
const DEFAULT_SORT = { key: 'updated', direction: 'desc' };
const PRIORITY_RANK = new Map([
  ['Critical', 0],
  ['High', 1],
  ['Normal', 2],
  ['Low', 3]
]);

export default function DashboardScreen() {
  return (
    <AuthGate>
      {(user) => <Dashboard user={user} />}
    </AuthGate>
  );
}

function Dashboard({ user }) {
  const [meta, setMeta] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [sortConfig, setSortConfig] = useState(DEFAULT_SORT);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [moreOpen, setMoreOpen] = useState(false);
  const [exportLoading, setExportLoading] = useState('');
  const filtersRef = useRef(filters);
  const isInitialSearchSync = useRef(true);
  filtersRef.current = filters;

  const load = useCallback(async (nextFilters) => {
    const activeFilters = nextFilters ?? filtersRef.current;
    setError('');
    setLoading(true);
    try {
      const params = Object.fromEntries(Object.entries(activeFilters).filter(([, value]) => value !== ''));
      const [metaResponse, ticketsResponse] = await Promise.all([
        api.get('/meta'),
        api.get('/tickets', { params })
      ]);
      setMeta(metaResponse.data);
      setTickets(asArray(ticketsResponse.data));
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const exportTickets = async (format) => {
    setError('');
    setExportLoading(format);
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''));
      const response = await api.get('/tickets/export', { params: { ...params, format }, responseType: 'blob' });
      downloadResponse(response, `ticketmaster_export.${format === 'csv' ? 'zip' : format}`);
    } catch (err) {
      setError(await exportError(err));
    } finally {
      setExportLoading('');
    }
  };

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (isInitialSearchSync.current) {
      isInitialSearchSync.current = false;
      return undefined;
    }
    const timeout = window.setTimeout(() => {
      load();
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timeout);
  }, [filters.search, load]);

  useRefetchOnFocus(load);
  usePolling(load, TICKETS_POLL_MS);
  useEffect(() => {
    if (!loading && meta) {
      window.dispatchEvent(new Event('tm:dashboard-ready'));
    }
  }, [loading, meta]);

  const statusRank = useMemo(() => buildRankMap(asArray(meta?.statuses)), [meta]);
  const sortedTickets = useMemo(
    () => sortTickets(tickets, sortConfig, statusRank),
    [tickets, sortConfig, statusRank]
  );

  const onSortChange = (key) => {
    setSortConfig((current) => (
      current.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: key === 'updated' ? 'desc' : 'asc' }
    ));
  };

  const canCreateOnBehalf = user.kind === 'internal' && ['Admin', 'DeliveryManager'].includes(user.internal_role);

  return (
    <div className="tm-screen tm-tickets-screen">
      <PageHeader
        title="Tickets"
        actions={(
          <>
            <Button color="primary" tag={Link} to="/tickets/new">
              Create ticket
            </Button>
            <MoreActionsMenu
              isOpen={moreOpen}
              setOpen={setMoreOpen}
              canCreateOnBehalf={canCreateOnBehalf}
              loading={exportLoading}
              onExport={exportTickets}
            />
          </>
        )}
      />
      <ErrorBanner error={error} />
      {loading && !meta ? <Loading /> : (
        <>
          <TicketFilters
            filters={filters}
            setFilters={setFilters}
            meta={meta}
            user={user}
            onApply={load}
            onReset={() => {
              setFilters(EMPTY_FILTERS);
              load(EMPTY_FILTERS);
            }}
          />
          <TicketTable tickets={sortedTickets} sortConfig={sortConfig} onSortChange={onSortChange} />
        </>
      )}
    </div>
  );
}

function MoreActionsMenu({ isOpen, setOpen, canCreateOnBehalf, loading, onExport }) {
  return (
    <ButtonDropdown isOpen={isOpen} toggle={() => setOpen(!isOpen)}>
      <DropdownToggle color="secondary" outline caret>
        More
      </DropdownToggle>
      <DropdownMenu end>
        {canCreateOnBehalf && (
          <DropdownItem tag={Link} to="/tickets/new?mode=partner">
            Create for partner
          </DropdownItem>
        )}
        <DropdownItem disabled={Boolean(loading)} onClick={() => onExport('json')}>
          {loading === 'json' ? 'Exporting JSON...' : 'Export tickets (JSON)'}
        </DropdownItem>
        <DropdownItem disabled={Boolean(loading)} onClick={() => onExport('xlsx')}>
          {loading === 'xlsx' ? 'Exporting XLSX...' : 'Export tickets (XLSX)'}
        </DropdownItem>
        <DropdownItem disabled={Boolean(loading)} onClick={() => onExport('csv')}>
          {loading === 'csv' ? 'Exporting CSV ZIP...' : 'Export tickets (CSV ZIP)'}
        </DropdownItem>
      </DropdownMenu>
    </ButtonDropdown>
  );
}

function downloadResponse(response, fallbackName) {
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

async function exportError(err) {
  if (err.response?.data instanceof Blob) {
    const text = await err.response.data.text();
    try {
      return JSON.parse(text).detail || text;
    } catch {
      return text || 'Export could not be created.';
    }
  }
  return apiError(err);
}

async function uploadTicketAttachments(ticketId, files) {
  const rows = Array.isArray(files) ? files : [];
  if (rows.length === 0) return [];
  const failedUploads = [];
  for (const file of rows) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      await api.post(`/tickets/${ticketId}/attachments`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
    } catch (err) {
      failedUploads.push({ name: file.name, reason: apiError(err) });
    }
  }
  return failedUploads;
}

function formatAttachmentSize(size) {
  if (!size) return '0 B';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function TicketFilters({ filters, setFilters, meta, user, onApply, onReset }) {
  const update = (key, value) => setFilters({ ...filters, [key]: value });
  const updateAndApply = (key, value) => {
    const nextFilters = { ...filters, [key]: value };
    setFilters(nextFilters);
    onApply(nextFilters);
  };
  const statuses = asArray(meta?.statuses);
  const priorities = asArray(meta?.priorities);
  const ticketTypes = asArray(meta?.ticket_types);
  const resolverTeams = asArray(meta?.resolver_teams);
  const hasQueueFilter = user.kind === 'internal';

  return (
    <>
      <Form className="tm-ticket-searchbar" onSubmit={(event) => { event.preventDefault(); onApply(); }}>
        <Input
          value={filters.search}
          onChange={(event) => update('search', event.target.value)}
          placeholder="Search by ID, title, partner, client..."
          aria-label="Search tickets"
        />
      </Form>
      <Form className={`tm-ticket-filters-panel${hasQueueFilter ? ' tm-ticket-filters-panel-with-queue' : ''}`}>
        <FormGroup>
          <Label>Status</Label>
          <Input type="select" value={filters.status} onChange={(event) => updateAndApply('status', event.target.value)}>
            <option value="">All</option>
            {statuses.map((status) => <option key={status} value={status}>{labelValue(status)}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Priority</Label>
          <Input type="select" value={filters.priority} onChange={(event) => updateAndApply('priority', event.target.value)}>
            <option value="">All</option>
            {priorities.map((priority) => <option key={priority} value={priority}>{labelValue(priority)}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Type</Label>
          <Input type="select" value={filters.type} onChange={(event) => updateAndApply('type', event.target.value)}>
            <option value="">All</option>
            {ticketTypes.map((ticketType) => <option key={ticketType} value={ticketType}>{labelValue(ticketType)}</option>)}
          </Input>
        </FormGroup>
        {hasQueueFilter && (
          <FormGroup>
            <Label>Queue</Label>
            <Input type="select" value={filters.resolver_team} onChange={(event) => updateAndApply('resolver_team', event.target.value)}>
              <option value="">All</option>
              {resolverTeams.map((team) => <option key={team}>{team}</option>)}
            </Input>
          </FormGroup>
        )}
        <div className="tm-ticket-filters-actions">
          <Label className="tm-ticket-filters-reset-spacer" aria-hidden="true">&nbsp;</Label>
          <Button className="tm-ticket-filters-reset-btn" color="secondary" outline type="button" onClick={onReset}>
            Reset filters
          </Button>
        </div>
      </Form>
    </>
  );
}

function TicketTable({ tickets, sortConfig, onSortChange }) {
  const sortHeaders = [
    { key: 'title', label: 'Title' },
    { key: 'status', label: 'Status' },
    { key: 'priority', label: 'Priority' },
    { key: 'partner', label: 'Partner' },
    { key: 'client', label: 'Client' },
    { key: 'updated', label: 'Updated', align: 'end' }
  ];

  return (
    <div className="tm-table-wrap tm-tickets-table-wrap">
      <Table hover responsive className="tm-table tm-tickets-table">
        <thead>
          <tr>
            {sortHeaders.map((header) => {
              const isActive = sortConfig.key === header.key;
              const direction = isActive ? sortConfig.direction : null;
              const ariaSort = isActive
                ? (direction === 'asc' ? 'ascending' : 'descending')
                : 'none';
              return (
                <th key={header.key} className={header.align === 'end' ? 'text-end' : undefined} aria-sort={ariaSort}>
                  <button
                    type="button"
                    className={`tm-sort-button${isActive ? ' is-active' : ''}${header.align === 'end' ? ' is-end' : ''}`}
                    onClick={() => onSortChange(header.key)}
                    aria-label={`Sort by ${header.label}${isActive ? ` (${direction})` : ''}`}
                  >
                    <span>{header.label}</span>
                    <span className="tm-sort-indicator" aria-hidden="true">
                      {isActive ? (direction === 'asc' ? '↑' : '↓') : '↕'}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr key={ticket.id}>
              <td className="tm-row-title">
                <Link className="tm-row-title-link" to={`/tickets/${ticket.id}`}>
                  {ticket.title}
                </Link>
                <div className="tm-ticket-meta">
                  <span>#{ticket.id.slice(0, 8)}</span>
                  <span>{labelValue(ticket.type)}</span>
                  <span>{ticket.resolver_team || 'Unassigned'}</span>
                  <span>GitLab: {ticket.gitlab_status || 'none'}</span>
                </div>
              </td>
              <td><StatusPill value={ticket.status} /></td>
              <td><StatusPill value={ticket.priority} priority={ticket.priority} /></td>
              <td className="tm-quiet-cell">{ticket.partner_name || '-'}</td>
              <td className="tm-quiet-cell">
                <span className="tm-row-client" title={ticket.client_name || '-'}>
                  {ticket.client_name || '-'}
                </span>
              </td>
              <td className="text-end tm-quiet-cell"><TimeCell value={ticket.updated_at} /></td>
            </tr>
          ))}
          {tickets.length === 0 && (
            <EmptyRow colSpan="6" title="No tickets found" message="Try updating filters or create a new ticket." />
          )}
        </tbody>
      </Table>
    </div>
  );
}

function buildRankMap(values) {
  const map = new Map();
  values.forEach((value, index) => {
    if (!map.has(value)) map.set(value, index);
  });
  return map;
}

function parseTimestamp(value) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function normalizeText(value) {
  return String(value || '').trim();
}

function isEmpty(value) {
  return value === null || value === undefined || value === '';
}

function compareNullable(left, right, direction, compare) {
  const leftEmpty = isEmpty(left);
  const rightEmpty = isEmpty(right);
  if (leftEmpty && rightEmpty) return 0;
  if (leftEmpty) return 1;
  if (rightEmpty) return -1;
  return compare(left, right) * direction;
}

function compareText(left, right) {
  return left.localeCompare(right, undefined, { sensitivity: 'base', numeric: true });
}

function compareByRankWithFallback(left, right, rankMap) {
  const leftRank = rankMap.get(left) ?? Number.MAX_SAFE_INTEGER;
  const rightRank = rankMap.get(right) ?? Number.MAX_SAFE_INTEGER;
  if (leftRank !== rightRank) return leftRank - rightRank;
  return compareText(left, right);
}

function compareTickets(left, right, sortConfig, statusRank) {
  const direction = sortConfig.direction === 'asc' ? 1 : -1;
  switch (sortConfig.key) {
    case 'title':
      return compareNullable(normalizeText(left.title), normalizeText(right.title), direction, compareText);
    case 'status':
      return compareNullable(
        normalizeText(left.status),
        normalizeText(right.status),
        direction,
        (a, b) => compareByRankWithFallback(a, b, statusRank)
      );
    case 'priority':
      return compareNullable(
        normalizeText(left.priority),
        normalizeText(right.priority),
        direction,
        (a, b) => compareByRankWithFallback(a, b, PRIORITY_RANK)
      );
    case 'partner':
      return compareNullable(normalizeText(left.partner_name), normalizeText(right.partner_name), direction, compareText);
    case 'client':
      return compareNullable(normalizeText(left.client_name), normalizeText(right.client_name), direction, compareText);
    case 'updated':
    default:
      return compareNullable(parseTimestamp(left.updated_at), parseTimestamp(right.updated_at), direction, (a, b) => a - b);
  }
}

function sortTickets(rows, sortConfig, statusRank) {
  return rows
    .map((ticket, index) => ({ ticket, index }))
    .sort((left, right) => {
      const compared = compareTickets(left.ticket, right.ticket, sortConfig, statusRank);
      if (compared !== 0) return compared;
      return left.index - right.index;
    })
    .map(({ ticket }) => ticket);
}

export function PartnerTicketForm({ meta, clients, onCreated, onCancel = () => {} }) {
  const [form, setForm] = useState({ type: 'Question', priority: 'Normal', title: '', description: '', client_id: '' });
  const [attachments, setAttachments] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const update = (key, value) => setForm({ ...form, [key]: value });
  const submit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setError('');
    setSubmitting(true);
    try {
      const ticketResponse = await api.post('/tickets', { ...form, client_id: form.client_id || null });
      const failedUploads = await uploadTicketAttachments(ticketResponse.data.id, attachments);
      setForm((current) => ({ ...current, title: '', description: '' }));
      setAttachments([]);
      onCreated(ticketResponse.data, failedUploads);
    } catch (err) {
      setError(apiError(err));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Form className="tm-ticket-create-form" onSubmit={submit}>
      <ErrorBanner error={error} />
      <TicketFormFields
        form={form}
        update={update}
        meta={meta}
        clients={clients}
        attachments={attachments}
        setAttachments={setAttachments}
        editorDisabled={submitting}
      />
      <div className="tm-form-actions tm-form-actions-split">
        <Button color="secondary" outline type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button color="primary" type="submit" disabled={submitting || !form.title.trim() || !form.description.trim()}>
          {submitting ? 'Creating ticket...' : 'Create ticket'}
        </Button>
      </div>
    </Form>
  );
}

export function InternalTicketForm({ meta, onCreated, onCancel = () => {} }) {
  const [form, setForm] = useState({ type: 'Operational Request', priority: 'Normal', title: '', description: '', team: '' });
  const [attachments, setAttachments] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const update = (key, value) => setForm({ ...form, [key]: value });
  const resolverTeams = asArray(meta?.resolver_teams);
  const submit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setError('');
    setSubmitting(true);
    try {
      const ticketResponse = await api.post('/tickets/internal', { ...form, team: form.team || null });
      const failedUploads = await uploadTicketAttachments(ticketResponse.data.id, attachments);
      setForm((current) => ({ ...current, title: '', description: '' }));
      setAttachments([]);
      onCreated(ticketResponse.data, failedUploads);
    } catch (err) {
      setError(apiError(err));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Form className="tm-ticket-create-form" onSubmit={submit}>
      <ErrorBanner error={error} />
      <TicketFormFields
        form={form}
        update={update}
        meta={meta}
        attachments={attachments}
        setAttachments={setAttachments}
        editorDisabled={submitting}
      />
      <div className="tm-ticket-form-grid tm-ticket-form-grid-extra">
        <FormGroup>
          <Label>Team</Label>
          <Input type="select" value={form.team} onChange={(event) => update('team', event.target.value)}>
            <option value="">Unassigned</option>
            {resolverTeams.map((team) => <option key={team}>{team}</option>)}
          </Input>
        </FormGroup>
      </div>
      <div className="tm-form-actions tm-form-actions-split">
        <Button color="secondary" outline type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button color="primary" type="submit" disabled={submitting || !form.title.trim() || !form.description.trim()}>
          {submitting ? 'Creating ticket...' : 'Create ticket'}
        </Button>
      </div>
    </Form>
  );
}

export function PartnerOnBehalfTicketForm({ meta, partners, clients, users, onCreated, onCancel = () => {} }) {
  const [form, setForm] = useState({
    partner_id: '',
    owner_id: '',
    type: 'Question',
    priority: 'Normal',
    title: '',
    description: '',
    client_id: '',
    participant_ids: []
  });
  const [attachments, setAttachments] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const update = (key, value) => setForm({ ...form, [key]: value });
  const updatePartner = (partnerId) => setForm({
    ...form,
    partner_id: partnerId,
    owner_id: '',
    client_id: '',
    participant_ids: []
  });
  const partnerRows = asArray(partners);
  const clientRows = asArray(clients).filter((client) => client.partner_id === form.partner_id);
  const partnerUsers = asArray(users).filter((row) => row.kind === 'partner' && row.active && row.partner_id === form.partner_id);
  const owners = partnerUsers.filter((row) => row.partner_role === 'responsible');
  const participantOptions = partnerUsers.filter((row) => row.id !== form.owner_id);
  const submit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setError('');
    setSubmitting(true);
    try {
      const ticketResponse = await api.post('/tickets/on-behalf', {
        ...form,
        client_id: form.client_id || null,
        participant_ids: form.participant_ids
      });
      const failedUploads = await uploadTicketAttachments(ticketResponse.data.id, attachments);
      setForm((current) => ({ ...current, title: '', description: '', participant_ids: [] }));
      setAttachments([]);
      onCreated(ticketResponse.data, failedUploads);
    } catch (err) {
      setError(apiError(err));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Form className="tm-ticket-create-form" onSubmit={submit}>
      <ErrorBanner error={error} />
      <div className="tm-ticket-form-grid">
        <FormGroup>
          <Label>Partner</Label>
          <Input type="select" value={form.partner_id} onChange={(event) => updatePartner(event.target.value)} required>
            <option value="">Select partner</option>
            {partnerRows.map((partner) => <option key={partner.id} value={partner.id}>{partner.name}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Owner</Label>
          <Input type="select" value={form.owner_id} onChange={(event) => update('owner_id', event.target.value)} required disabled={!form.partner_id}>
            <option value="">Select responsible user</option>
            {owners.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Participants</Label>
          <Input
            className="tm-multi-select"
            type="select"
            multiple
            value={form.participant_ids}
            disabled={!form.partner_id}
            onChange={(event) => update('participant_ids', Array.from(event.target.selectedOptions).map((option) => option.value))}
          >
            {participantOptions.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </Input>
        </FormGroup>
      </div>
      <TicketFormFields
        form={form}
        update={update}
        meta={meta}
        clients={clientRows}
        attachments={attachments}
        setAttachments={setAttachments}
        editorDisabled={submitting}
      />
      <div className="tm-form-actions tm-form-actions-split">
        <Button color="secondary" outline type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          color="primary"
          type="submit"
          disabled={submitting || !form.partner_id || !form.owner_id || !form.title.trim() || !form.description.trim()}
        >
          {submitting ? 'Creating ticket...' : 'Create for partner'}
        </Button>
      </div>
    </Form>
  );
}

export function TicketFormFields({
  form,
  update,
  meta,
  clients = [],
  attachments = [],
  setAttachments = () => {},
  editorDisabled = false
}) {
  const descriptionRef = useRef(null);
  const uploadInputRef = useRef(null);
  const [attachmentError, setAttachmentError] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const ticketTypes = asArray(meta?.ticket_types);
  const priorities = asArray(meta?.priorities);
  const clientRows = asArray(clients);

  const setDescriptionWithSelection = (nextValue, selectionStart, selectionEnd) => {
    update('description', nextValue);
    requestAnimationFrame(() => {
      const input = descriptionRef.current;
      if (!input) return;
      input.focus();
      if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
        input.setSelectionRange(selectionStart, selectionEnd);
      }
    });
  };

  const insertWrapped = (prefix, suffix = '', placeholder = '') => {
    const input = descriptionRef.current;
    const currentValue = form.description || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const selectedText = currentValue.slice(selectionStart, selectionEnd);
    const body = selectedText || placeholder;
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefix}${body}${suffix}${currentValue.slice(selectionEnd)}`;
    const cursorStart = selectionStart + prefix.length;
    const cursorEnd = cursorStart + body.length;
    setDescriptionWithSelection(nextValue, cursorStart, cursorEnd);
  };

  const insertAtCursor = (text) => {
    const input = descriptionRef.current;
    const currentValue = form.description || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const nextValue = `${currentValue.slice(0, selectionStart)}${text}${currentValue.slice(selectionEnd)}`;
    const cursor = selectionStart + text.length;
    setDescriptionWithSelection(nextValue, cursor, cursor);
  };

  const prefixSelectedLines = (prefix) => {
    const input = descriptionRef.current;
    const currentValue = form.description || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    if (selectionStart === selectionEnd) {
      insertAtCursor(prefix);
      return;
    }
    const selected = currentValue.slice(selectionStart, selectionEnd);
    const prefixed = selected.split('\n').map((line) => (line ? `${prefix}${line}` : prefix.trimEnd())).join('\n');
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefixed}${currentValue.slice(selectionEnd)}`;
    setDescriptionWithSelection(nextValue, selectionStart, selectionStart + prefixed.length);
  };

  const pickFiles = () => uploadInputRef.current?.click();

  const handleFileSelection = (event) => {
    const pickedFiles = Array.from(event.target.files || []);
    if (pickedFiles.length === 0) return;
    const validFiles = [];
    const rejectedNames = [];
    for (const file of pickedFiles) {
      const extension = `.${(file.name.split('.').pop() || '').toLowerCase()}`;
      if (!ALLOWED_ATTACHMENT_EXTENSIONS.has(extension)) {
        rejectedNames.push(file.name);
        continue;
      }
      if (file.size > MAX_ATTACHMENT_BYTES) {
        rejectedNames.push(file.name);
        continue;
      }
      validFiles.push(file);
    }
    if (validFiles.length > 0) {
      setAttachments((current) => {
        const rows = Array.isArray(current) ? current : [];
        const byKey = new Map(rows.map((file) => [`${file.name}:${file.size}:${file.lastModified}`, file]));
        for (const file of validFiles) {
          byKey.set(`${file.name}:${file.size}:${file.lastModified}`, file);
        }
        return Array.from(byKey.values());
      });
    }
    if (rejectedNames.length > 0) {
      setAttachmentError(`Some files could not be added (unsupported type or size above 25 MB): ${rejectedNames.join(', ')}`);
    } else {
      setAttachmentError('');
    }
    event.target.value = '';
  };

  return (
    <div className="tm-ticket-form-grid">
      <FormGroup>
        <Label>Type</Label>
        <Input type="select" value={form.type} onChange={(event) => update('type', event.target.value)}>
          {ticketTypes.map((ticketType) => <option key={ticketType}>{ticketType}</option>)}
        </Input>
      </FormGroup>
      <FormGroup>
        <Label>Priority</Label>
        <Input type="select" value={form.priority} onChange={(event) => update('priority', event.target.value)}>
          {priorities.map((priority) => <option key={priority}>{priority}</option>)}
        </Input>
      </FormGroup>
      {clientRows.length > 0 && (
        <FormGroup>
          <Label>Client</Label>
          <Input type="select" value={form.client_id} onChange={(event) => update('client_id', event.target.value)}>
            <option value="">No client</option>
            {clientRows.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
          </Input>
        </FormGroup>
      )}
      <FormGroup className="tm-field-wide">
        <Label>Title</Label>
        <Input value={form.title} onChange={(event) => update('title', event.target.value)} required />
      </FormGroup>
      <FormGroup className="tm-field-wide">
        <Label>Description</Label>
        <div className="tm-md-editor">
          <div className="tm-md-editor-toolbar" role="toolbar" aria-label="Markdown toolbar">
            <Button
              type="button"
              color="secondary"
              outline
              size="sm"
              className="tm-md-toolbar-btn"
              title="Bold"
              aria-label="Bold"
              onClick={() => insertWrapped('**', '**', 'bold text')}
              disabled={editorDisabled}
            >
              <i className="bi bi-type-bold" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              color="secondary"
              outline
              size="sm"
              className="tm-md-toolbar-btn"
              title="Italic"
              aria-label="Italic"
              onClick={() => insertWrapped('_', '_', 'italic text')}
              disabled={editorDisabled}
            >
              <i className="bi bi-type-italic" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              color="secondary"
              outline
              size="sm"
              className="tm-md-toolbar-btn"
              title="Heading"
              aria-label="Heading"
              onClick={() => insertAtCursor('## ')}
              disabled={editorDisabled}
            >
              <i className="bi bi-type-h2" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              color="secondary"
              outline
              size="sm"
              className="tm-md-toolbar-btn"
              title="Quote"
              aria-label="Quote"
              onClick={() => prefixSelectedLines('> ')}
              disabled={editorDisabled}
            >
              <i className="bi bi-chat-square-quote" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              color="secondary"
              outline
              size="sm"
              className="tm-md-toolbar-btn"
              title="Bulleted list"
              aria-label="Bulleted list"
              onClick={() => prefixSelectedLines('- ')}
              disabled={editorDisabled}
            >
              <i className="bi bi-list-ul" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              color="secondary"
              outline
              size="sm"
              className="tm-md-toolbar-btn"
              title="Numbered list"
              aria-label="Numbered list"
              onClick={() => prefixSelectedLines('1. ')}
              disabled={editorDisabled}
            >
              <i className="bi bi-list-ol" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              color="secondary"
              outline
              size="sm"
              className="tm-md-toolbar-btn"
              title="Link"
              aria-label="Link"
              onClick={() => insertWrapped('[', '](https://)', 'link text')}
              disabled={editorDisabled}
            >
              <i className="bi bi-link-45deg" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              color="secondary"
              outline
              size="sm"
              className="tm-md-toolbar-btn"
              title="Code block"
              aria-label="Code block"
              onClick={() => insertWrapped('```\n', '\n```', 'code')}
              disabled={editorDisabled}
            >
              <i className="bi bi-code-slash" aria-hidden="true" />
            </Button>
            <span className="tm-md-editor-separator" />
            <Button
              type="button"
              color="secondary"
              outline
              size="sm"
              className="tm-md-toolbar-btn"
              title="Attach files"
              aria-label="Attach files"
              onClick={pickFiles}
              disabled={editorDisabled}
            >
              <i className="bi bi-paperclip" aria-hidden="true" />
            </Button>
            <Input
              innerRef={uploadInputRef}
              type="file"
              className="d-none"
              multiple
              accept={ATTACHMENT_ACCEPT}
              onChange={handleFileSelection}
            />
          </div>
          <Input
            innerRef={descriptionRef}
            type="textarea"
            rows="6"
            value={form.description}
            onChange={(event) => update('description', event.target.value)}
            required
            disabled={editorDisabled}
          />
        </div>
        <div className="tm-muted tm-field-help">Markdown supported (headings, lists, links, bold, code).</div>
        {attachments.length > 0 && (
          <div className="tm-draft-attachments">
            <div className="tm-draft-attachments-head">Attachments ({attachments.length})</div>
            <div className="tm-draft-attachments-list">
              {attachments.map((file, index) => (
                <span className="tm-draft-attachment" key={`${file.name}:${file.size}:${file.lastModified}`}>
                  <span className="tm-draft-attachment-name" title={file.name}>{file.name}</span>
                  <span className="tm-muted">{formatAttachmentSize(file.size)}</span>
                  <button
                    type="button"
                    className="tm-draft-attachment-remove"
                    aria-label={`Remove ${file.name}`}
                    onClick={() => setAttachments((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                    disabled={editorDisabled}
                  >
                    x
                  </button>
                </span>
              ))}
            </div>
            <div className="tm-muted tm-field-help">Attachments will upload automatically right after ticket creation.</div>
          </div>
        )}
        {attachmentError && <div className="text-danger small">{attachmentError}</div>}
        <Button color="secondary" outline size="sm" type="button" className="mt-2" onClick={() => setShowPreview(!showPreview)}>
          {showPreview ? 'Hide preview' : 'Show preview'}
        </Button>
        {showPreview && (
          <div className="tm-markdown-preview">
            <div className="tm-markdown-preview-head">Markdown preview</div>
            <MarkdownText
              content={form.description}
              className="tm-markdown tm-markdown-preview-body"
              emptyMessage="Preview appears when description is filled."
            />
          </div>
        )}
      </FormGroup>
    </div>
  );
}
