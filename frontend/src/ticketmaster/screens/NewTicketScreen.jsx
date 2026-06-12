import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { ErrorBanner, Loading, PageHeader, apiError } from './helpers.jsx';
import { InternalTicketForm, PartnerOnBehalfTicketForm, PartnerTicketForm } from './DashboardScreen.jsx';

export default function NewTicketScreen() {
  return (
    <AuthGate>
      {(user) => <NewTicket user={user} />}
    </AuthGate>
  );
}

function NewTicket({ user }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [meta, setMeta] = useState(null);
  const [clients, setClients] = useState([]);
  const [partners, setPartners] = useState([]);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');
  const canCreateOnBehalf = user.kind === 'internal' && ['Admin', 'DeliveryManager'].includes(user.internal_role);
  const onBehalfMode = canCreateOnBehalf && searchParams.get('mode') === 'partner';
  const handleCreated = (ticket, failedUploads = []) => {
    const notice = buildUploadNotice(failedUploads);
    navigate(`/tickets/${ticket.id}`, notice ? { state: { notice } } : undefined);
  };

  useEffect(() => {
    Promise.all([
      api.get('/meta'),
      api.get('/clients').catch(() => ({ data: [] })),
      onBehalfMode ? api.get('/partners').catch(() => ({ data: [] })) : Promise.resolve({ data: [] }),
      onBehalfMode ? api.get('/users').catch(() => ({ data: [] })) : Promise.resolve({ data: [] })
    ])
      .then(([metaResponse, clientsResponse, partnersResponse, usersResponse]) => {
        setMeta(metaResponse.data);
        setClients(clientsResponse.data);
        setPartners(partnersResponse.data);
        setUsers(usersResponse.data);
      })
      .catch((err) => setError(apiError(err)));
  }, [onBehalfMode]);

  if (!meta && !error) return <Loading />;

  return (
    <div className="tm-screen">
      <PageHeader title={onBehalfMode ? 'Přidat ticket za partnera' : 'Vytvořit ticket'}>
        {onBehalfMode ? 'Partnerský ticket vytvořený interním uživatelem.' : 'Nový požadavek pro podporu.'}
      </PageHeader>
      <ErrorBanner error={error} />
      <section className="tm-new-ticket-page">
        {user.kind === 'partner' && <PartnerTicketForm meta={meta} clients={clients} onCreated={handleCreated} />}
        {user.kind === 'internal' && onBehalfMode && (
          <PartnerOnBehalfTicketForm
            meta={meta}
            partners={partners}
            clients={clients}
            users={users}
            onCreated={handleCreated}
          />
        )}
        {user.kind === 'internal' && !onBehalfMode && <InternalTicketForm meta={meta} onCreated={handleCreated} />}
      </section>
    </div>
  );
}

function buildUploadNotice(failedUploads) {
  if (!Array.isArray(failedUploads) || failedUploads.length === 0) return '';
  const names = failedUploads.map((item) => item.name).filter(Boolean);
  const listed = names.slice(0, 3).join(', ');
  const rest = names.length > 3 ? ` a dalších ${names.length - 3}` : '';
  return `Ticket byl vytvořen, ale ${failedUploads.length} příloh se nepodařilo nahrát (${listed}${rest}). Nahraj je prosím z detailu ticketu v sekci Přílohy.`;
}
