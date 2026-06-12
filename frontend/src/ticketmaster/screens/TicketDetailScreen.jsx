import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useParams } from 'react-router';
import {
  Alert,
  Button,
  Form,
  FormGroup,
  Input,
  Label,
  Table
} from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { usePolling, useRefetchOnFocus } from '../hooks/useLiveRefresh.js';
import { EmptyRow, EmptyState, ErrorBanner, Loading, MarkdownText, PageHeader, StatusPill, TimeCell, apiError, labelValue } from './helpers.jsx';

const TICKET_DETAIL_POLL_MS = 30000;

export default function TicketDetailScreen() {
  return (
    <AuthGate>
      {(user) => <TicketDetail user={user} />}
    </AuthGate>
  );
}

function TicketDetail({ user }) {
  const { ticketId } = useParams();
  const location = useLocation();
  const [ticket, setTicket] = useState(null);
  const [comments, setComments] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [users, setUsers] = useState([]);
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [downloadingAttachmentId, setDownloadingAttachmentId] = useState('');
  const [commentBody, setCommentBody] = useState('');
  const [internalNoteBody, setInternalNoteBody] = useState('');
  const [assignment, setAssignment] = useState({ team: 'L1', assignee: '' });
  const [ticketType, setTicketType] = useState('');
  const [transferOwner, setTransferOwner] = useState('');
  const [participantId, setParticipantId] = useState('');
  const [uploadFile, setUploadFile] = useState(null);

  const load = useCallback(async () => {
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
      setTicketType(ticketResponse.data.type || '');
    } catch (err) {
      setError(apiError(err));
    }
  }, [ticketId]);

  useEffect(() => {
    load();
  }, [load]);

  useRefetchOnFocus(load);
  usePolling(load, TICKET_DETAIL_POLL_MS);

  useEffect(() => {
    if (location.state?.notice) {
      setNotice(location.state.notice);
    }
  }, [location.state]);

  const action = async (fn) => {
    setError('');
    try {
      await fn();
      await load();
    } catch (err) {
      setError(apiError(err));
    }
  };

  const downloadAttachment = async (attachment) => {
    if (!attachment?.id || !attachment?.download_url) return;
    setError('');
    setDownloadingAttachmentId(attachment.id);
    try {
      const response = await api.get(normalizeApiPath(attachment.download_url), { responseType: 'blob' });
      saveDownloadResponse(response, attachment.filename || 'attachment');
    } catch (err) {
      setError(apiError(err));
    } finally {
      setDownloadingAttachmentId('');
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
  const ticketTypes = asArray(meta?.ticket_types);
  const assignmentTeam = ticket?.resolver_team || assignment.team;
  const canTransferOwner = !ticket?.internal && !ticket?.system && responsibleUsers.length > 0;
  const canManageParticipants = ticket?.system
    ? user.kind === 'partner' && user.partner_role === 'responsible'
    : !ticket?.internal && (user.kind === 'internal' || ticket?.owner_id === user.id);
  const canEditTicketType = user.kind === 'internal'
    && ['Admin', 'DeliveryManager'].includes(user.internal_role)
    && ticketTypes.length > 0;
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
  const showPrimaryStatusActions = user.kind === 'internal';
  const showManagementActions = canEditTicketType || canAssignTicket || canTransferOwner;

  return (
    <div className="tm-screen">
      <PageHeader title={ticket?.title || 'Ticket detail'} />
      <ErrorBanner error={error} />
      {notice && (
        <Alert color="warning" className="tm-alert" toggle={() => setNotice('')}>
          {notice}
        </Alert>
      )}
      {ticket && (
        <div className="tm-ticket-layout">
          <main className="tm-ticket-main">
            <section className="tm-panel tm-ticket-summary-panel">
              <div className="tm-ticket-title-row">
                <div className="tm-ticket-summary-pills">
                  <StatusPill value={ticket.status} />
                  <StatusPill value={ticket.priority} priority={ticket.priority} />
                </div>
                <div className="tm-ticket-summary-id tm-muted">{ticket.id}</div>
              </div>
              <div className="tm-ticket-summary-meta tm-muted">
                <span>{labelValue(ticket.type) || '-'}</span>
                <span>{ticket.partner_name || 'No partner'}</span>
                <span>{ticket.owner_name || 'No owner'}</span>
              </div>
              <h2>Description</h2>
              <MarkdownText content={ticket.description} className="tm-markdown tm-ticket-description" />
            </section>
            <section className="tm-panel tm-ticket-communication-panel">
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
            <section className="tm-panel tm-ticket-meta-panel">
              <h2>Overview</h2>
              <div className="tm-meta-list">
                <InfoRow label="ID" value={ticket.id} />
                <InfoRow label="Type" value={labelValue(ticket.type)} />
                <InfoRow label="Status" value={<StatusPill value={ticket.status} />} />
                <InfoRow label="Priority" value={<StatusPill value={ticket.priority} priority={ticket.priority} />} />
                <InfoRow label="Partner" value={ticket.partner_name || '-'} />
                <InfoRow label="Owner" value={ticket.owner_name || '-'} />
                {user.kind === 'internal' && <InfoRow label="Assignee" value={ticket.assignee_name || '-'} />}
                {user.kind === 'internal' && <InfoRow label="Team" value={ticket.resolver_team || '-'} />}
                <InfoRow label="Created" value={<TimeCell value={ticket.created_at} />} />
                <InfoRow label="Updated" value={<TimeCell value={ticket.updated_at} />} />
              </div>
            </section>
            {showActions && (
              <section className="tm-panel tm-ticket-actions-panel">
                <h2>Actions</h2>
                {showPrimaryStatusActions && (
                  <div className="tm-action-group tm-action-group-primary">
                    <div className="tm-action-group-head">
                      <h3>Status</h3>
                      <StatusPill value={ticket.status} />
                    </div>
                    <div className="tm-actions">
                      {availableTransitions.map((status) => (
                        <Button key={status} size="sm" outline color="primary" onClick={() => action(() => api.post(`/tickets/${ticket.id}/transition`, { status }))}>
                          {labelValue(status)}
                        </Button>
                      ))}
                      {availableTransitions.length === 0 && <span className="tm-muted">No status changes are available.</span>}
                    </div>
                  </div>
                )}
                {showManagementActions && (
                  <details className="tm-side-collapsible tm-side-collapsible-management">
                    <summary>Management</summary>
                    <div className="tm-side-collapsible-body">
                      {canEditTicketType && (
                        <div className="tm-action-subgroup">
                          <h3>Ticket type</h3>
                          <Form className="tm-action-form" onSubmit={(event) => {
                            event.preventDefault();
                            action(() => api.post(`/tickets/${ticket.id}/type`, { type: ticketType }));
                          }}>
                            <FormGroup>
                              <Label>Type</Label>
                              <Input type="select" value={ticketType || ticket.type || ''} onChange={(event) => setTicketType(event.target.value)}>
                                {ticketTypes.map((type) => <option key={type} value={type}>{labelValue(type)}</option>)}
                              </Input>
                            </FormGroup>
                            <Button color="secondary" outline type="submit" size="sm" disabled={!ticketType || ticketType === ticket.type} className="w-100">
                              Save
                            </Button>
                          </Form>
                        </div>
                      )}
                      {canAssignTicket && (
                        <div className="tm-action-subgroup">
                          <h3>Assignment</h3>
                          <Form className="tm-action-form" onSubmit={(event) => {
                            event.preventDefault();
                            action(() => api.post(`/tickets/${ticket.id}/assign`, { ...assignment, team: assignmentTeam }));
                          }}>
                            <FormGroup>
                              <Label>Team</Label>
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
                            <Button color="primary" size="sm" className="w-100" type="submit">
                              Save assignment
                            </Button>
                          </Form>
                          {canReturnToQueue && (
                            <Button
                              color="secondary"
                              outline
                              className="w-100 mt-2"
                              size="sm"
                              type="button"
                              onClick={() => action(() => api.post(`/tickets/${ticket.id}/unassign`))}
                            >
                              Return to queue
                            </Button>
                          )}
                        </div>
                      )}
                      {canTransferOwner && (
                        <div className="tm-action-subgroup">
                          <h3>Transfer owner</h3>
                          <Form className="tm-action-form" onSubmit={(event) => {
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
                            <Button color="secondary" outline type="submit" size="sm" disabled={!transferOwner} className="w-100">
                              Transfer
                            </Button>
                          </Form>
                        </div>
                      )}
                    </div>
                  </details>
                )}
              </section>
            )}
            <section className="tm-panel tm-ticket-collab-panel">
              <h2>Participants & attachments</h2>
              <details className="tm-side-collapsible tm-side-collapsible-participants">
                <summary>
                  <span>Participants</span>
                  <span className="tm-side-count">{participants.length}</span>
                </summary>
                <div className="tm-side-collapsible-body">
                  <div className="tm-participant-list">
                    {participants.map((participant) => (
                      <span className="tm-participant-pill" key={participant.id}>{participant.name}</span>
                    ))}
                    {participants.length === 0 && <span className="tm-muted">No participants.</span>}
                  </div>
                  {canManageParticipants && partnerUsers.length > 0 && (
                    <Form className="tm-inline-form tm-inline-form-compact" onSubmit={(event) => {
                      event.preventDefault();
                      action(() => api.post(`/tickets/${ticket.id}/participants`, { user_id: participantId }));
                    }}>
                      <Input type="select" value={participantId} onChange={(event) => setParticipantId(event.target.value)}>
                        <option value="">Add participant</option>
                        {partnerUsers.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                      </Input>
                      <Button color="secondary" outline size="sm" type="submit" disabled={!participantId}>
                        Add
                      </Button>
                    </Form>
                  )}
                </div>
              </details>
              <details className="tm-side-collapsible tm-side-collapsible-attachments">
                <summary>
                  <span>Attachments</span>
                  <span className="tm-side-count">{attachments.length}</span>
                </summary>
                <div className="tm-side-collapsible-body">
                  <AttachmentPanel
                    compact
                    attachments={attachments}
                    uploadFile={uploadFile}
                    setUploadFile={setUploadFile}
                    canUpload={canAddCommunication}
                    downloadingAttachmentId={downloadingAttachmentId}
                    onDownload={downloadAttachment}
                    onUpload={() => action(async () => {
                      const formData = new FormData();
                      formData.append('file', uploadFile);
                      await api.post(`/tickets/${ticket.id}/attachments`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
                      setUploadFile(null);
                    })}
                  />
                </div>
              </details>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="tm-meta-item">
      <div className="tm-meta-item-label">{label}</div>
      <div className="tm-meta-item-value">{value}</div>
    </div>
  );
}

function AttachmentPanel({ compact = false, attachments, uploadFile, setUploadFile, canUpload, onUpload, onDownload, downloadingAttachmentId }) {
  return (
    <div className={compact ? 'tm-attachments-block tm-attachments-block-compact' : 'mb-3'}>
      {!compact && <h3>Attachments</h3>}
      <div className={`tm-table-wrap ${compact ? 'mb-1' : 'mb-2'}`}>
        <Table size="sm" responsive className="tm-table">
          <thead>
            <tr>
              <th>File</th>
              <th>Size</th>
              {!compact && <th>Uploaded by</th>}
              {!compact && <th>Created</th>}
            </tr>
          </thead>
          <tbody>
            {attachments.map((attachment) => (
              <tr key={attachment.id}>
                <td>
                  <Button
                    color="link"
                    className="p-0 align-baseline tm-attachment-name"
                    onClick={() => onDownload(attachment)}
                    disabled={downloadingAttachmentId === attachment.id}
                  >
                    {downloadingAttachmentId === attachment.id ? 'Downloading...' : attachment.filename}
                  </Button>
                </td>
                <td>{formatBytes(attachment.size_bytes)}</td>
                {!compact && <td>{attachment.uploaded_by_name || '-'}</td>}
                {!compact && <td><TimeCell value={attachment.created_at} /></td>}
              </tr>
            ))}
            {attachments.length === 0 && <EmptyRow colSpan={compact ? 2 : 4} title="No attachments" message="Uploaded files for this ticket are listed here." />}
          </tbody>
        </Table>
      </div>
      {canUpload && (
        <Form className={`tm-inline-form ${compact ? 'tm-inline-form-compact' : ''}`} onSubmit={(event) => {
          event.preventDefault();
          if (uploadFile) onUpload();
        }}>
          <Input type="file" accept=".png,.jpg,.jpeg,.pdf,.txt,.log,.zip" onChange={(event) => setUploadFile(event.target.files?.[0] || null)} />
          <Button color="secondary" outline size={compact ? 'sm' : undefined} type="submit" disabled={!uploadFile}>
            Upload
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
          <div className="tm-comment-head">
            <strong className="tm-comment-author">{comment.author_name || comment.author_id}</strong>
            <span className="tm-muted tm-comment-time"><TimeCell value={comment.created_at} /></span>
          </div>
          {comment.visibility === 'internal_note' && <span className="badge text-bg-warning mb-1">Internal note</span>}
          <MarkdownText content={comment.body} className="tm-markdown tm-comment-body" />
        </div>
      ))}
      {comments.length === 0 && <EmptyState icon="bi-chat-left-text" title="No comments yet" message="Ticket communication will appear here." />}
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

function normalizeApiPath(path) {
  if (typeof path !== 'string') return path;
  if (path.startsWith('/api/')) return path.slice(4);
  return path;
}

function saveDownloadResponse(response, fallbackName) {
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

function CommentForm({ title, value, setValue, onSubmit }) {
  const inputRef = useRef(null);

  const setValueWithSelection = (nextValue, selectionStart, selectionEnd) => {
    setValue(nextValue);
    requestAnimationFrame(() => {
      const input = inputRef.current;
      if (!input) return;
      input.focus();
      if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
        input.setSelectionRange(selectionStart, selectionEnd);
      }
    });
  };

  const insertWrapped = (prefix, suffix = '', placeholder = '') => {
    const input = inputRef.current;
    const currentValue = value || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const selectedText = currentValue.slice(selectionStart, selectionEnd);
    const body = selectedText || placeholder;
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefix}${body}${suffix}${currentValue.slice(selectionEnd)}`;
    const cursorStart = selectionStart + prefix.length;
    const cursorEnd = cursorStart + body.length;
    setValueWithSelection(nextValue, cursorStart, cursorEnd);
  };

  const insertAtCursor = (text) => {
    const input = inputRef.current;
    const currentValue = value || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const nextValue = `${currentValue.slice(0, selectionStart)}${text}${currentValue.slice(selectionEnd)}`;
    const cursor = selectionStart + text.length;
    setValueWithSelection(nextValue, cursor, cursor);
  };

  const prefixSelectedLines = (prefix) => {
    const input = inputRef.current;
    const currentValue = value || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    if (selectionStart === selectionEnd) {
      insertAtCursor(prefix);
      return;
    }
    const selected = currentValue.slice(selectionStart, selectionEnd);
    const prefixed = selected.split('\n').map((line) => (line ? `${prefix}${line}` : prefix.trimEnd())).join('\n');
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefixed}${currentValue.slice(selectionEnd)}`;
    setValueWithSelection(nextValue, selectionStart, selectionStart + prefixed.length);
  };

  return (
    <Form className="tm-comment-form mb-3" onSubmit={(event) => {
      event.preventDefault();
      onSubmit();
    }}>
      <FormGroup>
        <Label>{title}</Label>
        <div className="tm-md-editor">
          <div className="tm-md-editor-toolbar" role="toolbar" aria-label={`${title} markdown panel`}>
            <Button type="button" color="secondary" outline size="sm" onClick={() => insertWrapped('**', '**', 'bold text')}>
              <i className="bi bi-type-bold" />
            </Button>
            <Button type="button" color="secondary" outline size="sm" onClick={() => insertWrapped('_', '_', 'italic text')}>
              <i className="bi bi-type-italic" />
            </Button>
            <Button type="button" color="secondary" outline size="sm" onClick={() => insertAtCursor('## ')}>
              <i className="bi bi-type-h2" />
            </Button>
            <Button type="button" color="secondary" outline size="sm" onClick={() => prefixSelectedLines('> ')}>
              <i className="bi bi-blockquote-left" />
            </Button>
            <Button type="button" color="secondary" outline size="sm" onClick={() => prefixSelectedLines('- ')}>
              <i className="bi bi-list-ul" />
            </Button>
            <Button type="button" color="secondary" outline size="sm" onClick={() => prefixSelectedLines('1. ')}>
              <i className="bi bi-list-ol" />
            </Button>
            <Button type="button" color="secondary" outline size="sm" onClick={() => insertWrapped('[', '](https://)', 'link text')}>
              <i className="bi bi-link-45deg" />
            </Button>
            <Button type="button" color="secondary" outline size="sm" onClick={() => insertWrapped('```\n', '\n```', 'code')}>
              <i className="bi bi-code-square" />
            </Button>
          </div>
          <Input
            innerRef={inputRef}
            type="textarea"
            rows="4"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </div>
        <div className="tm-muted tm-field-help">Markdown supported (headings, lists, links, bold, code).</div>
        <details className="tm-markdown-preview tm-markdown-preview-collapsible">
          <summary className="tm-markdown-preview-head">Markdown preview</summary>
          <MarkdownText
            content={value}
            className="tm-markdown tm-markdown-preview-body"
            emptyMessage="Preview appears when text is filled."
          />
        </details>
      </FormGroup>
      <Button color="primary" outline size="sm" type="submit" disabled={!value.trim()}>
        Send
      </Button>
    </Form>
  );
}
