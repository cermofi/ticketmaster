import React, { useEffect, useState } from 'react';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { EmptyState, ErrorBanner, Loading, PageHeader, apiError, asArray } from './helpers.jsx';

export default function PartnerOverviewScreen() {
  return (
    <AuthGate>
      {(user) => <PartnerOverview user={user} />}
    </AuthGate>
  );
}

function PartnerOverview({ user }) {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setError('');
    setLoading(true);
    try {
      const response = await api.get('/partner-dashboard');
      setOverview(response.data);
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user.kind === 'partner') {
      load();
    } else {
      setLoading(false);
    }
  }, []);

  if (user.kind !== 'partner') {
    return (
      <div className="tm-screen">
        <PageHeader title="Partner overview" />
        <EmptyState icon="bi-shield-lock" title="Partner-only access" message="This overview is available only to partner users." />
      </div>
    );
  }

  const clients = asArray(overview?.clients);
  const technicalUsers = asArray(overview?.technical_users);
  const responsibleClientCount = clients.filter((client) => client.current_user_responsible).length;

  return (
    <div className="tm-screen">
      <PageHeader title="Partner overview">
        {user.partner_role === 'responsible'
          ? `${responsibleClientCount} clients assigned to you`
          : `${clients.length} partner clients`}
      </PageHeader>
      <ErrorBanner error={error} />
      {loading ? <Loading /> : (
        <div className="tm-partner-overview-grid">
          <section className="tm-panel">
            <h2>Clients and responsible users</h2>
            <div className="tm-client-list">
              {clients.map((client) => {
                const responsibleUsers = asArray(client.responsible_users);
                return (
                  <article className={`tm-client-card ${client.current_user_responsible ? 'is-current-user' : ''}`} key={client.id}>
                    <div>
                      <strong>{client.name}</strong>
                      <div className="tm-muted">{client.key}</div>
                    </div>
                    <div className="tm-person-list">
                      {responsibleUsers.map((row) => <PersonChip key={row.id} user={row} />)}
                      {responsibleUsers.length === 0 && <span className="tm-muted">No responsible user assigned.</span>}
                    </div>
                  </article>
                );
              })}
              {clients.length === 0 && (
                <EmptyState icon="bi-building" title="No clients" message="This partner has no clients yet." />
              )}
            </div>
          </section>
          <aside className="tm-panel">
            <h2>Technical users</h2>
            <div className="tm-person-list tm-person-list-vertical">
              {technicalUsers.map((row) => <PersonChip key={row.id} user={row} />)}
              {technicalUsers.length === 0 && <span className="tm-muted">No technical users.</span>}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

function PersonChip({ user }) {
  return (
    <span className="tm-person-chip">
      <span>{user.name || user.email}</span>
      <small>{user.email}</small>
    </span>
  );
}
