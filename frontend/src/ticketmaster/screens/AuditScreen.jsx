import React, { useEffect, useState } from 'react';
import { Button, Input, Table } from 'reactstrap';

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
    return <div className="tm-screen"><ErrorBanner error="Audit log vidí pouze Admin a Delivery Manager." /></div>;
  }

  return (
    <div className="tm-screen">
      <PageHeader
        title="Audit log"
        actions={(
          <Button outline color="secondary" onClick={load} title="Obnovit audit log">
            <i className="bi bi-arrow-clockwise" />
            Obnovit
          </Button>
        )}
      />
      <ErrorBanner error={error} />
      <div className="tm-toolbar tm-audit-toolbar">
        <Input value={entityId} onChange={(event) => setEntityId(event.target.value)} placeholder="Filtrovat podle ID entity" />
        <Button color="primary" onClick={load}>
          <i className="bi bi-search" />
          Hledat
        </Button>
      </div>
      <div className="tm-table-wrap">
        <Table responsive hover className="tm-table">
          <thead>
            <tr>
              <th>Čas</th>
              <th>Entity</th>
              <th>Akce</th>
              <th>Zdroj</th>
              <th>Změnil</th>
              <th>Nová hodnota</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td><TimeCell value={row.changed_at} /></td>
                <td>{row.entity_type}:{row.entity_id.slice(0, 8)}</td>
                <td>{row.action}</td>
                <td>{row.source}</td>
                <td>{row.changed_by_user_id?.slice(0, 8) || '-'}</td>
                <td><code className="tm-code-cell">{JSON.stringify(row.new_value)}</code></td>
              </tr>
            ))}
            {rows.length === 0 && <EmptyRow colSpan="6" title="Žádné auditní záznamy" message="Pro tento filtr nejsou uložené žádné změny." />}
          </tbody>
        </Table>
      </div>
    </div>
  );
}
