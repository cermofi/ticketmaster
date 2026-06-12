import React, { useEffect, useState } from 'react';
import { Button, Form, Input, Table } from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { EmptyRow, ErrorBanner, PageHeader, TimeCell, apiError } from './helpers.jsx';

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

  const load = async () => {
    setError('');
    try {
      const response = await api.get('/audit', { params: entityId ? { entity_id: entityId } : {} });
      setRows(response.data);
    } catch (err) {
      setError(apiError(err));
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (user.kind !== 'internal' || !['Admin', 'DeliveryManager'].includes(user.internal_role)) {
    return <div className="tm-screen"><ErrorBanner error="Audit log is available only to Admin and Delivery Manager." /></div>;
  }

  return (
    <div className="tm-screen">
      <PageHeader
        title="Audit"
        actions={(
          <Button outline color="secondary" onClick={load} title="Refresh audit log">
            Refresh
          </Button>
        )}
      />
      <ErrorBanner error={error} />
      <Form
        className="tm-audit-search"
        onSubmit={(event) => {
          event.preventDefault();
          load();
        }}
      >
        <Input
          value={entityId}
          onChange={(event) => setEntityId(event.target.value)}
          placeholder="Filter by entity ID"
        />
      </Form>
      <div className="tm-table-wrap">
        <Table responsive hover className="tm-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Entity</th>
              <th>Action</th>
              <th>Source</th>
              <th>Changed by</th>
              <th>New value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td><TimeCell value={row.changed_at} /></td>
                <td>{row.entity_type}:{row.entity_id.slice(0, 8)}</td>
                <td>{row.action}</td>
                <td className="tm-quiet-cell">{row.source}</td>
                <td className="tm-quiet-cell">{row.changed_by_user_id?.slice(0, 8) || '-'}</td>
                <td>
                  <code className="tm-code-cell tm-audit-json" title={stringifyValue(row.new_value)}>
                    {truncateValue(stringifyValue(row.new_value))}
                  </code>
                </td>
              </tr>
            ))}
            {rows.length === 0 && <EmptyRow colSpan="6" title="No audit records" message="No changes found for this filter." />}
          </tbody>
        </Table>
      </div>
    </div>
  );
}

function stringifyValue(value) {
  if (value === null || typeof value === 'undefined') return '-';
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function truncateValue(value, length = 120) {
  if (!value || value.length <= length) return value;
  return `${value.slice(0, length)}...`;
}
