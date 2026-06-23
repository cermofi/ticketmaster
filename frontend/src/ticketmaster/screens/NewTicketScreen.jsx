import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { ErrorBanner, Loading, PageHeader, apiError } from './helpers.jsx';
import { InternalTicketForm, PartnerTicketForm } from './ticketForms.jsx';

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
  const handleCancel = () => navigate('/');
  const handleCreated = (ticket, failedUploads = []) => {
    const notice = buildUploadNotice(failedUploads);
    navigate(`/tickets/${ticket.id}`, notice ? { state: { notice } } : undefined);
  };

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
      <PageHeader title="Create ticket" />
      <ErrorBanner error={error} />
      <section className="tm-new-ticket-page">
        {user.kind === 'partner' && <PartnerTicketForm meta={meta} clients={clients} onCreated={handleCreated} onCancel={handleCancel} />}
        {user.kind === 'internal' && <InternalTicketForm meta={meta} onCreated={handleCreated} onCancel={handleCancel} />}
      </section>
    </div>
  );
}

function buildUploadNotice(failedUploads) {
  if (!Array.isArray(failedUploads) || failedUploads.length === 0) return '';
  const names = failedUploads.map((item) => item.name).filter(Boolean);
  const listed = names.slice(0, 3).join(', ');
  const rest = names.length > 3 ? ` and ${names.length - 3} more` : '';
  return `Ticket was created, but ${failedUploads.length} attachments failed to upload (${listed}${rest}). Upload them from the ticket detail in the Attachments section.`;
}
