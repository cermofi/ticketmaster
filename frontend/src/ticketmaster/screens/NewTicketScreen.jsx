import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { ErrorBanner, Loading, PageHeader, apiError } from './helpers.jsx';
import { InternalTicketForm, PartnerTicketForm } from './DashboardScreen.jsx';

export default function NewTicketScreen() {
  return (
    <AuthGate>
      {(user) => <NewTicket user={user} />}
    </AuthGate>
  );
}

function NewTicket({ user }) {
  const navigate = useNavigate();
  const [meta, setMeta] = useState(null);
  const [clients, setClients] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      api.get('/meta'),
      api.get('/clients').catch(() => ({ data: [] }))
    ])
      .then(([metaResponse, clientsResponse]) => {
        setMeta(metaResponse.data);
        setClients(clientsResponse.data);
      })
      .catch((err) => setError(apiError(err)));
  }, []);

  if (!meta && !error) return <Loading />;

  return (
    <div className="tm-screen">
      <PageHeader title="Vytvořit ticket">
        Nový požadavek pro podporu.
      </PageHeader>
      <ErrorBanner error={error} />
      <section className="tm-new-ticket-page">
        {user.kind === 'partner'
          ? <PartnerTicketForm meta={meta} clients={clients} onCreated={() => navigate('/')} />
          : <InternalTicketForm meta={meta} onCreated={() => navigate('/')} />}
      </section>
    </div>
  );
}
