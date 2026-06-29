import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Form,
  FormGroup,
  Input,
  Label,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Table
} from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { usePolling, useRefetchOnFocus, useSessionDomainRefresh, DATA_DOMAINS } from '../hooks/useLiveRefresh.js';
import { useUrlFilters } from '../hooks/useUrlFilters.js';
import {
  asArray,
  downloadResponse,
  EmptyRow,
  ErrorBanner,
  exportError,
  Loading,
  PageHeader,
  StatusPill,
  TimeCell,
  apiError,
  hasAnyInternalRole
} from './helpers.jsx';

const DEFAULT_SORT = { sort_by: 'last_gitlab_update', sort_direction: 'desc' };
const EMPTY_FILTERS = {
  search: '',
  target_team: '',
  state: '',
  assignee: '',
  label: '',
  updated_since: '',
  sort_by: DEFAULT_SORT.sort_by,
  sort_direction: DEFAULT_SORT.sort_direction
};
const FILTER_KEYS = Object.keys(EMPTY_FILTERS);
const POLL_MS = 60000;

export default function GitLabDeliveryTrackingScreen() {
  return (
    <AuthGate>
      {(user) => <TrackingDashboard user={user} />}
    </AuthGate>
  );
}

function TrackingDashboard({ user }) {
  const canView = user?.kind === 'internal';
  const canManage = canView && hasAnyInternalRole(user, ['Admin', 'DeliveryManager']);
  const { filters, syncFiltersToUrl, resetFilters: resetUrlFilters } = useUrlFilters(
    EMPTY_FILTERS,
    FILTER_KEYS
  );
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const [meta, setMeta] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [syncLoading, setSyncLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [mappingModalOpen, setMappingModalOpen] = useState(false);
  const [mappingTargetUrl, setMappingTargetUrl] = useState('');
  const [mappingError, setMappingError] = useState('');
  const [mappingSaving, setMappingSaving] = useState(false);
  const [mappingRow, setMappingRow] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailRow, setDetailRow] = useState(null);
  const [alertsModalOpen, setAlertsModalOpen] = useState(false);
  const [alertsRows, setAlertsRows] = useState([]);
  const [alertsUnreadCount, setAlertsUnreadCount] = useState(0);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [alertsActionLoading, setAlertsActionLoading] = useState(false);
  const [alertsError, setAlertsError] = useState('');

  const setFilters = useCallback((next) => {
    const merged = typeof next === 'function' ? next(filtersRef.current) : next;
    syncFiltersToUrl(merged);
  }, [syncFiltersToUrl]);

  const loadAlerts = useCallback(async ({ silent = false } = {}) => {
    if (!canView) return;
    if (!silent) setAlertsLoading(true);
    setAlertsError('');
    try {
      const response = await api.get('/gitlab/delivery-tracking/alerts', {
        params: { limit: 30, offset: 0 }
      });
      setAlertsRows(asArray(response.data));
      setAlertsUnreadCount(Number(response.data?.unread_count || 0));
    } catch (err) {
      setAlertsError(apiError(err));
    } finally {
      if (!silent) setAlertsLoading(false);
    }
  }, [canView]);

  const load = useCallback(async (nextFilters) => {
    if (!canView) return;
    const activeFilters = nextFilters ?? filtersRef.current;
    setError('');
    setLoading(true);
    try {
      const params = buildRequestParams(activeFilters);
      const [metaResponse, listResponse] = await Promise.all([
        api.get('/gitlab/delivery-tracking/meta'),
        api.get('/gitlab/delivery-tracking', { params })
      ]);
      setMeta(metaResponse.data);
      setRows(asArray(listResponse.data));
      await loadAlerts({ silent: true });
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  }, [canView, loadAlerts]);

  const filtersKey = useMemo(() => JSON.stringify(filters), [filters]);

  useEffect(() => {
    load(filters);
  }, [filtersKey, load]);

  useRefetchOnFocus(load, canView);
  useSessionDomainRefresh(DATA_DOMAINS.gitlabDeliveryTracking, load, canView);
  usePolling(load, POLL_MS, canView);

  const triggerSync = async () => {
    if (!canManage) return;
    setError('');
    setSyncLoading(true);
    try {
      await api.post('/gitlab/delivery-tracking/sync');
      await load();
    } catch (err) {
      setError(apiError(err));
    } finally {
      setSyncLoading(false);
    }
  };

  const exportDashboard = async () => {
    setError('');
    setExportLoading(true);
    try {
      const params = buildRequestParams(filtersRef.current);
      const response = await api.get('/gitlab/delivery-tracking/export', {
        params,
        responseType: 'blob'
      });
      downloadResponse(response, 'delivery_tracking.xlsx');
    } catch (err) {
      setError(await exportError(err));
    } finally {
      setExportLoading(false);
    }
  };

  const onSortChange = (key) => {
    const isSame = filtersRef.current.sort_by === key;
    const nextDirection = isSame && filtersRef.current.sort_direction === 'asc' ? 'desc' : 'asc';
    const nextFilters = {
      ...filtersRef.current,
      sort_by: key,
      sort_direction: nextDirection
    };
    setFilters(nextFilters);
  };

  const openMappingDialog = (row) => {
    setMappingRow(row);
    setMappingTargetUrl(row.target_url || '');
    setMappingError('');
    setMappingModalOpen(true);
  };

  const openDetailDialog = (row) => {
    setDetailRow(row);
    setDetailModalOpen(true);
  };

  const openAlertsDialog = () => {
    setAlertsModalOpen(true);
    loadAlerts();
  };

  const closeAlertsDialog = () => {
    if (alertsActionLoading) return;
    setAlertsModalOpen(false);
  };

  const markAllAlertsRead = async () => {
    setAlertsError('');
    setAlertsActionLoading(true);
    try {
      await api.post('/gitlab/delivery-tracking/alerts/read-all');
      await loadAlerts({ silent: true });
    } catch (err) {
      setAlertsError(apiError(err));
    } finally {
      setAlertsActionLoading(false);
    }
  };

  const openAlertIssue = (alert) => {
    const matched = rows.find(
      (row) => row.id === alert.tracked_issue_id || row.delivery_issue_iid === alert.delivery_issue_iid
    );
    if (matched) {
      closeAlertsDialog();
      openDetailDialog(matched);
      return;
    }
    if (alert.delivery_url) {
      window.open(alert.delivery_url, '_blank', 'noopener,noreferrer');
    }
  };

  const closeDetailDialog = () => {
    setDetailModalOpen(false);
    setDetailRow(null);
  };

  const closeMappingDialog = () => {
    if (mappingSaving) return;
    setMappingModalOpen(false);
    setMappingRow(null);
    setMappingTargetUrl('');
    setMappingError('');
  };

  const saveManualMapping = async () => {
    if (!mappingRow) return;
    setMappingError('');
    setMappingSaving(true);
    try {
      await api.post(`/gitlab/delivery-tracking/${mappingRow.id}/manual-mapping`, {
        target_url: mappingTargetUrl
      });
      setMappingModalOpen(false);
      setMappingRow(null);
      setMappingTargetUrl('');
      await load();
    } catch (err) {
      setMappingError(apiError(err));
    } finally {
      setMappingSaving(false);
    }
  };

  if (!canView) {
    return (
      <div className="tm-screen">
        <PageHeader title="Tickets" />
        <ErrorBanner error="Tickets are available only to internal users." />
      </div>
    );
  }

  return (
    <div className="tm-screen">
      <PageHeader
        title="Tickets"
        actions={(
          <div className="d-flex gap-2">
            <Button
              color="secondary"
              outline
              className="tm-delivery-alert-bell"
              onClick={openAlertsDialog}
              aria-label="Open ticket alerts"
              title="Ticket alerts"
            >
              <i className="bi bi-bell" aria-hidden="true" />
              {alertsUnreadCount > 0 && (
                <span className="tm-delivery-alert-badge">{formatAlertUnreadCount(alertsUnreadCount)}</span>
              )}
            </Button>
            {canManage && (
              <Button color="primary" onClick={triggerSync} disabled={syncLoading}>
                {syncLoading ? 'Sync in progress...' : 'Sync now'}
              </Button>
            )}
            <Button color="secondary" outline onClick={exportDashboard} disabled={exportLoading}>
              {exportLoading ? 'Exporting...' : 'Export Excel'}
            </Button>
          </div>
        )}
      >
        {meta?.last_sync_run?.finished_at ? `Last sync: ${new Date(meta.last_sync_run.finished_at).toLocaleString()}` : 'No sync run yet'}
      </PageHeader>
      <ErrorBanner error={error} />
      {loading && !meta ? <Loading /> : (
        <>
          <TrackingFilters
            filters={filters}
            setFilters={setFilters}
            teams={asArray(meta?.target_teams)}
            states={asArray(meta?.states)}
            assignees={asArray(meta?.assignees)}
            labels={asArray(meta?.labels)}
            onApply={load}
            onReset={() => {
              const reset = resetUrlFilters();
              load(reset);
            }}
          />
          <TrackingTable
            rows={rows}
            sortBy={filters.sort_by}
            sortDirection={filters.sort_direction}
            onSortChange={onSortChange}
            onOpenDetails={openDetailDialog}
          />
        </>
      )}
      <TrackingDetailsModal
        isOpen={detailModalOpen}
        row={detailRow}
        canManage={canManage}
        onClose={closeDetailDialog}
        onManualMapping={(row) => {
          if (!row) return;
          closeDetailDialog();
          openMappingDialog(row);
        }}
      />
      <DeliveryAlertsModal
        isOpen={alertsModalOpen}
        alerts={alertsRows}
        loading={alertsLoading}
        actionLoading={alertsActionLoading}
        unreadCount={alertsUnreadCount}
        error={alertsError}
        onClose={closeAlertsDialog}
        onRefresh={() => loadAlerts()}
        onMarkAllRead={markAllAlertsRead}
        onOpenAlert={openAlertIssue}
      />
      <Modal isOpen={mappingModalOpen} toggle={closeMappingDialog}>
        <ModalHeader toggle={closeMappingDialog}>Manual issue mapping</ModalHeader>
        <ModalBody>
          <ErrorBanner error={mappingError} />
          <p className="tm-muted">
            Paste target GitLab issue URL (for example:
            {' '}
            <code>https://gitlab.example.com/group/project/-/issues/123</code>
            ).
          </p>
          <FormGroup>
            <Label for="manual-mapping-url">Target issue URL</Label>
            <Input
              id="manual-mapping-url"
              value={mappingTargetUrl}
              onChange={(event) => setMappingTargetUrl(event.target.value)}
              placeholder="https://gitlab.example.com/group/project/-/issues/123"
            />
          </FormGroup>
        </ModalBody>
        <ModalFooter>
          <Button outline color="secondary" onClick={closeMappingDialog} disabled={mappingSaving}>
            Cancel
          </Button>
          <Button color="primary" onClick={saveManualMapping} disabled={!mappingTargetUrl.trim() || mappingSaving}>
            {mappingSaving ? 'Saving...' : 'Save mapping'}
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}

function TrackingFilters({
  filters,
  setFilters,
  teams,
  states,
  assignees,
  labels,
  onApply,
  onReset
}) {
  const update = (key, value) => setFilters({ ...filters, [key]: value });

  return (
    <Form className="tm-delivery-filters-panel" onSubmit={(event) => { event.preventDefault(); onApply(); }}>
      <div className="tm-delivery-filters-head">
        <h6>Filters</h6>
        <span>Refine issues by team, assignee, labels and state.</span>
      </div>
      <div className="tm-delivery-filters-grid">
        <FormGroup className="tm-delivery-filter-search">
          <Label>Search</Label>
          <Input
            value={filters.search}
            placeholder="Search by delivery title or ticket ID"
            onChange={(event) => update('search', event.target.value)}
          />
        </FormGroup>
        <FormGroup>
          <Label>Target team</Label>
          <Input type="select" value={filters.target_team} onChange={(event) => update('target_team', event.target.value)}>
            <option value="">All</option>
            {teams.map((team) => <option key={team.name} value={team.name}>{team.name}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Current state</Label>
          <Input type="select" value={filters.state} onChange={(event) => update('state', event.target.value)}>
            <option value="">All</option>
            {states.map((state) => <option key={state} value={state}>{state}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Asignee</Label>
          <Input type="select" value={filters.assignee} onChange={(event) => update('assignee', event.target.value)}>
            <option value="">All</option>
            {assignees.map((assignee) => <option key={assignee} value={assignee}>{assignee}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Labels</Label>
          <Input type="select" value={filters.label} onChange={(event) => update('label', event.target.value)}>
            <option value="">All</option>
            {labels.map((label) => <option key={label} value={label}>{label}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Updated since</Label>
          <Input type="date" value={filters.updated_since} onChange={(event) => update('updated_since', event.target.value)} />
        </FormGroup>
      </div>
      <div className="tm-delivery-filters-actions">
        <Button size="sm" color="primary" type="submit">Apply filters</Button>
        <Button size="sm" color="secondary" outline type="button" onClick={onReset}>Reset</Button>
      </div>
    </Form>
  );
}

function TrackingTable({ rows, sortBy, sortDirection, onSortChange, onOpenDetails }) {
  const headers = [
    { key: 'last_gitlab_update', label: 'last update' },
    { key: 'ticket_id', label: 'ID' },
    { key: 'delivery_issue', label: 'delivery issue' },
    { key: 'current_state', label: 'Current state' },
    { key: 'target_issue_url', label: 'team id' },
    { key: 'assignee', label: 'Asignee' },
    { key: 'labels', label: 'Labels' }
  ];

  return (
    <div className="tm-table-wrap tm-delivery-table-wrap">
      <Table hover className="tm-table">
        <thead>
          <tr>
            {headers.map((header) => {
              const isActive = sortBy === header.key;
              const direction = isActive ? sortDirection : null;
              const ariaSort = isActive ? (direction === 'asc' ? 'ascending' : 'descending') : 'none';
              return (
                <th key={header.key} aria-sort={ariaSort}>
                  <button
                    type="button"
                    className={`tm-sort-button${isActive ? ' is-active' : ''}`}
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
          {rows.map((row) => {
            const currentState = row.target_state || row.delivery_state;
            const labels = (Array.isArray(row.target_labels) && row.target_labels.length > 0)
              ? row.target_labels
              : row.delivery_labels;
            return (
              <tr key={row.id}>
                <td className="tm-quiet-cell">
                  <TimeCell value={row.target_updated_at || row.delivery_updated_at} />
                </td>
                <td className="tm-quiet-cell">{formatTicketId(row.delivery_issue_iid)}</td>
                <td>
                  <button
                    type="button"
                    className="tm-delivery-drilldown"
                    onClick={() => onOpenDetails(row)}
                  >
                    {row.delivery_title || '-'}
                  </button>
                </td>
                <td>
                  {currentState ? <StatusPill value={currentState} /> : <span className="tm-muted">-</span>}
                </td>
                <td>
                  <ExternalLink href={row.target_url} label={row.target_issue_iid || 'Open'} />
                </td>
                <td className="tm-quiet-cell">{formatAssignees(row.target_assignees)}</td>
                <td className="tm-quiet-cell">{formatLabels(labels)}</td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <EmptyRow
              colSpan="7"
              title="No tracked issues found"
              message="Adjust filters or run a sync to import Delivery issues from GitLab."
            />
          )}
        </tbody>
      </Table>
    </div>
  );
}

function DeliveryAlertsModal({
  isOpen,
  alerts,
  loading,
  actionLoading,
  unreadCount,
  error,
  onClose,
  onRefresh,
  onMarkAllRead,
  onOpenAlert
}) {
  return (
    <Modal isOpen={isOpen} toggle={onClose} size="lg">
      <ModalHeader toggle={onClose}>
        Delivery alerts
      </ModalHeader>
      <ModalBody>
        <ErrorBanner error={error} />
        <div className="tm-delivery-alerts-head">
          <span className="tm-muted">Unread alerts: {unreadCount}</span>
          <div className="d-flex gap-2">
            <Button size="sm" color="secondary" outline onClick={onRefresh} disabled={loading || actionLoading}>
              Refresh
            </Button>
            <Button size="sm" color="primary" outline onClick={onMarkAllRead} disabled={unreadCount === 0 || actionLoading}>
              {actionLoading ? 'Marking...' : 'Mark all read'}
            </Button>
          </div>
        </div>
        <div className="tm-delivery-alert-list">
          {loading && alerts.length === 0 ? (
            <div className="tm-muted">Loading alerts...</div>
          ) : alerts.length === 0 ? (
            <div className="tm-muted">No alerts yet.</div>
          ) : alerts.map((alert) => (
            <button
              key={alert.id}
              type="button"
              className={`tm-delivery-alert-item${alert.is_read ? '' : ' is-unread'}`}
              onClick={() => onOpenAlert(alert)}
            >
              <div className="tm-delivery-alert-title-row">
                <strong>{alert.message || 'Delivery ticket changed'}</strong>
                {!alert.is_read && <span className="tm-delivery-alert-dot" aria-label="Unread alert" />}
              </div>
              <div className="tm-muted">#{alert.delivery_issue_iid} {alert.delivery_title}</div>
              {alert.change_summary ? (
                <div className="tm-delivery-alert-summary">{alert.change_summary}</div>
              ) : null}
              <div className="tm-muted">
                <TimeCell value={alert.created_at} />
              </div>
            </button>
          ))}
        </div>
      </ModalBody>
      <ModalFooter>
        <Button outline color="secondary" onClick={onClose} disabled={actionLoading}>
          Close
        </Button>
      </ModalFooter>
    </Modal>
  );
}

function TrackingDetailsModal({ isOpen, row, canManage, onClose, onManualMapping }) {
  const currentState = row?.target_state || row?.delivery_state;
  const labels = (Array.isArray(row?.target_labels) && row.target_labels.length > 0)
    ? row.target_labels
    : row?.delivery_labels;
  const targetTeam = row?.target_team_name || (row?.sync_status === 'in_delivery' ? 'Delivery' : '-');
  const lastGitlabUpdate = row ? (row.target_updated_at || row.delivery_updated_at) : null;
  const lastSyncedAt = row?.last_synced_at || null;

  return (
    <Modal isOpen={isOpen} toggle={onClose} size="lg">
      <ModalHeader toggle={onClose}>Delivery issue detail</ModalHeader>
      <ModalBody>
        {!row ? null : (
          <div className="row g-3">
            <DetailItem label="Delivery issue">
              <div>{row.delivery_title || '-'}</div>
              <div className="tm-muted">{formatTicketId(row.delivery_issue_iid)}</div>
            </DetailItem>
            <DetailItem label="Delivery URL">
              <ExternalLink href={row.delivery_url} label="Open delivery issue" />
            </DetailItem>
            <DetailItem label="Current state">
              {currentState ? <StatusPill value={currentState} /> : <span className="tm-muted">-</span>}
            </DetailItem>
            <DetailItem label="Target team / project">
              <div>{targetTeam}</div>
              <div className="tm-muted">{row.target_project_name || '-'}</div>
            </DetailItem>
            <DetailItem label="Target issue URL">
              <ExternalLink href={row.target_url} label={row.target_issue_iid ? `#${row.target_issue_iid}` : 'Open target issue'} />
            </DetailItem>
            <DetailItem label="Asignee">
              {formatAssignees(row.target_assignees)}
            </DetailItem>
            <DetailItem label="Labels">
              {formatLabels(labels)}
            </DetailItem>
            <DetailItem label="Sync status">
              <StatusPill value={syncStatusLabel(row.sync_status)} tone={syncStatusTone(row.sync_status)} />
            </DetailItem>
            <DetailItem label="Resolution source">
              <span>{row.resolution_source || '-'}</span>
            </DetailItem>
            <DetailItem label="Last update">
              <TimeCell value={lastGitlabUpdate} />
            </DetailItem>
            <DetailItem label="Last synced at">
              <TimeCell value={lastSyncedAt} />
            </DetailItem>
            {row.sync_error && (
              <div className="col-12">
                <div className="tm-muted mb-1">Sync error</div>
                <div>{row.sync_error}</div>
              </div>
            )}
          </div>
        )}
      </ModalBody>
      <ModalFooter>
        {canManage && row?.target_missing && (
          <Button color="secondary" outline onClick={() => onManualMapping(row)}>
            Map manually
          </Button>
        )}
        <Button outline color="secondary" onClick={onClose}>
          Close
        </Button>
      </ModalFooter>
    </Modal>
  );
}

function DetailItem({ label, children }) {
  return (
    <div className="col-12 col-md-6">
      <div className="tm-muted mb-1">{label}</div>
      <div>{children}</div>
    </div>
  );
}

function ExternalLink({ href, label }) {
  if (!href) return <span className="tm-muted">-</span>;
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {label}
    </a>
  );
}

function formatLabels(labels) {
  if (!Array.isArray(labels) || labels.length === 0) return '-';
  return labels.join(', ');
}

function formatAssignees(assignees) {
  if (!Array.isArray(assignees) || assignees.length === 0) return '-';
  return assignees.map((assignee) => assignee?.name || assignee?.username).filter(Boolean).join(', ') || '-';
}

function formatTicketId(value) {
  if (!value) return '-';
  return String(value);
}

function syncStatusLabel(value) {
  if (value === 'ok') return 'Synced';
  if (value === 'in_delivery') return 'In delivery';
  if (value === 'target_missing') return 'Target missing';
  if (value === 'error') return 'Sync error';
  return value || 'Unknown';
}

function syncStatusTone(value) {
  if (value === 'ok') return 'success';
  if (value === 'in_delivery') return 'neutral';
  if (value === 'target_missing') return 'warning';
  if (value === 'error') return 'danger';
  return 'muted';
}

function buildRequestParams(filters) {
  const params = {};
  if (filters.search) params.search = filters.search;
  if (filters.target_team) params.target_team = filters.target_team;
  if (filters.state) params.state = filters.state;
  if (filters.assignee) params.assignee = filters.assignee;
  if (filters.label) params.label = filters.label;
  if (filters.updated_since) params.updated_since = filters.updated_since;
  if (filters.sort_by) params.sort_by = filters.sort_by;
  if (filters.sort_direction) params.sort_direction = filters.sort_direction;
  return params;
}

function formatAlertUnreadCount(value) {
  const count = Number(value || 0);
  if (count > 99) return '99+';
  return String(Math.max(count, 0));
}
