import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { Button } from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { ErrorBanner, Loading, PageHeader, apiError } from './helpers.jsx';
import { InternalTicketForm, PartnerOnBehalfTicketForm, PartnerTicketForm } from './ticketForms.jsx';

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
  const initialMode = searchParams.get('target') === 'partner' ? 'partner' : 'internal';
  const [mode, setMode] = useState(user.kind === 'internal' ? initialMode : 'partner');
  const [meta, setMeta] = useState(null);
  const [clients, setClients] = useState([]);
  const [partners, setPartners] = useState([]);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');
  const handleCancel = () => navigate('/');
  const handleCreated = (ticket, failedUploads = []) => {
    const notice = buildUploadNotice(failedUploads);
    navigate(`/tickets/${ticket.id}`, notice ? { state: { notice } } : undefined);
  };

  useEffect(() => {
    const requests = [api.get('/meta')];
    if (user.kind === 'partner') {
      requests.push(api.get('/clients').catch(() => ({ data: [] })));
    } else if (mode === 'partner') {
      requests.push(
        api.get('/clients').catch(() => ({ data: [] })),
        api.get('/partners').catch(() => ({ data: [] })),
        api.get('/users').catch(() => ({ data: [] }))
      );
    }
    Promise.all(requests)
      .then((responses) => {
        setMeta(responses[0].data);
        if (user.kind === 'partner') {
          setClients(responses[1]?.data || []);
          return;
        }
        if (mode === 'partner') {
          setClients(responses[1]?.data || []);
          setPartners(responses[2]?.data || []);
          setUsers(responses[3]?.data || []);
        }
      })
      .catch((err) => setError(apiError(err)));
  }, [user.kind, mode]);

  if (!meta && !error) return <Loading />;

  const pageTitle = user.kind === 'internal' && mode === 'partner' ? 'Create ticket to partner' : 'Create ticket';

  return (
    <div className="tm-screen">
      <PageHeader title={pageTitle} />
      <ErrorBanner error={error} />
      <section className="tm-new-ticket-page">
        {user.kind === 'internal' && (
          <div className="tm-segmented tm-new-ticket-mode" aria-label="Ticket target">
            <Button
              color={mode === 'internal' ? 'primary' : 'secondary'}
              outline={mode !== 'internal'}
              type="button"
              onClick={() => setMode('internal')}
            >
              Internal
            </Button>
            <Button
              color={mode === 'partner' ? 'primary' : 'secondary'}
              outline={mode !== 'partner'}
              type="button"
              onClick={() => setMode('partner')}
            >
              To partner
            </Button>
          </div>
        )}
        {user.kind === 'partner' && (
          <PartnerTicketForm meta={meta} clients={clients} onCreated={handleCreated} onCancel={handleCancel} />
        )}
        {user.kind === 'internal' && mode === 'internal' && (
          <InternalTicketForm meta={meta} onCreated={handleCreated} onCancel={handleCancel} />
        )}
        {user.kind === 'internal' && mode === 'partner' && (
          <PartnerOnBehalfTicketForm
            meta={meta}
            partners={partners}
            clients={clients}
            users={users}
            onCreated={handleCreated}
            onCancel={handleCancel}
          />
        )}
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
