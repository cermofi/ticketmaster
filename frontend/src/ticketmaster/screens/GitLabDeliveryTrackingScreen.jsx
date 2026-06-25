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
import { asArray, EmptyRow, ErrorBanner, Loading, PageHeader, StatusPill, TimeCell, apiError, hasAnyInternalRole } from './helpers.jsx';

const EMPTY_FILTERS = {
  search: '',
  target_team: '',
  state: '',
  missing_mapping: false,
  updated_since: ''
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
    FILTER_KEYS,
    { booleanKeys: ['missing_mapping'] }
  );
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const [meta, setMeta] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [syncLoading, setSyncLoading] = useState(false);
  const [mappingModalOpen, setMappingModalOpen] = useState(false);
  const [mappingTargetUrl, setMappingTargetUrl] = useState('');
  const [mappingError, setMappingError] = useState('');
  const [mappingSaving, setMappingSaving] = useState(false);
  const [mappingRow, setMappingRow] = useState(null);

  const setFilters = useCallback((next) => {
    const merged = typeof next === 'function' ? next(filtersRef.current) : next;
    syncFiltersToUrl(merged);
  }, [syncFiltersToUrl]);

  const load = useCallback(async (nextFilters) => {
    if (!canView) return;
    const activeFilters = nextFilters ?? filtersRef.current;
    setError('');
    setLoading(true);
    try {
      const params = {};
      if (activeFilters.search) params.search = activeFilters.search;
      if (activeFilters.target_team) params.target_team = activeFilters.target_team;
      if (activeFilters.state) params.state = activeFilters.state;
      if (activeFilters.missing_mapping) params.missing_mapping = true;
      if (activeFilters.updated_since) params.updated_since = activeFilters.updated_since;
      const [metaResponse, listResponse] = await Promise.all([
        api.get('/gitlab/delivery-tracking/meta'),
        api.get('/gitlab/delivery-tracking', { params })
      ]);
      setMeta(metaResponse.data);
      setRows(asArray(listResponse.data));
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  }, [canView]);

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

  const openMappingDialog = (row) => {
    setMappingRow(row);
    setMappingTargetUrl(row.target_url || '');
    setMappingError('');
    setMappingModalOpen(true);
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
        <PageHeader title="Delivery tracking" />
        <ErrorBanner error="Delivery tracking is available only to internal users." />
      </div>
    );
  }

  return (
    <div className="tm-screen">
      <PageHeader
        title="GitLab Delivery Tracking"
        actions={canManage ? (
          <Button color="primary" onClick={triggerSync} disabled={syncLoading}>
            {syncLoading ? 'Sync in progress...' : 'Sync now'}
          </Button>
        ) : null}
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
            onApply={load}
            onReset={() => {
              const reset = resetUrlFilters();
              load(reset);
            }}
          />
          <TrackingTable
            rows={rows}
            canManage={canManage}
            onManualMapping={openMappingDialog}
          />
        </>
      )}
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

function TrackingFilters({ filters, setFilters, teams, states, onApply, onReset }) {
  const update = (key, value) => setFilters({ ...filters, [key]: value });
  const updateAndApply = (key, value) => {
    const next = { ...filters, [key]: value };
    setFilters(next);
    onApply(next);
  };

  return (
    <Form className="tm-ticket-filters-panel" onSubmit={(event) => { event.preventDefault(); onApply(); }}>
      <FormGroup>
        <Label>Search</Label>
        <Input
          value={filters.search}
          placeholder="Search by title or issue IID"
          onChange={(event) => update('search', event.target.value)}
        />
      </FormGroup>
      <FormGroup>
        <Label>Target team</Label>
        <Input type="select" value={filters.target_team} onChange={(event) => updateAndApply('target_team', event.target.value)}>
          <option value="">All</option>
          {teams.map((team) => <option key={team.name} value={team.name}>{team.name}</option>)}
        </Input>
      </FormGroup>
      <FormGroup>
        <Label>Current state</Label>
        <Input type="select" value={filters.state} onChange={(event) => updateAndApply('state', event.target.value)}>
          <option value="">All</option>
          {states.map((state) => <option key={state} value={state}>{state}</option>)}
        </Input>
      </FormGroup>
      <FormGroup>
        <Label>Updated since</Label>
        <Input type="date" value={filters.updated_since} onChange={(event) => updateAndApply('updated_since', event.target.value)} />
      </FormGroup>
      <FormGroup className="d-flex align-items-end">
        <div className="form-check mb-2">
          <Input
            id="filter-missing-mapping"
            type="checkbox"
            checked={Boolean(filters.missing_mapping)}
            onChange={(event) => updateAndApply('missing_mapping', event.target.checked)}
          />
          <Label className="form-check-label" for="filter-missing-mapping">
            Missing mapping only
          </Label>
        </div>
      </FormGroup>
      <FormGroup className="tm-ticket-filters-actions">
        <Label className="tm-ticket-filters-reset-spacer" aria-hidden="true">&nbsp;</Label>
        <button className="tm-ticket-filters-reset-btn form-control" type="button" onClick={onReset}>
          Reset filters
        </button>
      </FormGroup>
    </Form>
  );
}

function TrackingTable({ rows, canManage, onManualMapping }) {
  return (
    <div className="tm-table-wrap">
      <Table hover responsive className="tm-table">
        <thead>
          <tr>
            <th>Delivery issue</th>
            <th>Delivery URL</th>
            <th>Target team/project</th>
            <th>Target issue URL</th>
            <th>Current state</th>
            <th>Labels</th>
            <th>Assignee</th>
            <th>Last GitLab update</th>
            <th>Sync status</th>
            <th className="text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <div>{row.delivery_title}</div>
                <div className="tm-muted">#{row.delivery_issue_iid}</div>
              </td>
              <td>
                <ExternalLink href={row.delivery_url} label="Open delivery issue" />
              </td>
              <td>
                <div>{row.target_team_name || '-'}</div>
                <div className="tm-muted">{row.target_project_name || '-'}</div>
              </td>
              <td>
                <ExternalLink href={row.target_url} label={row.target_issue_iid ? `#${row.target_issue_iid}` : 'Open target issue'} />
              </td>
              <td>
                {row.target_state ? <StatusPill value={row.target_state} /> : <span className="tm-muted">-</span>}
              </td>
              <td className="tm-quiet-cell">{formatLabels(row.target_labels)}</td>
              <td className="tm-quiet-cell">{formatAssignees(row.target_assignees)}</td>
              <td className="tm-quiet-cell">
                <TimeCell value={row.target_updated_at || row.delivery_updated_at} />
              </td>
              <td>
                <StatusPill value={syncStatusLabel(row.sync_status)} tone={syncStatusTone(row.sync_status)} />
              </td>
              <td className="text-end">
                {canManage && row.target_missing && (
                  <Button size="sm" outline color="secondary" onClick={() => onManualMapping(row)}>
                    Map manually
                  </Button>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <EmptyRow
              colSpan="10"
              title="No tracked issues found"
              message="Adjust filters or run a sync to import Delivery issues from GitLab."
            />
          )}
        </tbody>
      </Table>
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

function syncStatusLabel(value) {
  if (value === 'ok') return 'Synced';
  if (value === 'target_missing') return 'Target missing';
  if (value === 'error') return 'Sync error';
  return value || 'Unknown';
}

function syncStatusTone(value) {
  if (value === 'ok') return 'success';
  if (value === 'target_missing') return 'warning';
  if (value === 'error') return 'danger';
  return 'muted';
}
