import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router';
import {
  Button,
  Form,
  FormGroup,
  Input,
  Label,
  Table
} from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { EmptyRow, EmptyState, ErrorBanner, Loading, PageHeader, StatusPill, TimeCell, apiError } from './helpers.jsx';

export default function TicketDetailScreen() {
  return (
    <AuthGate>
      {(user) => <TicketDetail user={user} />}
    </AuthGate>
  );
}

function TicketDetail({ user }) {
  const { ticketId } = useParams();
  const [ticket, setTicket] = useState(null);
  const [comments, setComments] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [users, setUsers] = useState([]);
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState('');
  const [commentBody, setCommentBody] = useState('');
  const [internalNoteBody, setInternalNoteBody] = useState('');
  const [assignment, setAssignment] = useState({ team: 'L1', assignee: '' });
  const [transferOwner, setTransferOwner] = useState('');
  const [participantId, setParticipantId] = useState('');
  const [uploadFile, setUploadFile] = useState(null);

  const load = async () => {
    setError('');
    try {
      const [ticketResponse, commentsResponse, attachmentsResponse, metaResponse, usersResponse] = await Promise.all([
        api.get(`/tickets/${ticketId}`),
        api.get(`/tickets/${ticketId}/comments`),
        api.get(`/tickets/${ticketId}/attachments`),
        api.get('/meta'),
        api.get('/users').catch(() => ({ data: [] }))
      ]);
      setTicket(ticketResponse.data);
      setComments(commentsResponse.data);
      setAttachments(attachmentsResponse.data);
      setMeta(metaResponse.data);
      setUsers(usersResponse.data);
      setAssignment({ team: ticketResponse.data.resolver_team || 'L1', assignee: ticketResponse.data.assignee_id || '' });
    } catch (err) {
      setError(apiError(err));
    }
  };

  useEffect(() => {
    load();
  }, [ticketId]);

  const action = async (fn) => {
    setError('');
    try {
      await fn();
      await load();
    } catch (err) {
      setError(apiError(err));
    }
  };

  if (!ticket && !error) return <Loading />;

  const internalUsers = users.filter((row) => row.kind === 'internal');
  const partnerUsers = users.filter((row) => row.kind === 'partner' && row.partner_id === ticket?.partner_id);
  const responsibleUsers = partnerUsers.filter((row) => row.partner_role === 'responsible');
  const availableTransitions = asArray(ticket?.available_transitions);
  const participants = asArray(ticket?.participants);
  const participantIds = participants.map((participant) => participant.id);
  const resolverTeams = asArray(meta?.resolver_teams);
  const assignmentTeam = ticket?.resolver_team || assignment.team;
  const canTransferOwner = !ticket?.internal && !ticket?.system && responsibleUsers.length > 0;
  const canManageParticipants = ticket?.system
    ? user.kind === 'partner' && user.partner_role === 'responsible'
    : !ticket?.internal && (user.kind === 'internal' || ticket?.owner_id === user.id);
  const showActions = user.kind === 'internal' || canTransferOwner;
  const canAddCommunication = ticket?.status !== 'Closed' && (
    user.kind === 'internal'
    || (ticket?.system && user.partner_role === 'responsible')
    || (!ticket?.system && participantIds.includes(user.id))
  );
  const canAssignTicket = ticket?.status !== 'Closed';
  const canReturnToQueue = canAssignTicket
    && user.kind === 'internal'
    && ['Admin', 'DeliveryManager'].includes(user.internal_role)
    && Boolean(ticket?.resolver_team)
    && Boolean(ticket?.assignee_id);

  return (
    <div className="tm-screen">
      <PageHeader
        title={ticket?.title || 'Ticket detail'}
        actions={(
          <Button outline color="primary" onClick={load} title="Refresh ticket">
            <i className="bi bi-arrow-clockwise" />
          </Button>
        )}
      />
      <ErrorBanner error={error} />
      {ticket && (
        <div className="tm-ticket-layout">
          <main className="tm-ticket-main">
            <section className="tm-panel">
              <div className="tm-ticket-title-row">
                <div>
                  <div className="tm-muted">Current status</div>
                  <StatusPill value={ticket.status} />
                </div>
                <StatusPill value={ticket.priority} priority={ticket.priority} />
              </div>
              <h2>Description</h2>
              <p className="tm-ticket-description">{ticket.description}</p>
            </section>
            <section className="tm-panel">
              <h2>Communication</h2>
              <CommentList comments={comments} />
              {canAddCommunication && (
                <CommentForm
                  title="Add comment"
                  value={commentBody}
                  setValue={setCommentBody}
                  onSubmit={() => action(async () => {
                    await api.post(`/tickets/${ticket.id}/comments`, { body: commentBody });
                    setCommentBody('');
                  })}
                />
              )}
              {canAddCommunication && user.kind === 'internal' && (
                <CommentForm
                  title="Internal note"
                  value={internalNoteBody}
                  setValue={setInternalNoteBody}
                  onSubmit={() => action(async () => {
                    await api.post(`/tickets/${ticket.id}/internal-notes`, { body: internalNoteBody });
                    setInternalNoteBody('');
                  })}
                />
              )}
            </section>
          </main>
          <aside className="tm-ticket-side">
            <section className="tm-panel">
              <h2>Metadata</h2>
              <Table borderless responsive size="sm" className="tm-meta-table">
                <tbody>
                  <InfoRow label="ID" value={ticket.id} />
                  <InfoRow label="Kind" value={ticket.kind || (ticket.system ? 'system' : (ticket.internal ? 'internal' : 'partner'))} />
                  <InfoRow label="Type" value={ticket.type} />
                  <InfoRow label="Partner" value={ticket.partner_name || '-'} />
                  <InfoRow label="Client" value={ticket.client_name || '-'} />
                  <InfoRow label="Owner" value={ticket.owner_name || '-'} />
                  {user.kind === 'internal' && <InfoRow label="Resolver team" value={ticket.resolver_team || '-'} />}
                  {user.kind === 'internal' && <InfoRow label="Assignee" value={ticket.assignee_name || '-'} />}
                  {user.kind === 'internal' && <InfoRow label="GitLab" value={ticket.gitlab_link ? <a href={ticket.gitlab_link}>{ticket.gitlab_status || 'Open'}</a> : (ticket.gitlab_status || '-')} />}
                  <InfoRow label="Created" value={<TimeCell value={ticket.created_at} />} />
                  <InfoRow label="Updated" value={<TimeCell value={ticket.updated_at} />} />
                </tbody>
              </Table>
            </section>
            {showActions && (
              <section className="tm-panel">
                <h2>Actions</h2>
                {user.kind === 'internal' && (
                  <>
                    <div className="tm-action-group">
                      <div className="tm-action-group-head">
                        <h3>Status</h3>
                        <StatusPill value={ticket.status} />
                      </div>
                      <div className="tm-actions">
                        {availableTransitions.map((status) => (
                          <Button key={status} size="sm" outline color="primary" onClick={() => action(() => api.post(`/tickets/${ticket.id}/transition`, { status }))}>
                            {status}
                          </Button>
                        ))}
                        {availableTransitions.length === 0 && <span className="tm-muted">No status changes available.</span>}
                      </div>
                    </div>
                    {canAssignTicket && <div className="tm-action-group">
                      <h3>Assignment</h3>
                      <Form onSubmit={(event) => {
                        event.preventDefault();
                        action(() => api.post(`/tickets/${ticket.id}/assign`, { ...assignment, team: assignmentTeam }));
                      }}>
                        <FormGroup>
                          <Label>Resolver team</Label>
                          {ticket.resolver_team ? (
                            <div className="tm-readonly-field">{ticket.resolver_team}</div>
                          ) : (
                            <Input type="select" value={assignment.team} onChange={(event) => setAssignment({ ...assignment, team: event.target.value })}>
                              {resolverTeams.map((team) => <option key={team}>{team}</option>)}
                            </Input>
                          )}
                        </FormGroup>
                        <FormGroup>
                          <Label>Assignee</Label>
                          <Input type="select" value={assignment.assignee || ''} onChange={(event) => setAssignment({ ...assignment, assignee: event.target.value })}>
                            <option value="">Unassigned</option>
                            {internalUsers.filter((row) => row.internal_role === assignmentTeam).map((row) => <option key={row.id} value={row.email}>{row.name}</option>)}
                          </Input>
                        </FormGroup>
                        <Button color="primary" className="w-100" type="submit">
                          <i className="bi bi-diagram-3 me-1" />
                          Assign
                        </Button>
                      </Form>
                      {canReturnToQueue && (
                        <Button
                          color="secondary"
                          outline
                          className="w-100 mt-2"
                          type="button"
                          onClick={() => action(() => api.post(`/tickets/${ticket.id}/unassign`))}
                        >
                          <i className="bi bi-arrow-counterclockwise me-1" />
                          Return to queue
                        </Button>
                      )}
                    </div>}
                  </>
                )}
                {canTransferOwner && (
                  <div className="tm-action-group">
                    <h3>Transfer owner</h3>
                    <Form onSubmit={(event) => {
                      event.preventDefault();
                      action(() => api.post(`/tickets/${ticket.id}/transfer-owner`, { new_owner: transferOwner }));
                    }}>
                      <FormGroup>
                        <Label>New owner</Label>
                        <Input type="select" value={transferOwner} onChange={(event) => setTransferOwner(event.target.value)}>
                          <option value="">Select owner</option>
                          {responsibleUsers.map((row) => <option key={row.id} value={row.email}>{row.name}</option>)}
                        </Input>
                      </FormGroup>
                      <Button color="secondary" outline type="submit" disabled={!transferOwner} className="w-100">
                        <i className="bi bi-arrow-left-right me-1" />
                        Transfer
                      </Button>
                    </Form>
                  </div>
                )}
              </section>
            )}
            <section className="tm-panel">
              <h2>Participants</h2>
              <div className="mb-3">
                {participants.map((participant) => (
                  <span className="badge text-bg-light border me-1 mb-1" key={participant.id}>{participant.name}</span>
                ))}
                {participants.length === 0 && <span className="tm-muted">No participants.</span>}
              </div>
              {canManageParticipants && partnerUsers.length > 0 && (
                <Form className="d-flex gap-2" onSubmit={(event) => {
                  event.preventDefault();
                  action(() => api.post(`/tickets/${ticket.id}/participants`, { user_id: participantId }));
                }}>
                  <Input type="select" value={participantId} onChange={(event) => setParticipantId(event.target.value)}>
                    <option value="">Add participant</option>
                    {partnerUsers.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                  </Input>
                  <Button color="secondary" outline type="submit" disabled={!participantId}>
                    <i className="bi bi-person-plus" />
                  </Button>
                </Form>
              )}
            </section>
            <section className="tm-panel">
              <AttachmentPanel
                attachments={attachments}
                uploadFile={uploadFile}
                setUploadFile={setUploadFile}
                canUpload={canAddCommunication}
                onUpload={() => action(async () => {
                  const formData = new FormData();
                  formData.append('file', uploadFile);
                  await api.post(`/tickets/${ticket.id}/attachments`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
                  setUploadFile(null);
                })}
              />
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <tr>
      <th className="tm-muted tm-meta-label">{label}</th>
      <td>{value}</td>
    </tr>
  );
}

function AttachmentPanel({ attachments, uploadFile, setUploadFile, canUpload, onUpload }) {
  return (
    <div className="mb-3">
      <h3>Attachments</h3>
      <div className="tm-table-wrap mb-2">
        <Table size="sm" responsive className="tm-table">
          <thead>
            <tr>
              <th>File</th>
              <th>Size</th>
              <th>Uploaded by</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {attachments.map((attachment) => (
              <tr key={attachment.id}>
                <td><a href={attachment.download_url}>{attachment.filename}</a></td>
                <td>{formatBytes(attachment.size_bytes)}</td>
                <td>{attachment.uploaded_by_name || '-'}</td>
                <td><TimeCell value={attachment.created_at} /></td>
              </tr>
            ))}
            {attachments.length === 0 && <EmptyRow colSpan="4" title="No attachments" message="Files uploaded to this ticket will appear here." />}
          </tbody>
        </Table>
      </div>
      {canUpload && (
        <Form className="d-flex gap-2" onSubmit={(event) => {
          event.preventDefault();
          if (uploadFile) onUpload();
        }}>
          <Input type="file" accept=".png,.jpg,.jpeg,.pdf,.txt,.log,.zip" onChange={(event) => setUploadFile(event.target.files?.[0] || null)} />
          <Button color="secondary" outline type="submit" disabled={!uploadFile}>
            <i className="bi bi-upload" />
          </Button>
        </Form>
      )}
    </div>
  );
}

function CommentList({ comments }) {
  return (
    <div className="mb-3">
      <h3>Comments and notes</h3>
      {comments.map((comment) => (
        <div key={comment.id} className="tm-comment">
          <div className="d-flex justify-content-between">
            <div>
              <strong>{comment.author_name || comment.author_id}</strong>
            </div>
            <span className="tm-muted"><TimeCell value={comment.created_at} /></span>
          </div>
          {comment.visibility === 'internal_note' && <span className="badge text-bg-warning mb-1">Internal note</span>}
          <div className="tm-comment-body">{comment.body}</div>
        </div>
      ))}
      {comments.length === 0 && <EmptyState icon="bi-chat-left-text" title="No comments yet" message="Communication on this ticket will appear here." />}
    </div>
  );
}

function formatBytes(size) {
  if (!size) return '0 B';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  return [];
}

function CommentForm({ title, value, setValue, onSubmit }) {
  return (
    <Form className="mb-3" onSubmit={(event) => {
      event.preventDefault();
      onSubmit();
    }}>
      <FormGroup>
        <Label>{title}</Label>
        <Input type="textarea" rows="3" value={value} onChange={(event) => setValue(event.target.value)} />
      </FormGroup>
      <Button color="primary" outline type="submit" disabled={!value.trim()}>
        <i className="bi bi-chat-left-text me-1" />
        Submit
      </Button>
    </Form>
  );
}
