import React, { useEffect, useRef, useState } from 'react';
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
import { EmptyRow, EmptyState, ErrorBanner, Loading, MarkdownText, PageHeader, StatusPill, TimeCell, apiError, labelValue } from './helpers.jsx';

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
        title={ticket?.title || 'Detail ticketu'}
        actions={(
          <Button outline color="secondary" onClick={load} title="Obnovit ticket">
            <i className="bi bi-arrow-clockwise" />
            Obnovit
          </Button>
        )}
      />
      <ErrorBanner error={error} />
      {notice && (
        <Alert color="warning" className="tm-alert" toggle={() => setNotice('')}>
          {notice}
        </Alert>
      )}
      {ticket && (
        <div className="tm-ticket-layout">
          <main className="tm-ticket-main">
            <section className="tm-panel">
              <div className="tm-ticket-title-row">
                <div>
                  <div className="tm-muted">Aktuální stav</div>
                  <StatusPill value={ticket.status} />
                </div>
                <StatusPill value={ticket.priority} priority={ticket.priority} />
              </div>
              <h2>Popis</h2>
              <MarkdownText content={ticket.description} className="tm-markdown tm-ticket-description" />
            </section>
            <section className="tm-panel">
              <h2>Komunikace</h2>
              <CommentList comments={comments} />
              {canAddCommunication && (
                <CommentForm
                  title="Přidat komentář"
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
                  title="Interní poznámka"
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
                  <InfoRow label="Druh" value={labelValue(ticket.kind || (ticket.system ? 'system' : (ticket.internal ? 'internal' : 'partner')))} />
                  <InfoRow label="Typ" value={labelValue(ticket.type)} />
                  <InfoRow label="Partner" value={ticket.partner_name || '-'} />
                  <InfoRow label="Klient" value={ticket.client_name || '-'} />
                  <InfoRow label="Vlastník" value={ticket.owner_name || '-'} />
                  {user.kind === 'internal' && <InfoRow label="Řešitelský tým" value={ticket.resolver_team || '-'} />}
                  {user.kind === 'internal' && <InfoRow label="Assignee" value={ticket.assignee_name || '-'} />}
                  {user.kind === 'internal' && <InfoRow label="GitLab" value={ticket.gitlab_link ? <a href={ticket.gitlab_link}>{labelValue(ticket.gitlab_status || 'Open')}</a> : (ticket.gitlab_status || '-')} />}
                  <InfoRow label="Vytvořeno" value={<TimeCell value={ticket.created_at} />} />
                  <InfoRow label="Aktualizováno" value={<TimeCell value={ticket.updated_at} />} />
                </tbody>
              </Table>
            </section>
            {showActions && (
              <section className="tm-panel">
                <h2>Akce</h2>
                {user.kind === 'internal' && (
                  <>
                    <div className="tm-action-group">
                      <div className="tm-action-group-head">
                        <h3>Stav</h3>
                        <StatusPill value={ticket.status} />
                      </div>
                      <div className="tm-actions">
                        {availableTransitions.map((status) => (
                          <Button key={status} size="sm" outline color="primary" onClick={() => action(() => api.post(`/tickets/${ticket.id}/transition`, { status }))}>
                            {labelValue(status)}
                          </Button>
                        ))}
                        {availableTransitions.length === 0 && <span className="tm-muted">Nejsou dostupné žádné změny stavu.</span>}
                      </div>
                    </div>
                    {canAssignTicket && <div className="tm-action-group">
                      <h3>Přiřazení</h3>
                      <Form onSubmit={(event) => {
                        event.preventDefault();
                        action(() => api.post(`/tickets/${ticket.id}/assign`, { ...assignment, team: assignmentTeam }));
                      }}>
                        <FormGroup>
                          <Label>Řešitelský tým</Label>
                          {ticket.resolver_team ? (
                            <div className="tm-readonly-field">{ticket.resolver_team}</div>
                          ) : (
                            <Input type="select" value={assignment.team} onChange={(event) => setAssignment({ ...assignment, team: event.target.value })}>
                              {resolverTeams.map((team) => <option key={team}>{team}</option>)}
                            </Input>
                          )}
                        </FormGroup>
                        <FormGroup>
                          <Label>Řešitel</Label>
                          <Input type="select" value={assignment.assignee || ''} onChange={(event) => setAssignment({ ...assignment, assignee: event.target.value })}>
                            <option value="">Nepřiřazeno</option>
                            {internalUsers.filter((row) => row.internal_role === assignmentTeam).map((row) => <option key={row.id} value={row.email}>{row.name}</option>)}
                          </Input>
                        </FormGroup>
                        <Button color="primary" className="w-100" type="submit">
                          <i className="bi bi-diagram-3 me-1" />
                          Přiřadit
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
                          Vrátit do fronty
                        </Button>
                      )}
                    </div>}
                  </>
                )}
                {canTransferOwner && (
                  <div className="tm-action-group">
                    <h3>Předat vlastníka</h3>
                    <Form onSubmit={(event) => {
                      event.preventDefault();
                      action(() => api.post(`/tickets/${ticket.id}/transfer-owner`, { new_owner: transferOwner }));
                    }}>
                      <FormGroup>
                        <Label>Nový vlastník</Label>
                        <Input type="select" value={transferOwner} onChange={(event) => setTransferOwner(event.target.value)}>
                          <option value="">Vyberte vlastníka</option>
                          {responsibleUsers.map((row) => <option key={row.id} value={row.email}>{row.name}</option>)}
                        </Input>
                      </FormGroup>
                      <Button color="secondary" outline type="submit" disabled={!transferOwner} className="w-100">
                        <i className="bi bi-arrow-left-right me-1" />
                        Předat
                      </Button>
                    </Form>
                  </div>
                )}
              </section>
            )}
            <section className="tm-panel">
              <h2>Účastníci</h2>
              <div className="mb-3">
                {participants.map((participant) => (
                  <span className="badge text-bg-light border me-1 mb-1" key={participant.id}>{participant.name}</span>
                ))}
                {participants.length === 0 && <span className="tm-muted">Bez účastníků.</span>}
              </div>
              {canManageParticipants && partnerUsers.length > 0 && (
                <Form className="d-flex gap-2" onSubmit={(event) => {
                  event.preventDefault();
                  action(() => api.post(`/tickets/${ticket.id}/participants`, { user_id: participantId }));
                }}>
                  <Input type="select" value={participantId} onChange={(event) => setParticipantId(event.target.value)}>
                    <option value="">Přidat účastníka</option>
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
                downloadingAttachmentId={downloadingAttachmentId}
                onDownload={downloadAttachment}
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

function AttachmentPanel({ attachments, uploadFile, setUploadFile, canUpload, onUpload, onDownload, downloadingAttachmentId }) {
  return (
    <div className="mb-3">
      <h3>Přílohy</h3>
      <div className="tm-table-wrap mb-2">
        <Table size="sm" responsive className="tm-table">
          <thead>
            <tr>
              <th>Soubor</th>
              <th>Velikost</th>
              <th>Nahrál</th>
              <th>Vytvořeno</th>
            </tr>
          </thead>
          <tbody>
            {attachments.map((attachment) => (
              <tr key={attachment.id}>
                <td>
                  <Button
                    color="link"
                    className="p-0 align-baseline"
                    onClick={() => onDownload(attachment)}
                    disabled={downloadingAttachmentId === attachment.id}
                  >
                    {attachment.filename}
                  </Button>
                </td>
                <td>{formatBytes(attachment.size_bytes)}</td>
                <td>{attachment.uploaded_by_name || '-'}</td>
                <td><TimeCell value={attachment.created_at} /></td>
              </tr>
            ))}
            {attachments.length === 0 && <EmptyRow colSpan="4" title="Žádné přílohy" message="Nahrané soubory k ticketu se zobrazí zde." />}
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
      <h3>Komentáře a poznámky</h3>
      {comments.map((comment) => (
        <div key={comment.id} className="tm-comment">
          <div className="d-flex justify-content-between">
            <div>
              <strong>{comment.author_name || comment.author_id}</strong>
            </div>
            <span className="tm-muted"><TimeCell value={comment.created_at} /></span>
          </div>
          {comment.visibility === 'internal_note' && <span className="badge text-bg-warning mb-1">Interní poznámka</span>}
          <MarkdownText content={comment.body} className="tm-markdown tm-comment-body" />
        </div>
      ))}
      {comments.length === 0 && <EmptyState icon="bi-chat-left-text" title="Zatím žádné komentáře" message="Komunikace k ticketu se zobrazí zde." />}
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
    <Form className="mb-3" onSubmit={(event) => {
      event.preventDefault();
      onSubmit();
    }}>
      <FormGroup>
        <Label>{title}</Label>
        <div className="tm-md-editor">
          <div className="tm-md-editor-toolbar" role="toolbar" aria-label={`${title} markdown panel`}>
            <Button type="button" color="secondary" outline size="sm" onClick={() => insertWrapped('**', '**', 'tučný text')}>
              <i className="bi bi-type-bold" />
            </Button>
            <Button type="button" color="secondary" outline size="sm" onClick={() => insertWrapped('_', '_', 'kurzíva')}>
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
            <Button type="button" color="secondary" outline size="sm" onClick={() => insertWrapped('[', '](https://)', 'odkaz')}>
              <i className="bi bi-link-45deg" />
            </Button>
            <Button type="button" color="secondary" outline size="sm" onClick={() => insertWrapped('```\n', '\n```', 'kód')}>
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
        <div className="tm-muted tm-field-help">Podporuje Markdown (nadpisy, seznamy, odkazy, tučné písmo, kód).</div>
        <div className="tm-markdown-preview">
          <div className="tm-markdown-preview-head">Náhled markdownu</div>
          <MarkdownText
            content={value}
            className="tm-markdown tm-markdown-preview-body"
            emptyMessage="Náhled se zobrazí po vyplnění textu."
          />
        </div>
      </FormGroup>
      <Button color="primary" outline type="submit" disabled={!value.trim()}>
        <i className="bi bi-chat-left-text me-1" />
        Odeslat
      </Button>
    </Form>
  );
}
