import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { Button } from 'reactstrap';

import api from '../../api/client.js';
import { DATA_DOMAINS } from '../../api/queryStore.js';
import AuthGate from './AuthGate.jsx';
import { useSessionDomainRefresh } from '../hooks/useLiveRefresh.js';
import { isNewTicketModeVisible, resolveNewTicketInitialMode } from '../newTicketMode.js';
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
  const initialMode = resolveNewTicketInitialMode(user, searchParams.get('target'));
  const [mode, setMode] = useState(initialMode);
  const [meta, setMeta] = useState(null);
  const [clients, setClients] = useState([]);
  const [partners, setPartners] = useState([]);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');
  const handleCancel = () => navigate('/legacy-tickets');
  const handleCreated = (ticket, failedUploads = []) => {
    const notice = buildUploadNotice(failedUploads);
    navigate(`/legacy-tickets/${ticket.id}`, notice ? { state: { notice } } : undefined);
  };

  useEffect(() => {
    setMode(resolveNewTicketInitialMode(user, searchParams.get('target')));
  }, [user.kind, searchParams]);

  const loadFormData = useCallback(async () => {
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
    try {
      const responses = await Promise.all(requests);
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
    } catch (err) {
      setError(apiError(err));
    }
  }, [user.kind, mode]);

  useEffect(() => {
    loadFormData();
  }, [loadFormData]);

  useSessionDomainRefresh(
    [DATA_DOMAINS.meta, DATA_DOMAINS.clients, DATA_DOMAINS.partners, DATA_DOMAINS.users],
    loadFormData
  );

  if (!meta && !error) return <Loading />;

  const pageTitle = user.kind === 'internal' && mode === 'partner' ? 'Create ticket to partner' : 'Create ticket';

  return (
    <div className="tm-screen">
      <PageHeader title={pageTitle} />
      <ErrorBanner error={error} />
      <section className="tm-new-ticket-page">
        {user.kind === 'internal' && (
          <div className="tm-segmented tm-new-ticket-mode" aria-label="Ticket target">
            {isNewTicketModeVisible(user, 'internal') && (
            <Button
              color={mode === 'internal' ? 'primary' : 'secondary'}
              outline={mode !== 'internal'}
              type="button"
              onClick={() => setMode('internal')}
            >
              Internal
            </Button>
            )}
            {isNewTicketModeVisible(user, 'partner') && (
            <Button
              color={mode === 'partner' ? 'primary' : 'secondary'}
              outline={mode !== 'partner'}
              type="button"
              onClick={() => setMode('partner')}
            >
              To partner
            </Button>
            )}
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
