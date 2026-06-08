import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Form,
  FormGroup,
  Input,
  Label,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Table
} from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { EmptyRow, ErrorBanner, PageHeader, apiError, roleLabel } from './helpers.jsx';

export default function AdminScreen() {
  return (
    <AuthGate>
      {(user) => <Admin user={user} />}
    </AuthGate>
  );
}

function Admin({ user }) {
  const [partners, setPartners] = useState([]);
  const [clients, setClients] = useState([]);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');
  const [partnerName, setPartnerName] = useState('');
  const [clientForm, setClientForm] = useState({ partner_id: '', name: '' });
  const [internalUser, setInternalUser] = useState({ email: '', name: '', role: 'L1' });
  const [partnerUser, setPartnerUser] = useState({ partner_id: '', email: '', name: '', role: 'responsible' });
  const [assignment, setAssignment] = useState({ client_id: '', user_id: '' });
  const [editingClient, setEditingClient] = useState(null);
  const [editingUser, setEditingUser] = useState(null);
  const [userActionMessage, setUserActionMessage] = useState('');
  const [directoryView, setDirectoryView] = useState('clients');
  const [activeAction, setActiveAction] = useState('client');
  const [directoryFilters, setDirectoryFilters] = useState({
    search: '',
    partner_id: '',
    active: 'active',
    user_kind: '',
    role: ''
  });

  const load = async () => {
    setError('');
    try {
      const [partnersResponse, clientsResponse, usersResponse] = await Promise.all([
        api.get('/partners'),
        api.get('/clients'),
        api.get('/users')
      ]);
      setPartners(partnersResponse.data);
      setClients(clientsResponse.data);
      setUsers(usersResponse.data);
    } catch (err) {
      setError(apiError(err));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const partnerNames = useMemo(() => new Map(partners.map((partner) => [partner.id, partner.name])), [partners]);
  const filteredPartners = useMemo(() => filterPartners(partners, directoryFilters), [partners, directoryFilters]);
  const filteredClients = useMemo(() => filterClients(clients, partnerNames, directoryFilters), [clients, partnerNames, directoryFilters]);
  const filteredUsers = useMemo(() => filterUsers(users, partnerNames, directoryFilters), [users, partnerNames, directoryFilters]);
  const selectedAssignmentClient = useMemo(
    () => clients.find((client) => client.id === assignment.client_id),
    [clients, assignment.client_id]
  );
  const selectedAssignmentClientExists = useMemo(
    () => clients.some((client) => client.id === assignment.client_id),
    [clients, assignment.client_id]
  );
  const assignmentResponsibleUsers = useMemo(
    () => selectedAssignmentClient
      ? users.filter((row) => (
        row.active
        && row.kind === 'partner'
        && row.partner_role === 'responsible'
        && row.partner_id === selectedAssignmentClient.partner_id
      ))
      : [],
    [users, selectedAssignmentClient]
  );

  useEffect(() => {
    if (assignment.client_id && !selectedAssignmentClient && selectedAssignmentClientExists) {
      setAssignment({ client_id: '', user_id: '' });
    }
  }, [assignment.client_id, selectedAssignmentClient, selectedAssignmentClientExists]);

  useEffect(() => {
    if (!assignment.user_id) return;
    const selectedUserIsAllowed = assignmentResponsibleUsers.some((row) => row.id === assignment.user_id);
    if (!selectedUserIsAllowed) {
      setAssignment((current) => ({ ...current, user_id: '' }));
    }
  }, [assignment.user_id, assignmentResponsibleUsers]);

  if (user.kind !== 'internal' || !['Admin', 'DeliveryManager'].includes(user.internal_role)) {
    return <div className="tm-screen"><ErrorBanner error="Admin section is available only to Admin and Delivery Manager users." /></div>;
  }

  const submit = async (fn) => {
    setError('');
    try {
      await fn();
      await load();
    } catch (err) {
      setError(apiError(err));
    }
  };

  const saveClient = (payload) => submit(async () => {
    await api.patch(`/clients/${editingClient.id}`, payload);
    setEditingClient(null);
  });

  const saveUser = (payload) => submit(async () => {
    await api.patch(`/users/${editingUser.id}`, payload);
    setEditingUser(null);
  });

  const deleteUser = (row) => {
    if (!window.confirm(`Deactivate user "${row.email}"?`)) return;
    submit(() => api.delete(`/users/${row.id}`));
  };

  const sendPasswordReset = (row) => submit(async () => {
    const response = await api.post(`/users/${row.id}/password-reset`);
    setUserActionMessage(`Password reset e-mail queued for ${row.email}. Dev token: ${response.data.reset_token}`);
  });

  return (
    <div className="tm-screen">
      <PageHeader
        title="Admin"
        actions={(
          <Button outline color="primary" onClick={load} title="Refresh administration data">
            <i className="bi bi-arrow-clockwise" />
          </Button>
        )}
      />
      <ErrorBanner error={error} />
      <div className="tm-admin-layout">
        <section className="tm-panel tm-admin-directory">
          <DirectoryPanel
            view={directoryView}
            setView={setDirectoryView}
            filters={directoryFilters}
            setFilters={setDirectoryFilters}
            partners={partners}
            partnerRows={filteredPartners}
            clientRows={filteredClients}
            userRows={filteredUsers}
            counts={{ partners: partners.length, clients: clients.length, users: users.length }}
            currentUser={user}
            onEditClient={setEditingClient}
            onEditUser={setEditingUser}
            onDeleteUser={deleteUser}
          />
        </section>
        <aside className="tm-panel tm-admin-actions-panel">
          <ActionPanel
            user={user}
            activeAction={activeAction}
            setActiveAction={setActiveAction}
            partners={partners}
            clients={clients}
            partnerName={partnerName}
            setPartnerName={setPartnerName}
            clientForm={clientForm}
            setClientForm={setClientForm}
            internalUser={internalUser}
            setInternalUser={setInternalUser}
            partnerUser={partnerUser}
            setPartnerUser={setPartnerUser}
            assignment={assignment}
            setAssignment={setAssignment}
            selectedAssignmentClient={selectedAssignmentClient}
            assignmentResponsibleUsers={assignmentResponsibleUsers}
            submit={submit}
          />
        </aside>
      </div>
      <ClientEditModal
        client={editingClient}
        users={users}
        isOpen={Boolean(editingClient)}
        onClose={() => setEditingClient(null)}
        onSave={saveClient}
        submit={submit}
      />
      <UserEditModal
        currentUser={user}
        userRow={editingUser}
        isOpen={Boolean(editingUser)}
        onClose={() => setEditingUser(null)}
        onSave={saveUser}
        onPasswordReset={sendPasswordReset}
        actionMessage={userActionMessage}
        clearActionMessage={() => setUserActionMessage('')}
      />
    </div>
  );
}

function PartnerSelect({ partners, value, onChange }) {
  return (
    <FormGroup>
      <Label>Partner</Label>
      <Input type="select" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select partner</option>
        {partners.map((partner) => <option key={partner.id} value={partner.id}>{partner.name}</option>)}
      </Input>
    </FormGroup>
  );
}

function ActionPanel({
  user,
  activeAction,
  setActiveAction,
  partners,
  clients,
  partnerName,
  setPartnerName,
  clientForm,
  setClientForm,
  internalUser,
  setInternalUser,
  partnerUser,
  setPartnerUser,
  assignment,
  setAssignment,
  selectedAssignmentClient,
  assignmentResponsibleUsers,
  submit
}) {
  const actions = [
    ...(user.internal_role === 'Admin' ? [
      { id: 'partner', label: 'Partner', icon: 'bi-building' },
      { id: 'internal-user', label: 'Internal user', icon: 'bi-person-badge' }
    ] : []),
    { id: 'client', label: 'Client', icon: 'bi-briefcase' },
    { id: 'partner-user', label: 'Partner user', icon: 'bi-person-plus' }
  ];
  const currentAction = actions.some((action) => action.id === activeAction) ? activeAction : actions[0].id;

  return (
    <>
      <div className="tm-admin-action-head">
        <h2>Actions</h2>
      </div>
      <div className="tm-admin-action-picker" aria-label="Admin action">
        {actions.map((action) => (
          <Button
            key={action.id}
            type="button"
            color={currentAction === action.id ? 'primary' : 'secondary'}
            outline={currentAction !== action.id}
            onClick={() => setActiveAction(action.id)}
          >
            <i className={`bi ${action.icon}`} />
            <span>{action.label}</span>
          </Button>
        ))}
      </div>
      <div className="tm-admin-action-form">
        {currentAction === 'partner' && (
          <Form onSubmit={(event) => {
            event.preventDefault();
            submit(async () => {
              await api.post('/partners', { name: partnerName });
              setPartnerName('');
            });
          }}>
            <h3>Create partner</h3>
            <FormGroup>
              <Label>Name</Label>
              <Input value={partnerName} onChange={(event) => setPartnerName(event.target.value)} autoComplete="organization" />
            </FormGroup>
            <Button color="primary" type="submit" className="w-100" disabled={!partnerName.trim()}>
              <i className="bi bi-plus-circle me-1" />
              Create partner
            </Button>
          </Form>
        )}

        {currentAction === 'internal-user' && (
          <Form onSubmit={(event) => {
            event.preventDefault();
            submit(async () => {
              await api.post('/users/internal', internalUser);
              setInternalUser({ email: '', name: '', role: 'L1' });
            });
          }}>
            <h3>Create internal user</h3>
            <FormGroup>
              <Label>E-mail</Label>
              <Input value={internalUser.email} onChange={(event) => setInternalUser({ ...internalUser, email: event.target.value })} autoComplete="email" />
            </FormGroup>
            <FormGroup>
              <Label>Name</Label>
              <Input value={internalUser.name} onChange={(event) => setInternalUser({ ...internalUser, name: event.target.value })} autoComplete="name" />
            </FormGroup>
            <FormGroup>
              <Label>Role</Label>
              <Input type="select" value={internalUser.role} onChange={(event) => setInternalUser({ ...internalUser, role: event.target.value })}>
                {['Admin', 'DeliveryManager', 'L1', 'L2', 'L3'].map((role) => <option key={role} value={role}>{roleLabel(role)}</option>)}
              </Input>
            </FormGroup>
            <Button color="primary" type="submit" className="w-100" disabled={!internalUser.email.trim() || !internalUser.name.trim()}>
              <i className="bi bi-plus-circle me-1" />
              Create user
            </Button>
          </Form>
        )}

        {currentAction === 'client' && (
          <Form onSubmit={(event) => {
            event.preventDefault();
            submit(async () => {
              await api.post('/clients', clientForm);
              setClientForm({ partner_id: '', name: '' });
            });
          }}>
            <h3>Create client</h3>
            <PartnerSelect partners={partners} value={clientForm.partner_id} onChange={(value) => setClientForm({ ...clientForm, partner_id: value })} />
            <FormGroup>
              <Label>Name</Label>
              <Input value={clientForm.name} onChange={(event) => setClientForm({ ...clientForm, name: event.target.value })} autoComplete="organization" />
            </FormGroup>
            <Button color="primary" type="submit" className="w-100" disabled={!clientForm.partner_id || !clientForm.name.trim()}>
              <i className="bi bi-plus-circle me-1" />
              Create client
            </Button>
          </Form>
        )}

        {currentAction === 'partner-user' && (
          <Form onSubmit={(event) => {
            event.preventDefault();
            submit(async () => {
              await api.post('/users/partner', partnerUser);
              setPartnerUser({ partner_id: '', email: '', name: '', role: 'responsible' });
            });
          }}>
            <h3>Invite partner user</h3>
            <PartnerSelect partners={partners} value={partnerUser.partner_id} onChange={(value) => setPartnerUser({ ...partnerUser, partner_id: value })} />
            <FormGroup>
              <Label>E-mail</Label>
              <Input value={partnerUser.email} onChange={(event) => setPartnerUser({ ...partnerUser, email: event.target.value })} autoComplete="email" />
            </FormGroup>
            <FormGroup>
              <Label>Name</Label>
              <Input value={partnerUser.name} onChange={(event) => setPartnerUser({ ...partnerUser, name: event.target.value })} autoComplete="name" />
            </FormGroup>
            <FormGroup>
              <Label>Role</Label>
              <Input type="select" value={partnerUser.role} onChange={(event) => setPartnerUser({ ...partnerUser, role: event.target.value })}>
                <option value="responsible">Odpovědná osoba</option>
                <option value="technical">Technická osoba</option>
              </Input>
            </FormGroup>
            <Button color="primary" type="submit" className="w-100" disabled={!partnerUser.partner_id || !partnerUser.email.trim() || !partnerUser.name.trim()}>
              <i className="bi bi-envelope-plus me-1" />
              Invite user
            </Button>
          </Form>
        )}

        {currentAction === 'assignment' && (
          <Form onSubmit={(event) => {
            event.preventDefault();
            submit(() => api.post('/client-assignments', assignment));
          }}>
            <h3>Přiřadit odpovědnou osobu</h3>
            <FormGroup>
              <Label>Client</Label>
              <Input type="select" value={assignment.client_id} onChange={(event) => setAssignment({ client_id: event.target.value, user_id: '' })}>
                <option value="">Select client</option>
                {clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
              </Input>
            </FormGroup>
            <FormGroup>
              <Label>User</Label>
              <Input
                type="select"
                value={assignment.user_id}
                disabled={!selectedAssignmentClient || assignmentResponsibleUsers.length === 0}
                onChange={(event) => setAssignment({ ...assignment, user_id: event.target.value })}
              >
                <option value="">
                  {selectedAssignmentClient ? 'Select responsible user' : 'Select client first'}
                </option>
                {assignmentResponsibleUsers.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </Input>
            </FormGroup>
            <Button color="primary" type="submit" className="w-100" disabled={!assignment.client_id || !assignment.user_id}>
              <i className="bi bi-check2-circle me-1" />
              Assign
            </Button>
          </Form>
        )}
      </div>
    </>
  );
}

function DirectoryPanel({
  view,
  setView,
  filters,
  setFilters,
  partners,
  partnerRows,
  clientRows,
  userRows,
  counts,
  currentUser,
  onEditClient,
  onEditUser,
  onDeleteUser
}) {
  const updateFilter = (key, value) => setFilters({ ...filters, [key]: value });
  const resetFilters = () => setFilters({ search: '', partner_id: '', active: 'active', user_kind: '', role: '' });
  const visibleCount = view === 'partners' ? partnerRows.length : view === 'clients' ? clientRows.length : userRows.length;
  return (
    <>
      <div className="tm-admin-directory-head">
        <div>
          <h2>Directory</h2>
          <div className="tm-muted">{visibleCount} shown</div>
        </div>
        <div className="tm-segmented" aria-label="Directory view">
          <Button size="sm" color={view === 'partners' ? 'primary' : 'secondary'} outline={view !== 'partners'} onClick={() => setView('partners')}>
            Partners <span>{counts.partners}</span>
          </Button>
          <Button size="sm" color={view === 'clients' ? 'primary' : 'secondary'} outline={view !== 'clients'} onClick={() => setView('clients')}>
            Clients <span>{counts.clients}</span>
          </Button>
          <Button size="sm" color={view === 'users' ? 'primary' : 'secondary'} outline={view !== 'users'} onClick={() => setView('users')}>
            Users <span>{counts.users}</span>
          </Button>
        </div>
      </div>
      <div className="tm-admin-filters">
        <FormGroup>
          <Label>Search</Label>
          <Input
            value={filters.search}
            onChange={(event) => updateFilter('search', event.target.value)}
            placeholder={view === 'users' ? 'Name, e-mail, role' : 'Name or key'}
          />
        </FormGroup>
        {view !== 'partners' && (
          <FormGroup>
            <Label>Partner</Label>
            <Input type="select" value={filters.partner_id} onChange={(event) => updateFilter('partner_id', event.target.value)}>
              <option value="">Any</option>
              {partners.map((partner) => <option key={partner.id} value={partner.id}>{partner.name}</option>)}
            </Input>
          </FormGroup>
        )}
        {view === 'users' && (
          <>
            <FormGroup>
              <Label>Status</Label>
              <Input type="select" value={filters.active} onChange={(event) => updateFilter('active', event.target.value)}>
                <option value="">Any</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </Input>
            </FormGroup>
            <FormGroup>
              <Label>Kind</Label>
              <Input type="select" value={filters.user_kind} onChange={(event) => updateFilter('user_kind', event.target.value)}>
                <option value="">Any</option>
                <option value="internal">Internal</option>
                <option value="partner">Partner</option>
              </Input>
            </FormGroup>
            <FormGroup>
              <Label>Role</Label>
              <Input type="select" value={filters.role} onChange={(event) => updateFilter('role', event.target.value)}>
                <option value="">Any</option>
                {['Admin', 'DeliveryManager', 'L1', 'L2', 'L3', 'responsible', 'technical'].map((role) => <option key={role} value={role}>{roleLabel(role)}</option>)}
              </Input>
            </FormGroup>
          </>
        )}
        <div className="tm-admin-filter-reset">
          <Button outline color="secondary" type="button" onClick={resetFilters}>
            <i className="bi bi-x-circle" />
          </Button>
        </div>
      </div>
      {view === 'partners' && <PartnersTable rows={partnerRows} />}
      {view === 'clients' && <ClientsTable rows={clientRows} partners={partners} onEdit={onEditClient} />}
      {view === 'users' && <UsersTable rows={userRows} partners={partners} currentUser={currentUser} onEdit={onEditUser} onDelete={onDeleteUser} />}
    </>
  );
}

function PartnersTable({ rows }) {
  return (
    <div className="tm-table-wrap">
      <Table hover responsive className="tm-table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Name</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.key}</td>
              <td>{row.name}</td>
            </tr>
          ))}
          {rows.length === 0 && <EmptyRow colSpan="2" title="No partners found" message="Try changing the directory filters." />}
        </tbody>
      </Table>
    </div>
  );
}

function ClientsTable({ rows, partners, onEdit }) {
  const partnerNames = useMemo(() => new Map(partners.map((partner) => [partner.id, partner.name])), [partners]);
  return (
    <div className="tm-table-wrap">
      <Table hover responsive className="tm-table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Name</th>
            <th>Partner</th>
            <th className="text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.key}</td>
              <td>{row.name}</td>
              <td>{partnerNames.get(row.partner_id) || row.partner_id}</td>
              <td className="text-end">
                <Button size="sm" outline color="secondary" title="Edit client" onClick={() => onEdit(row)}>
                  <i className="bi bi-pencil" />
                </Button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && <EmptyRow colSpan="4" title="No clients found" message="Try changing the directory filters." />}
        </tbody>
      </Table>
    </div>
  );
}

function UsersTable({ rows, partners, currentUser, onEdit, onDelete }) {
  const partnerNames = useMemo(() => new Map(partners.map((partner) => [partner.id, partner.name])), [partners]);
  return (
    <div className="tm-table-wrap">
      <Table hover responsive className="tm-table">
        <thead>
          <tr>
            <th>E-mail</th>
            <th>Name</th>
            <th>Kind</th>
            <th>Role</th>
            <th>Partner</th>
            <th>Active</th>
            <th className="text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const canManage = currentUser.internal_role === 'Admin' || row.kind === 'partner';
            return (
              <tr key={row.id}>
                <td>{row.email}</td>
                <td>{row.name}</td>
                <td>{row.kind}</td>
                <td>{roleLabel(userRole(row))}</td>
                <td>{row.partner_id ? partnerNames.get(row.partner_id) || row.partner_id : '-'}</td>
                <td><ActiveBadge active={row.active} /></td>
                <td className="text-end">
                  <div className="d-inline-flex gap-2">
                    <Button size="sm" outline color="secondary" title="Edit user" disabled={!canManage} onClick={() => onEdit(row)}>
                      <i className="bi bi-pencil" />
                    </Button>
                    <Button
                      size="sm"
                      outline
                      color="danger"
                      title="Deactivate user"
                      disabled={!canManage || !row.active || row.id === currentUser.id}
                      onClick={() => onDelete(row)}
                    >
                      <i className="bi bi-trash" />
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
          {rows.length === 0 && <EmptyRow colSpan="7" title="No users found" message="Try changing the directory filters." />}
        </tbody>
      </Table>
    </div>
  );
}

function ClientEditModal({ client, users, isOpen, onClose, onSave, submit: runAdminAction }) {
  const [form, setForm] = useState({ name: '' });
  const [assignments, setAssignments] = useState([]);
  const [responsibleUserId, setResponsibleUserId] = useState('');

  useEffect(() => {
    setForm({ name: client?.name || '' });
    setResponsibleUserId('');
    if (!client) {
      setAssignments([]);
      return;
    }
    api.get('/client-assignments', { params: { client_id: client.id } })
      .then((response) => setAssignments(response.data))
      .catch(() => setAssignments([]));
  }, [client]);

  const eligibleUsers = users.filter((row) => (
    row.active
    && row.kind === 'partner'
    && row.partner_role === 'responsible'
    && row.partner_id === client?.partner_id
    && !assignments.some((assignment) => assignment.user_id === row.id)
  ));

  const reloadAssignments = async () => {
    const response = await api.get('/client-assignments', { params: { client_id: client.id } });
    setAssignments(response.data);
  };

  const submit = (event) => {
    event.preventDefault();
    onSave({ name: form.name.trim() });
  };

  return (
    <Modal isOpen={isOpen} toggle={onClose}>
      <Form onSubmit={submit}>
        <ModalHeader toggle={onClose}>Edit client</ModalHeader>
        <ModalBody>
          <FormGroup>
            <Label>Name</Label>
            <Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
          </FormGroup>
          <hr />
          <div className="tm-client-responsibles">
            <h3>Odpovědné osoby</h3>
            {assignments.map((assignment) => (
              <div className="tm-responsible-row" key={assignment.id}>
                <div>
                  <strong>{assignment.user?.name || assignment.user_id}</strong>
                  <div className="tm-muted">{assignment.user?.email}</div>
                </div>
                <Button
                  size="sm"
                  outline
                  color="danger"
                  type="button"
                  onClick={() => runAdminAction(async () => {
                    await api.delete(`/client-assignments/${assignment.id}`);
                    await reloadAssignments();
                  })}
                >
                  <i className="bi bi-x-lg" />
                </Button>
              </div>
            ))}
            {assignments.length === 0 && <div className="tm-muted mb-2">No responsible users assigned.</div>}
            <div className="d-flex gap-2">
              <Input type="select" value={responsibleUserId} onChange={(event) => setResponsibleUserId(event.target.value)}>
                <option value="">Add responsible user</option>
                {eligibleUsers.map((row) => <option key={row.id} value={row.id}>{row.name} ({row.email})</option>)}
              </Input>
              <Button
                outline
                color="secondary"
                type="button"
                disabled={!responsibleUserId}
                onClick={() => runAdminAction(async () => {
                  await api.post('/client-assignments', { client_id: client.id, user_id: responsibleUserId });
                  setResponsibleUserId('');
                  await reloadAssignments();
                })}
              >
                <i className="bi bi-person-plus" />
              </Button>
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button outline color="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button color="primary" type="submit" disabled={!form.name.trim()}>Save</Button>
        </ModalFooter>
      </Form>
    </Modal>
  );
}

function UserEditModal({ userRow, currentUser, isOpen, onClose, onSave, onPasswordReset, actionMessage, clearActionMessage }) {
  const [form, setForm] = useState({ email: '', name: '', role: '', active: true });
  const roleOptions = userRow?.kind === 'internal'
    ? ['Admin', 'DeliveryManager', 'L1', 'L2', 'L3']
    : ['responsible', 'technical'];
  const isCurrentUser = userRow?.id === currentUser.id;

  useEffect(() => {
    clearActionMessage();
    setForm({
      email: userRow?.email || '',
      name: userRow?.name || '',
      role: userRow ? userRole(userRow) : '',
      active: userRow?.active ?? true
    });
  }, [userRow]);

  const submit = (event) => {
    event.preventDefault();
    onSave({
      email: form.email.trim(),
      name: form.name.trim(),
      role: form.role,
      active: form.active
    });
  };

  return (
    <Modal isOpen={isOpen} toggle={onClose}>
      <Form onSubmit={submit}>
        <ModalHeader toggle={onClose}>Edit user</ModalHeader>
        <ModalBody>
          <FormGroup>
            <Label>E-mail</Label>
            <Input value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
          </FormGroup>
          <FormGroup>
            <Label>Name</Label>
            <Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
          </FormGroup>
          <FormGroup>
            <Label>Role</Label>
            <Input type="select" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
              {roleOptions.map((role) => <option key={role} value={role}>{roleLabel(role)}</option>)}
            </Input>
          </FormGroup>
          <div className="tm-switch-row">
            <span>Active</span>
            <button
              type="button"
              className={`tm-switch ${form.active ? 'is-on' : ''}`}
              disabled={isCurrentUser}
              role="switch"
              aria-checked={form.active}
              onClick={() => setForm({ ...form, active: !form.active })}
            >
              <span />
            </button>
          </div>
          {actionMessage && <div className="alert alert-info tm-alert py-2 mt-3">{actionMessage}</div>}
        </ModalBody>
        <ModalFooter>
          <Button outline color="secondary" type="button" disabled={!userRow?.active} onClick={() => onPasswordReset(userRow)}>
            <i className="bi bi-envelope-lock me-1" />
            Odeslat reset hesla
          </Button>
          <Button outline color="secondary" type="button" onClick={onClose}>Cancel</Button>
          <Button color="primary" type="submit" disabled={!form.email.trim() || !form.name.trim() || !form.role}>Save</Button>
        </ModalFooter>
      </Form>
    </Modal>
  );
}

function ActiveBadge({ active }) {
  return <span className={`badge ${active ? 'text-bg-success' : 'text-bg-secondary'}`}>{active ? 'active' : 'inactive'}</span>;
}

function userRole(row) {
  return row.kind === 'internal' ? row.internal_role : row.partner_role;
}

function filterPartners(rows, filters) {
  return rows.filter((row) => matchesSearch([row.key, row.name], filters.search));
}

function filterClients(rows, partnerNames, filters) {
  return rows.filter((row) => (
    (!filters.partner_id || row.partner_id === filters.partner_id)
    && matchesSearch([row.key, row.name, partnerNames.get(row.partner_id)], filters.search)
  ));
}

function filterUsers(rows, partnerNames, filters) {
  return rows.filter((row) => {
    const role = userRole(row);
    return (
      matchesActive(row, filters.active)
      && (!filters.partner_id || row.partner_id === filters.partner_id)
      && (!filters.user_kind || row.kind === filters.user_kind)
      && (!filters.role || role === filters.role)
      && matchesSearch([row.email, row.name, row.kind, role, partnerNames.get(row.partner_id)], filters.search)
    );
  });
}

function matchesActive(row, value) {
  if (!value) return true;
  return value === 'active' ? row.active : !row.active;
}

function matchesSearch(values, search) {
  const needle = normalize(search);
  if (!needle) return true;
  return values.some((value) => normalize(value).includes(needle));
}

function normalize(value) {
  return String(value || '').toLocaleLowerCase();
}
