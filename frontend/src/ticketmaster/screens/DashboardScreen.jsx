import React, { useEffect, useState } from 'react';
import { Link } from 'react-router';
import {
  Button,
  ButtonDropdown,
  DropdownItem,
  DropdownMenu,
  DropdownToggle,
  Form,
  FormGroup,
  Input,
  Label,
  Table
} from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { EmptyRow, ErrorBanner, Loading, MarkdownText, PageHeader, StatusPill, TimeCell, apiError, asArray, labelValue } from './helpers.jsx';

const EMPTY_FILTERS = { search: '', status: '', priority: '', type: '', resolver_team: '', internal: '' };

export default function DashboardScreen() {
  return (
    <AuthGate>
      {(user) => <Dashboard user={user} />}
    </AuthGate>
  );
}

function Dashboard({ user }) {
  const [meta, setMeta] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportLoading, setExportLoading] = useState('');

  const load = async (nextFilters = filters) => {
    setError('');
    setLoading(true);
    try {
      const params = Object.fromEntries(Object.entries(nextFilters).filter(([, value]) => value !== ''));
      const [metaResponse, ticketsResponse] = await Promise.all([
        api.get('/meta'),
        api.get('/tickets', { params })
      ]);
      setMeta(metaResponse.data);
      setTickets(asArray(ticketsResponse.data));
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  };

  const exportTickets = async (format) => {
    setError('');
    setExportLoading(format);
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''));
      const response = await api.get('/tickets/export', { params: { ...params, format }, responseType: 'blob' });
      downloadResponse(response, `ticketmaster_export.${format === 'csv' ? 'zip' : format}`);
    } catch (err) {
      setError(await exportError(err));
    } finally {
      setExportLoading('');
    }
  };

  useEffect(() => {
    load();
  }, []);

  const canCreateOnBehalf = user.kind === 'internal' && ['Admin', 'DeliveryManager'].includes(user.internal_role);

  return (
    <div className="tm-screen">
      <PageHeader
        title="Tickety"
        actions={(
          <>
            <Button color="primary" tag={Link} to="/tickets/new">
              <i className="bi bi-plus-circle" />
              Vytvořit ticket
            </Button>
            {canCreateOnBehalf && (
              <Button color="secondary" outline tag={Link} to="/tickets/new?mode=partner">
                <i className="bi bi-building-add" />
                Ticket za partnera
              </Button>
            )}
            <ExportMenu
              isOpen={exportOpen}
              setOpen={setExportOpen}
              loading={exportLoading}
              onExport={exportTickets}
            />
            <Button color="secondary" outline onClick={load} title="Obnovit seznam ticketů">
              <i className="bi bi-arrow-clockwise" />
              Obnovit
            </Button>
          </>
        )}
      >
        Přehled dostupných ticketů v systému.
      </PageHeader>
      <ErrorBanner error={error} />
      {loading && !meta ? <Loading /> : (
        <>
          <TicketFilters filters={filters} setFilters={setFilters} meta={meta} user={user} onApply={() => load()} onReset={() => load(EMPTY_FILTERS)} />
          <TicketTable tickets={tickets} user={user} />
        </>
      )}
    </div>
  );
}

function ExportMenu({ isOpen, setOpen, loading, onExport }) {
  const formats = [
    { value: 'json', label: 'JSON' },
    { value: 'xlsx', label: 'XLSX' },
    { value: 'csv', label: 'CSV ZIP' }
  ];
  return (
    <ButtonDropdown isOpen={isOpen} toggle={() => setOpen(!isOpen)}>
      <DropdownToggle color="secondary" outline caret disabled={Boolean(loading)}>
        <i className="bi bi-download" />
        {loading ? 'Exportuji...' : 'Export ticketů'}
      </DropdownToggle>
      <DropdownMenu end>
        {formats.map((format) => (
          <DropdownItem key={format.value} onClick={() => onExport(format.value)} disabled={Boolean(loading)}>
            {format.label}
          </DropdownItem>
        ))}
      </DropdownMenu>
    </ButtonDropdown>
  );
}

function downloadResponse(response, fallbackName) {
  const disposition = response.headers?.['content-disposition'] || '';
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || fallbackName;
  const blob = new Blob([response.data], { type: response.headers?.['content-type'] || 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function exportError(err) {
  if (err.response?.data instanceof Blob) {
    const text = await err.response.data.text();
    try {
      return JSON.parse(text).detail || text;
    } catch {
      return text || 'Export se nepodařilo vytvořit.';
    }
  }
  return apiError(err);
}

function TicketFilters({ filters, setFilters, meta, user, onApply, onReset }) {
  const update = (key, value) => setFilters({ ...filters, [key]: value });
  const reset = () => {
    setFilters(EMPTY_FILTERS);
    onReset();
  };
  const statuses = asArray(meta?.statuses);
  const priorities = asArray(meta?.priorities);
  const ticketTypes = asArray(meta?.ticket_types);
  const resolverTeams = asArray(meta?.resolver_teams);
  return (
    <Form className="tm-toolbar" onSubmit={(event) => { event.preventDefault(); onApply(); }}>
      <FormGroup>
        <Label>Hledat</Label>
        <Input value={filters.search} onChange={(event) => update('search', event.target.value)} placeholder="ID, název, popis" />
      </FormGroup>
      <FormGroup>
        <Label>Stav</Label>
        <Input type="select" value={filters.status} onChange={(event) => update('status', event.target.value)}>
          <option value="">Vše</option>
          {statuses.map((status) => <option key={status} value={status}>{labelValue(status)}</option>)}
        </Input>
      </FormGroup>
      <FormGroup>
        <Label>Priorita</Label>
        <Input type="select" value={filters.priority} onChange={(event) => update('priority', event.target.value)}>
          <option value="">Vše</option>
          {priorities.map((priority) => <option key={priority} value={priority}>{labelValue(priority)}</option>)}
        </Input>
      </FormGroup>
      <FormGroup>
        <Label>Typ</Label>
        <Input type="select" value={filters.type} onChange={(event) => update('type', event.target.value)}>
          <option value="">Vše</option>
          {ticketTypes.map((ticketType) => <option key={ticketType} value={ticketType}>{labelValue(ticketType)}</option>)}
        </Input>
      </FormGroup>
      {user.kind === 'internal' && (
        <FormGroup>
          <Label>Fronta</Label>
          <Input type="select" value={filters.resolver_team} onChange={(event) => update('resolver_team', event.target.value)}>
            <option value="">Vše</option>
            {resolverTeams.map((team) => <option key={team}>{team}</option>)}
          </Input>
        </FormGroup>
      )}
      <div className="tm-toolbar-actions">
        <Button color="primary" type="submit">
          <i className="bi bi-search" />
          Hledat
        </Button>
        <Button color="secondary" outline type="button" onClick={reset}>
          <i className="bi bi-x-circle" />
          Reset filtrů
        </Button>
      </div>
    </Form>
  );
}

function TicketTable({ tickets, user }) {
  return (
    <div className="tm-table-wrap">
      <Table hover responsive className="tm-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Název</th>
            <th>Stav</th>
            <th>Priorita</th>
            <th>Typ</th>
            <th>Tým</th>
            <th>GitLab</th>
            {user.kind === 'internal' && <th>Partner</th>}
            <th className="text-end">Aktualizováno</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr key={ticket.id}>
              <td><Link className="tm-ticket-id" to={`/tickets/${ticket.id}`}>{ticket.id.slice(0, 8)}</Link></td>
              <td className="tm-row-title">
                {ticket.system && <span className="badge text-bg-info me-2">Systémový</span>}
                {ticket.internal && <span className="badge text-bg-secondary me-2">Interní</span>}
                {ticket.title}
              </td>
              <td><StatusPill value={ticket.status} /></td>
              <td><StatusPill value={ticket.priority} priority={ticket.priority} /></td>
              <td><span className="tm-soft-badge">{labelValue(ticket.type)}</span></td>
              <td>{ticket.resolver_team ? <span className="tm-soft-badge">{ticket.resolver_team}</span> : <span className="tm-muted">Nepřiřazeno</span>}</td>
              <td>{ticket.gitlab_status || <span className="tm-muted">-</span>}</td>
              {user.kind === 'internal' && <td>{ticket.partner_name || <span className="tm-muted">-</span>}</td>}
              <td className="text-end tm-quiet-cell"><TimeCell value={ticket.updated_at} /></td>
            </tr>
          ))}
          {tickets.length === 0 && (
            <EmptyRow colSpan={user.kind === 'internal' ? 9 : 8} title="Žádné tickety" message="Zkuste upravit filtry nebo vytvořit nový ticket." />
          )}
        </tbody>
      </Table>
    </div>
  );
}

export function PartnerTicketForm({ meta, clients, onCreated }) {
  const [form, setForm] = useState({ type: 'Question', priority: 'Normal', title: '', description: '', client_id: '' });
  const [error, setError] = useState('');
  const update = (key, value) => setForm({ ...form, [key]: value });
  const submit = async (event) => {
    event.preventDefault();
    setError('');
    try {
      await api.post('/tickets', { ...form, client_id: form.client_id || null });
      setForm({ ...form, title: '', description: '' });
      onCreated();
    } catch (err) {
      setError(apiError(err));
    }
  };
  return (
    <Form className="tm-ticket-create-form" onSubmit={submit}>
      <div className="tm-form-title">
        <h2>Nový ticket</h2>
        <p>Vyplňte základní údaje a popis požadavku.</p>
      </div>
      <ErrorBanner error={error} />
      <TicketFormFields form={form} update={update} meta={meta} clients={clients} />
      <div className="tm-form-actions">
        <Button color="primary" type="submit">
          <i className="bi bi-plus-circle me-1" />
          Vytvořit ticket
        </Button>
      </div>
    </Form>
  );
}

export function InternalTicketForm({ meta, onCreated }) {
  const [form, setForm] = useState({ type: 'Operational Request', priority: 'Normal', title: '', description: '', team: '' });
  const [error, setError] = useState('');
  const update = (key, value) => setForm({ ...form, [key]: value });
  const resolverTeams = asArray(meta?.resolver_teams);
  const submit = async (event) => {
    event.preventDefault();
    setError('');
    try {
      await api.post('/tickets/internal', { ...form, team: form.team || null });
      setForm({ ...form, title: '', description: '' });
      onCreated();
    } catch (err) {
      setError(apiError(err));
    }
  };
  return (
    <Form className="tm-ticket-create-form" onSubmit={submit}>
      <div className="tm-form-title">
        <h2>Nový interní ticket</h2>
        <p>Vyplňte základní údaje a tým, který má požadavek řešit.</p>
      </div>
      <ErrorBanner error={error} />
      <TicketFormFields form={form} update={update} meta={meta} />
      <div className="tm-ticket-form-grid tm-ticket-form-grid-extra">
        <FormGroup>
          <Label>Řešitelský tým</Label>
          <Input type="select" value={form.team} onChange={(event) => update('team', event.target.value)}>
            <option value="">Nepřiřazeno</option>
            {resolverTeams.map((team) => <option key={team}>{team}</option>)}
          </Input>
        </FormGroup>
      </div>
      <div className="tm-form-actions">
        <Button color="primary" type="submit">
          <i className="bi bi-plus-circle me-1" />
          Vytvořit interní ticket
        </Button>
      </div>
    </Form>
  );
}

export function PartnerOnBehalfTicketForm({ meta, partners, clients, users, onCreated }) {
  const [form, setForm] = useState({
    partner_id: '',
    owner_id: '',
    type: 'Question',
    priority: 'Normal',
    title: '',
    description: '',
    client_id: '',
    participant_ids: []
  });
  const [error, setError] = useState('');
  const update = (key, value) => setForm({ ...form, [key]: value });
  const updatePartner = (partnerId) => setForm({
    ...form,
    partner_id: partnerId,
    owner_id: '',
    client_id: '',
    participant_ids: []
  });
  const partnerRows = asArray(partners);
  const clientRows = asArray(clients).filter((client) => client.partner_id === form.partner_id);
  const partnerUsers = asArray(users).filter((row) => row.kind === 'partner' && row.active && row.partner_id === form.partner_id);
  const owners = partnerUsers.filter((row) => row.partner_role === 'responsible');
  const participantOptions = partnerUsers.filter((row) => row.id !== form.owner_id);
  const submit = async (event) => {
    event.preventDefault();
    setError('');
    try {
      await api.post('/tickets/on-behalf', {
        ...form,
        client_id: form.client_id || null,
        participant_ids: form.participant_ids
      });
      setForm({ ...form, title: '', description: '', participant_ids: [] });
      onCreated();
    } catch (err) {
      setError(apiError(err));
    }
  };
  return (
    <Form className="tm-ticket-create-form" onSubmit={submit}>
      <div className="tm-form-title">
        <h2>Přidat ticket za partnera</h2>
        <p>Vytvoří běžný partnerský ticket s vybranou odpovědnou osobou jako vlastníkem.</p>
      </div>
      <ErrorBanner error={error} />
      <div className="tm-ticket-form-grid">
        <FormGroup>
          <Label>Partner</Label>
          <Input type="select" value={form.partner_id} onChange={(event) => updatePartner(event.target.value)} required>
            <option value="">Vyberte partnera</option>
            {partnerRows.map((partner) => <option key={partner.id} value={partner.id}>{partner.name}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Vlastník ticketu</Label>
          <Input type="select" value={form.owner_id} onChange={(event) => update('owner_id', event.target.value)} required disabled={!form.partner_id}>
            <option value="">Vyberte odpovědnou osobu</option>
            {owners.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Participanti</Label>
          <Input
            className="tm-multi-select"
            type="select"
            multiple
            value={form.participant_ids}
            disabled={!form.partner_id}
            onChange={(event) => update('participant_ids', Array.from(event.target.selectedOptions).map((option) => option.value))}
          >
            {participantOptions.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
          </Input>
        </FormGroup>
      </div>
      <TicketFormFields form={form} update={update} meta={meta} clients={clientRows} />
      <div className="tm-form-actions">
        <Button color="primary" type="submit" disabled={!form.partner_id || !form.owner_id || !form.title.trim() || !form.description.trim()}>
          <i className="bi bi-plus-circle me-1" />
          Vytvořit ticket za partnera
        </Button>
      </div>
    </Form>
  );
}

export function TicketFormFields({ form, update, meta, clients = [] }) {
  const ticketTypes = asArray(meta?.ticket_types);
  const priorities = asArray(meta?.priorities);
  const clientRows = asArray(clients);
  return (
    <div className="tm-ticket-form-grid">
      <FormGroup>
        <Label>Typ</Label>
        <Input type="select" value={form.type} onChange={(event) => update('type', event.target.value)}>
          {ticketTypes.map((ticketType) => <option key={ticketType}>{ticketType}</option>)}
        </Input>
      </FormGroup>
      <FormGroup>
        <Label>Priorita</Label>
        <Input type="select" value={form.priority} onChange={(event) => update('priority', event.target.value)}>
          {priorities.map((priority) => <option key={priority}>{priority}</option>)}
        </Input>
      </FormGroup>
      {clientRows.length > 0 && (
        <FormGroup>
          <Label>Klient</Label>
          <Input type="select" value={form.client_id} onChange={(event) => update('client_id', event.target.value)}>
            <option value="">Bez klienta</option>
            {clientRows.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
          </Input>
        </FormGroup>
      )}
      <FormGroup className="tm-field-wide">
        <Label>Název</Label>
        <Input value={form.title} onChange={(event) => update('title', event.target.value)} required />
      </FormGroup>
      <FormGroup className="tm-field-wide">
        <Label>Popis</Label>
        <Input type="textarea" rows="8" value={form.description} onChange={(event) => update('description', event.target.value)} required />
        <div className="tm-muted tm-field-help">Podporuje Markdown (nadpisy, seznamy, odkazy, tučné písmo, kód).</div>
        <div className="tm-markdown-preview">
          <div className="tm-markdown-preview-head">Náhled markdownu</div>
          <MarkdownText
            content={form.description}
            className="tm-markdown tm-markdown-preview-body"
            emptyMessage="Náhled se zobrazí po vyplnění popisu."
          />
        </div>
      </FormGroup>
    </div>
  );
}
