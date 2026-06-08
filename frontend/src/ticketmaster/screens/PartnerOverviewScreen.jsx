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
        <PageHeader title="Přehled klientů" />
        <EmptyState icon="bi-shield-lock" title="Přístup pouze pro partnery" message="Tento přehled je dostupný jen partner uživatelům." />
      </div>
    );
  }

  const clients = asArray(overview?.clients);
  const technicalUsers = asArray(overview?.technical_users);
  const responsibleClientCount = clients.filter((client) => client.current_user_responsible).length;

  return (
    <div className="tm-screen">
      <PageHeader title="Přehled klientů">
        {user.partner_role === 'responsible'
          ? `${responsibleClientCount} klientů vedených u vás`
          : `${clients.length} klientů partnera`}
      </PageHeader>
      <ErrorBanner error={error} />
      {loading ? <Loading /> : (
        <div className="tm-partner-overview-grid">
          <section className="tm-panel">
            <h2>Klienti a odpovědné osoby</h2>
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
                      {responsibleUsers.length === 0 && <span className="tm-muted">Bez přiřazené odpovědné osoby.</span>}
                    </div>
                  </article>
                );
              })}
              {clients.length === 0 && (
                <EmptyState icon="bi-building" title="Žádní klienti" message="Partner zatím nemá žádné aktivní klienty." />
              )}
            </div>
          </section>
          <aside className="tm-panel">
            <h2>Technické osoby</h2>
            <div className="tm-person-list tm-person-list-vertical">
              {technicalUsers.map((row) => <PersonChip key={row.id} user={row} />)}
              {technicalUsers.length === 0 && <span className="tm-muted">Žádné technické osoby.</span>}
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
