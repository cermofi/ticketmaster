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
import { usePolling, useRefetchOnFocus, useRefetchOnSessionChange } from '../hooks/useLiveRefresh.js';
import { useUrlFilters } from '../hooks/useUrlFilters.js';
import { EmptyRow, ErrorBanner, Loading, PageHeader, StatusPill, TimeCell, apiError, asArray, downloadResponse, exportError, labelValue } from './helpers.jsx';

const EMPTY_FILTERS = { search: '', status: '', priority: '', type: '', resolver_team: '', internal: '' };
const FILTER_KEYS = Object.keys(EMPTY_FILTERS);
const TICKETS_POLL_MS = 30000;
const SEARCH_DEBOUNCE_MS = 320;
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
  const { filters, syncFiltersToUrl, resetFilters: resetUrlFilters } = useUrlFilters(EMPTY_FILTERS, FILTER_KEYS);
  const [sortConfig, setSortConfig] = useState(DEFAULT_SORT);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [moreOpen, setMoreOpen] = useState(false);
  const [exportLoading, setExportLoading] = useState('');
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const setFilters = useCallback((next) => {
    const merged = typeof next === 'function' ? next(filtersRef.current) : next;
    syncFiltersToUrl(merged);
  }, [syncFiltersToUrl]);

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

  const exportTickets = async () => {
    setError('');
    setExportLoading('xlsx');
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''));
      const response = await api.get('/tickets/export', { params: { ...params, format: 'xlsx' }, responseType: 'blob' });
      downloadResponse(response, 'ticketmaster_export.xlsx');
    } catch (err) {
      setError(await exportError(err));
    } finally {
      setExportLoading('');
    }
  };

  const filtersKey = useMemo(() => JSON.stringify(filters), [filters]);

  useEffect(() => {
    const delay = filters.search ? SEARCH_DEBOUNCE_MS : 0;
    const timeout = window.setTimeout(() => {
      load(filters);
    }, delay);
    return () => window.clearTimeout(timeout);
  }, [filtersKey, load, filters.search]);

  useRefetchOnFocus(load);
  useRefetchOnSessionChange(load);
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

  return (
    <div className="tm-screen tm-tickets-screen">
      <PageHeader
        title="Tickets"
        actions={(
          <>
            {user.kind === 'internal' ? (
              <>
                <Button color="primary" tag={Link} to="/tickets/new">
                  Create ticket
                </Button>
                <Button color="secondary" outline tag={Link} to="/tickets/new?target=partner">
                  To partner
                </Button>
              </>
            ) : (
              <Button color="primary" tag={Link} to="/tickets/new">
                Create ticket
              </Button>
            )}
            <MoreActionsMenu
              isOpen={moreOpen}
              setOpen={setMoreOpen}
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
              const cleared = resetUrlFilters();
              load(cleared);
            }}
          />
          <TicketTable tickets={sortedTickets} sortConfig={sortConfig} onSortChange={onSortChange} />
        </>
      )}
    </div>
  );
}

function MoreActionsMenu({ isOpen, setOpen, loading, onExport }) {
  return (
    <ButtonDropdown isOpen={isOpen} toggle={() => setOpen(!isOpen)}>
      <DropdownToggle color="secondary" outline caret>
        More
      </DropdownToggle>
      <DropdownMenu end>
        <DropdownItem disabled={Boolean(loading)} onClick={() => onExport()}>
          {loading ? 'Exporting Excel...' : 'Export tickets (Excel)'}
        </DropdownItem>
      </DropdownMenu>
    </ButtonDropdown>
  );
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
        <FormGroup className="tm-ticket-filters-actions">
          <Label className="tm-ticket-filters-reset-spacer" aria-hidden="true">&nbsp;</Label>
          <button className="tm-ticket-filters-reset-btn form-control" type="button" onClick={onReset}>
            Reset filters
          </button>
        </FormGroup>
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
    { key: 'assignee', label: 'Asignee' },
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
              <td className="tm-quiet-cell">{ticket.assignee_name || '-'}</td>
              <td className="text-end tm-quiet-cell"><TimeCell value={ticket.updated_at} /></td>
            </tr>
          ))}
          {tickets.length === 0 && (
            <EmptyRow colSpan="7" title="No tickets found" message="Try updating filters or create a new ticket." />
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
    case 'assignee':
      return compareNullable(normalizeText(left.assignee_name), normalizeText(right.assignee_name), direction, compareText);
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
