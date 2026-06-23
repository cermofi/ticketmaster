import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactJson from '@microlink/react-json-view';
import { Button, Form, Input, Modal, ModalBody, ModalFooter, ModalHeader, Table } from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { useRefetchOnFocus } from '../hooks/useLiveRefresh.js';
import { AbsoluteTimeCell, EmptyRow, ErrorBanner, PageHeader, apiError, hasAnyInternalRole } from './helpers.jsx';

export default function AuditScreen() {
  return (
    <AuthGate>
      {(user) => <Audit user={user} />}
    </AuthGate>
  );
}

function Audit({ user }) {
  const [rows, setRows] = useState([]);
  const [entityId, setEntityId] = useState('');
  const [error, setError] = useState('');
  const [detailRow, setDetailRow] = useState(null);
  const skipFilterEffect = useRef(true);
  const entityIdRef = useRef(entityId);
  entityIdRef.current = entityId;

  const load = useCallback(async () => {
    setError('');
    try {
      const filter = entityIdRef.current;
      const response = await api.get('/audit', { params: filter ? { entity_id: filter } : {} });
      setRows(response.data);
    } catch (err) {
      setError(apiError(err));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (skipFilterEffect.current) {
      skipFilterEffect.current = false;
      return undefined;
    }
    const handle = window.setTimeout(() => load(), 400);
    return () => window.clearTimeout(handle);
  }, [entityId, load]);

  useRefetchOnFocus(load);

  if (user.kind !== 'internal' || !hasAnyInternalRole(user, ['Admin', 'DeliveryManager'])) {
    return <div className="tm-screen tm-audit-screen"><ErrorBanner error="Audit log is available only to Admin and Delivery Manager." /></div>;
  }

  return (
    <div className="tm-screen tm-audit-screen">
      <PageHeader title="Audit" />
      <ErrorBanner error={error} />
      <Form className="tm-audit-search">
        <Input
          value={entityId}
          onChange={(event) => setEntityId(event.target.value)}
          placeholder="Filter by entity ID"
        />
      </Form>
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
      <AuditDetailsModal row={detailRow} onClose={() => setDetailRow(null)} />
    </div>
  );
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

