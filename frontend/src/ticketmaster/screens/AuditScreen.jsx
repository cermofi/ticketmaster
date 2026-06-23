import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactJson from '@microlink/react-json-view';
import { Button, Form, FormGroup, Input, Label, Modal, ModalBody, ModalFooter, ModalHeader, Table } from 'reactstrap';

import api from '../../api/client.js';
import { shouldShowAuditInitialLoading } from '../auditLoad.js';
import AuthGate from './AuthGate.jsx';
import { useRefetchOnFocus } from '../hooks/useLiveRefresh.js';
import { useUrlFilters } from '../hooks/useUrlFilters.js';
import { AbsoluteTimeCell, EmptyRow, ErrorBanner, Loading, PageHeader, apiError, hasAnyInternalRole } from './helpers.jsx';

const EMPTY_FILTERS = {
  search: '',
  from: '',
  to: '',
  action: '',
  source: '',
  entity_type: '',
  entity_id: '',
  changed_by: '',
  has_details: false,
};
const FILTER_KEYS = Object.keys(EMPTY_FILTERS);
const FILTER_DEBOUNCE_MS = 400;

export default function AuditScreen() {
  return (
    <AuthGate>
      {(user) => <Audit user={user} />}
    </AuthGate>
  );
}

function Audit({ user }) {
  const [rows, setRows] = useState([]);
  const { filters, syncFiltersToUrl, resetFilters: resetUrlFilters } = useUrlFilters(
    EMPTY_FILTERS,
    FILTER_KEYS,
    { booleanKeys: ['has_details'] },
  );
  const [options, setOptions] = useState({ actions: [], sources: [], entity_types: [] });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [detailRow, setDetailRow] = useState(null);
  const skipDebouncedReload = useRef(true);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const setFilters = useCallback((next) => {
    const merged = typeof next === 'function' ? next(filtersRef.current) : next;
    syncFiltersToUrl(merged);
  }, [syncFiltersToUrl]);

  const load = useCallback(async (nextFilters, { background = false } = {}) => {
    const activeFilters = nextFilters ?? filtersRef.current;
    setError('');
    if (!background) {
      setLoading(true);
    }
    try {
      const params = buildAuditParams(activeFilters);
      const response = await api.get('/audit', { params });
      setRows(response.data);
    } catch (err) {
      setError(apiError(err));
    } finally {
      if (!background) {
        setLoading(false);
      }
      setHasLoaded(true);
    }
  }, []);

  const refreshInBackground = useCallback(() => {
    load(undefined, { background: true });
  }, [load]);

  const loadOptions = useCallback(async () => {
    try {
      const response = await api.get('/audit/options');
      setOptions(response.data);
    } catch {
      // Filter dropdowns fall back to text inputs when options fail to load.
    }
  }, []);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  const filtersKey = useMemo(() => JSON.stringify(filters), [filters]);

  useEffect(() => {
    if (skipDebouncedReload.current) {
      skipDebouncedReload.current = false;
      load(filters);
      return undefined;
    }
    const handle = window.setTimeout(() => load(filters), FILTER_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [filtersKey, load, filters]);

  useRefetchOnFocus(refreshInBackground);

  const updateFilter = (key, value) => setFilters((current) => ({ ...current, [key]: value }));

  const updateAndApply = (key, value) => {
    const nextFilters = { ...filtersRef.current, [key]: value };
    setFilters(nextFilters);
    load(nextFilters);
  };

  const resetFilters = () => {
    skipDebouncedReload.current = true;
    const cleared = resetUrlFilters();
    load(cleared);
  };

  if (user.kind !== 'internal' || !hasAnyInternalRole(user, ['Admin', 'DeliveryManager'])) {
    return <div className="tm-screen tm-audit-screen"><ErrorBanner error="Audit log is available only to Admin and Delivery Manager." /></div>;
  }

  return (
    <div className="tm-screen tm-audit-screen">
      <PageHeader title="Audit" />
      <ErrorBanner error={error} />
      <AuditFilters
        filters={filters}
        options={options}
        onUpdate={updateFilter}
        onApply={updateAndApply}
        onReset={resetFilters}
      />
      {shouldShowAuditInitialLoading(loading, hasLoaded) ? <Loading /> : (
      <div className="tm-table-wrap tm-audit-table-wrap">
        <Table hover className="tm-table tm-audit-table">
          <colgroup>
            <col className="tm-audit-col-time" />
            <col className="tm-audit-col-entity" />
            <col className="tm-audit-col-action" />
            <col className="tm-audit-col-source" />
            <col className="tm-audit-col-changed-by" />
            <col className="tm-audit-col-view" />
          </colgroup>
          <thead>
            <tr>
              <th className="tm-audit-col-time">Time</th>
              <th className="tm-audit-col-entity">Entity</th>
              <th className="tm-audit-col-action">Action</th>
              <th className="tm-audit-col-source">Source</th>
              <th className="tm-audit-col-changed-by">Changed by</th>
              <th className="tm-audit-col-view" aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="tm-audit-col-time"><AbsoluteTimeCell value={row.changed_at} /></td>
                <td className="tm-audit-col-entity" title={`${row.entity_type}:${row.entity_id}`}>{row.entity_label || `${row.entity_type}:${row.entity_id}`}</td>
                <td className="tm-audit-col-action">{row.action}</td>
                <td className="tm-audit-col-source tm-quiet-cell">{row.source}</td>
                <td className="tm-audit-col-changed-by tm-quiet-cell">{row.changed_by_label || '-'}</td>
                <td className="tm-audit-col-view">
                  <AuditViewButton row={row} onOpen={setDetailRow} />
                </td>
              </tr>
            ))}
            {rows.length === 0 && <EmptyRow colSpan="6" title="No audit records" message="No changes found for this filter." />}
          </tbody>
        </Table>
      </div>
      )}
      <AuditDetailsModal row={detailRow} onClose={() => setDetailRow(null)} />
    </div>
  );
}

function AuditFilters({ filters, options, onUpdate, onApply, onReset }) {
  const actions = options.actions ?? [];
  const sources = options.sources ?? [];
  const entityTypes = options.entity_types ?? [];

  return (
    <>
      <Form className="tm-audit-search" onSubmit={(event) => event.preventDefault()}>
        <Input
          value={filters.search}
          onChange={(event) => onUpdate('search', event.target.value)}
          placeholder="Search action, entity, source, user, payload…"
          aria-label="Search audit log"
        />
      </Form>
      <Form className="tm-audit-filters-panel">
        <FormGroup>
          <Label for="audit-from">From</Label>
          <Input
            id="audit-from"
            type="datetime-local"
            value={filters.from}
            onChange={(event) => onApply('from', event.target.value)}
          />
        </FormGroup>
        <FormGroup>
          <Label for="audit-to">To</Label>
          <Input
            id="audit-to"
            type="datetime-local"
            value={filters.to}
            onChange={(event) => onApply('to', event.target.value)}
          />
        </FormGroup>
        <FormGroup>
          <Label for="audit-action">Action</Label>
          {actions.length > 0 ? (
            <Input id="audit-action" type="select" value={filters.action} onChange={(event) => onApply('action', event.target.value)}>
              <option value="">All</option>
              {actions.map((action) => <option key={action} value={action}>{action}</option>)}
            </Input>
          ) : (
            <Input
              id="audit-action"
              value={filters.action}
              onChange={(event) => onUpdate('action', event.target.value)}
              placeholder="e.g. ticket.create"
            />
          )}
        </FormGroup>
        <FormGroup>
          <Label for="audit-source">Source</Label>
          <Input id="audit-source" type="select" value={filters.source} onChange={(event) => onApply('source', event.target.value)}>
            <option value="">All</option>
            {sources.map((source) => <option key={source} value={source}>{source}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label for="audit-entity-type">Entity type</Label>
          <Input id="audit-entity-type" type="select" value={filters.entity_type} onChange={(event) => onApply('entity_type', event.target.value)}>
            <option value="">All</option>
            {entityTypes.map((entityType) => <option key={entityType} value={entityType}>{entityType}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label for="audit-entity-id">Entity ID</Label>
          <Input
            id="audit-entity-id"
            value={filters.entity_id}
            onChange={(event) => onUpdate('entity_id', event.target.value)}
            placeholder="Exact entity ID"
          />
        </FormGroup>
        <FormGroup>
          <Label for="audit-changed-by">Changed by</Label>
          <Input
            id="audit-changed-by"
            value={filters.changed_by}
            onChange={(event) => onUpdate('changed_by', event.target.value)}
            placeholder="Name or e-mail"
          />
        </FormGroup>
        <FormGroup className="tm-audit-filters-toggle">
          <Label for="audit-has-details">Details</Label>
          <div className="tm-audit-filters-checkbox">
            <Input
              id="audit-has-details"
              type="checkbox"
              checked={filters.has_details}
              onChange={(event) => onApply('has_details', event.target.checked)}
            />
            <span>Only with payload</span>
          </div>
        </FormGroup>
        <FormGroup className="tm-audit-filters-actions">
          <Label className="tm-audit-filters-reset-spacer" aria-hidden="true">&nbsp;</Label>
          <button className="tm-audit-filters-reset-btn form-control" type="button" onClick={onReset}>
            Reset filters
          </button>
        </FormGroup>
      </Form>
    </>
  );
}

function buildAuditParams(filters) {
  const params = {};
  if (filters.search) params.search = filters.search;
  if (filters.from) params.from = filters.from;
  if (filters.to) params.to = filters.to;
  if (filters.action) params.action = filters.action;
  if (filters.source) params.source = filters.source;
  if (filters.entity_type) params.entity_type = filters.entity_type;
  if (filters.entity_id) params.entity_id = filters.entity_id;
  if (filters.changed_by) params.changed_by = filters.changed_by;
  if (filters.has_details) params.has_details = true;
  return params;
}

function AuditViewButton({ row, onOpen }) {
  const hasPayload = row.old_value != null || row.new_value != null;

  if (!hasPayload) {
    return <span className="tm-muted">-</span>;
  }

  return (
    <Button color="link" size="sm" className="tm-audit-view-btn p-0" onClick={() => onOpen(row)}>
      View
    </Button>
  );
}

function AuditDetailsModal({ row, onClose }) {
  const isOpen = Boolean(row);

  return (
    <Modal isOpen={isOpen} toggle={onClose} size="lg" backdrop>
      <ModalHeader toggle={onClose}>Audit details</ModalHeader>
      <ModalBody>
        {row && (
          <div className="tm-audit-details-modal">
            <dl className="tm-audit-details-meta">
              <div><dt>Action</dt><dd>{row.action}</dd></div>
              <div><dt>Entity</dt><dd>{row.entity_label || row.entity_id}</dd></div>
              <div><dt>Changed by</dt><dd>{row.changed_by_label || '-'}</dd></div>
            </dl>
            <AuditPayloadSection title="Previous value" value={row.old_value} />
            <AuditPayloadSection title="New value" value={row.new_value} />
          </div>
        )}
      </ModalBody>
      <ModalFooter>
        <Button color="secondary" outline onClick={onClose}>Close</Button>
      </ModalFooter>
    </Modal>
  );
}

function AuditPayloadSection({ title, value }) {
  if (value === null || typeof value === 'undefined') {
    return (
      <section className="tm-audit-payload-section">
        <h6>{title}</h6>
        <p className="tm-muted">-</p>
      </section>
    );
  }

  return (
    <section className="tm-audit-payload-section">
      <h6>{title}</h6>
      <div className="tm-audit-payload-json">
        <ReactJson
          src={value}
          name={false}
          displayDataTypes={false}
          enableClipboard={false}
          collapsed={1}
          theme="monokai"
        />
      </div>
    </section>
  );
}
