import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import {
  Alert,
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
import { usePolling, useRefetchOnFocus, useSessionDomainRefresh, DATA_DOMAINS } from '../hooks/useLiveRefresh.js';
import { EmptyRow, EmptyState, ErrorBanner, Loading, MarkdownText, PageHeader, StatusPill, TimeCell, apiError, asArray, downloadResponse, formatAttachmentSize, hasAnyInternalRole, hasInternalRole, labelValue, normalizeApiPath } from './helpers.jsx';

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
  const navigate = useNavigate();
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
  const [changeStatusOpen, setChangeStatusOpen] = useState(false);
  const [reassignOpen, setReassignOpen] = useState(false);
  const [setPriorityOpen, setSetPriorityOpen] = useState(false);
  const [moreActionsOpen, setMoreActionsOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

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
  useSessionDomainRefresh([DATA_DOMAINS.ticketDetail, DATA_DOMAINS.meta, DATA_DOMAINS.users], load);
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
      downloadResponse(response, attachment.filename || 'attachment');
    } catch (err) {
      setError(apiError(err));
    } finally {
      setDownloadingAttachmentId('');
    }
  };

  const copyTicketId = async () => {
    if (!ticket?.id) return;
    try {
      await navigator.clipboard.writeText(ticket.id);
      setNotice('Ticket ID copied to clipboard.');
    } catch {
      setNotice('Could not copy ticket ID.');
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
  const priorities = asArray(meta?.priorities);
  const assignmentTeam = ticket?.resolver_team || assignment.team;
  const canTransferOwner = !ticket?.internal && !ticket?.system && responsibleUsers.length > 0;
  const canManageParticipants = ticket?.system
    ? user.kind === 'partner' && user.partner_role === 'responsible'
    : !ticket?.internal && (user.kind === 'internal' || ticket?.owner_id === user.id);
  const canEditTicketType = user.kind === 'internal'
    && hasAnyInternalRole(user, ['Admin', 'DeliveryManager'])
    && ticketTypes.length > 0;
  const canEditTicketPriority = user.kind === 'internal'
    && hasAnyInternalRole(user, ['Admin', 'DeliveryManager'])
    && priorities.length > 0;
  const canAddCommunication = ticket?.status !== 'Closed' && (
    user.kind === 'internal'
    || (ticket?.system && user.partner_role === 'responsible')
    || (!ticket?.system && participantIds.includes(user.id))
  );
  const canAssignTicket = ticket?.status !== 'Closed';
  const canReturnToQueue = canAssignTicket
    && user.kind === 'internal'
    && hasAnyInternalRole(user, ['Admin', 'DeliveryManager'])
    && Boolean(ticket?.resolver_team)
    && Boolean(ticket?.assignee_id);
  const showPrimaryStatusActions = user.kind === 'internal';
  const showChangeStatus = showPrimaryStatusActions;
  const showReassign = canAssignTicket;
  const showSetPriority = canEditTicketPriority;
  const canDeleteTicket = user.kind === 'internal' && hasInternalRole(user, 'Admin');

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
            <TicketInfoCard ticket={ticket} />
            <WorkflowCard
              showChangeStatus={showChangeStatus}
              showReassign={showReassign}
              showSetPriority={showSetPriority}
              onChangeStatus={() => setChangeStatusOpen(true)}
              onReassign={() => setReassignOpen(true)}
              onSetPriority={() => setSetPriorityOpen(true)}
              onMoreActions={() => setMoreActionsOpen(true)}
            />
            <RecentActivityCard ticket={ticket} onOpenHistory={() => setHistoryOpen(true)} />
          </aside>
        </div>
      )}
      {ticket && (
        <>
          <ChangeStatusModal
            isOpen={changeStatusOpen}
            onClose={() => setChangeStatusOpen(false)}
            ticket={ticket}
            availableTransitions={availableTransitions}
            onConfirm={async (status, note) => {
              setError('');
              try {
                await api.post(`/tickets/${ticket.id}/transition`, { status });
                if (note?.trim()) {
                  try {
                    await api.post(`/tickets/${ticket.id}/internal-notes`, { body: note.trim() });
                  } catch {
                    setNotice('Status updated, but the note could not be saved.');
                  }
                }
                await load();
                setChangeStatusOpen(false);
              } catch (err) {
                setError(apiError(err));
              }
            }}
          />
          <ReassignModal
            isOpen={reassignOpen}
            onClose={() => setReassignOpen(false)}
            ticket={ticket}
            assignment={assignment}
            setAssignment={setAssignment}
            assignmentTeam={assignmentTeam}
            resolverTeams={resolverTeams}
            internalUsers={internalUsers}
            canReturnToQueue={canReturnToQueue}
            onSubmit={() => action(async () => {
              await api.post(`/tickets/${ticket.id}/assign`, { ...assignment, team: assignmentTeam });
              setReassignOpen(false);
            })}
            onReturnToQueue={() => action(async () => {
              await api.post(`/tickets/${ticket.id}/unassign`);
              setReassignOpen(false);
            })}
          />
          <SetPriorityModal
            isOpen={setPriorityOpen}
            onClose={() => setSetPriorityOpen(false)}
            ticket={ticket}
            priorities={priorities}
            onSelectPriority={async (priority) => {
              await action(async () => {
                await api.post(`/tickets/${ticket.id}/priority`, { priority });
                setSetPriorityOpen(false);
              });
            }}
          />
          <MoreActionsModal
            isOpen={moreActionsOpen}
            onClose={() => setMoreActionsOpen(false)}
            ticket={ticket}
            participants={participants}
            attachments={attachments}
            partnerUsers={partnerUsers}
            responsibleUsers={responsibleUsers}
            ticketTypes={ticketTypes}
            canManageParticipants={canManageParticipants}
            canAddCommunication={canAddCommunication}
            canEditTicketType={canEditTicketType}
            canTransferOwner={canTransferOwner}
            canReturnToQueue={canReturnToQueue}
            canDeleteTicket={canDeleteTicket}
            participantId={participantId}
            setParticipantId={setParticipantId}
            uploadFile={uploadFile}
            setUploadFile={setUploadFile}
            ticketType={ticketType}
            setTicketType={setTicketType}
            transferOwner={transferOwner}
            setTransferOwner={setTransferOwner}
            downloadingAttachmentId={downloadingAttachmentId}
            onDownload={downloadAttachment}
            onCopyTicketId={copyTicketId}
            onAddParticipant={(userId) => action(async () => {
              await api.post(`/tickets/${ticket.id}/participants`, { user_id: userId });
            })}
            onRemoveParticipant={(userId) => action(async () => {
              await api.delete(`/tickets/${ticket.id}/participants/${userId}`);
            })}
            onUploadAttachment={() => action(async () => {
              const formData = new FormData();
              formData.append('file', uploadFile);
              await api.post(`/tickets/${ticket.id}/attachments`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
              setUploadFile(null);
            })}
            onSaveTicketType={() => action(async () => {
              await api.post(`/tickets/${ticket.id}/type`, { type: ticketType });
            })}
            onTransferOwner={() => action(async () => {
              await api.post(`/tickets/${ticket.id}/transfer-owner`, { new_owner: transferOwner });
            })}
            onReturnToQueue={() => action(async () => {
              await api.post(`/tickets/${ticket.id}/unassign`);
              setMoreActionsOpen(false);
            })}
            onDeleteTicket={() => {
              setMoreActionsOpen(false);
              setDeleteConfirmOpen(true);
            }}
          />
          <DeleteTicketConfirmModal
            isOpen={deleteConfirmOpen}
            onClose={() => setDeleteConfirmOpen(false)}
            ticket={ticket}
            onConfirm={async () => {
              setError('');
              try {
                await api.delete(`/tickets/${ticket.id}`);
                navigate('/', { state: { notice: `Ticket ${ticket.id} was deleted.` } });
              } catch (err) {
                setError(apiError(err));
                setDeleteConfirmOpen(false);
              }
            }}
          />
          <TicketHistoryModal
            isOpen={historyOpen}
            onClose={() => setHistoryOpen(false)}
            ticketId={ticket.id}
          />
        </>
      )}
    </div>
  );
}

function SideCardHeader({ id, icon, title, trailingIcon, onTrailingClick, trailingLabel }) {
  return (
    <header className="tm-side-card-header">
      <div className="tm-side-card-header-main">
        <i className={`bi ${icon}`} aria-hidden="true" />
        <h2 id={id}>{title}</h2>
      </div>
      {trailingIcon && onTrailingClick ? (
        <button
          type="button"
          className="tm-side-card-header-trail-btn"
          onClick={onTrailingClick}
          aria-label={trailingLabel || `View full ${title.toLowerCase()}`}
        >
          <i className={`bi ${trailingIcon}`} aria-hidden="true" />
        </button>
      ) : trailingIcon ? (
        <i className={`bi ${trailingIcon} tm-side-card-header-trail`} aria-hidden="true" />
      ) : null}
    </header>
  );
}

function TicketInfoCard({ ticket }) {
  return (
    <section className="tm-panel tm-side-card tm-ticket-info-card" aria-labelledby="tm-ticket-info-heading">
      <SideCardHeader id="tm-ticket-info-heading" icon="bi-info-circle" title="Ticket info" trailingIcon="bi-three-dots" />
      <div className="tm-side-info-list">
        <TicketInfoRow icon="bi-hash" label="Ticket ID" value={ticket?.id || '-'} />
        <TicketInfoRow icon="bi-tag" label="Type" value={labelValue(ticket?.type) || '-'} />
        <TicketInfoRow icon="bi-exclamation-triangle" label="Priority" value={<StatusPill value={ticket?.priority} priority={ticket?.priority} />} />
        <TicketInfoRow icon="bi-flag" label="Status" value={<StatusPill value={ticket?.status} />} />
        <TicketInfoRow icon="bi-person-circle" label="Owner" value={ticket?.owner_name || '-'} />
        <TicketInfoRow icon="bi-person" label="Assignee" value={ticket?.assignee_name || 'Unassigned'} />
        <TicketInfoRow icon="bi-people" label="Team" value={ticket?.resolver_team || 'No team'} />
        <TicketInfoRow
          icon="bi-calendar-plus"
          label="Created"
          value={ticket?.created_at ? <TimeCell value={ticket.created_at} /> : '—'}
        />
        <TicketInfoRow
          icon="bi-clock"
          label="Updated"
          value={ticket?.updated_at ? <TimeCell value={ticket.updated_at} /> : '—'}
        />
      </div>
    </section>
  );
}

function TicketInfoRow({ icon, label, value }) {
  return (
    <div className="tm-side-info-row">
      <div className="tm-side-info-label">
        <i className={`bi ${icon}`} aria-hidden="true" />
        <span>{label}</span>
      </div>
      <div className="tm-side-info-value">{value ?? '-'}</div>
    </div>
  );
}

function WorkflowCard({
  showChangeStatus,
  showReassign,
  showSetPriority,
  onChangeStatus,
  onReassign,
  onSetPriority,
  onMoreActions
}) {
  return (
    <section className="tm-panel tm-side-card tm-workflow-card" aria-labelledby="tm-workflow-heading">
      <SideCardHeader id="tm-workflow-heading" icon="bi-diagram-3" title="Workflow" trailingIcon="bi-chevron-right" />
      <div className="tm-workflow-actions">
        {showChangeStatus && (
          <button type="button" className="tm-workflow-action-btn tm-workflow-action-btn-primary" onClick={onChangeStatus}>
            <i className="bi bi-arrow-repeat" aria-hidden="true" />
            <span>Change status</span>
          </button>
        )}
        {showReassign && (
          <button type="button" className="tm-workflow-action-btn" onClick={onReassign}>
            <i className="bi bi-person-check" aria-hidden="true" />
            <span>Reassign</span>
          </button>
        )}
        {showSetPriority && (
          <button type="button" className="tm-workflow-action-btn" onClick={onSetPriority}>
            <i className="bi bi-exclamation-triangle" aria-hidden="true" />
            <span>Set priority</span>
          </button>
        )}
        <button type="button" className="tm-workflow-action-btn" onClick={onMoreActions}>
          <i className="bi bi-three-dots" aria-hidden="true" />
          <span>More actions</span>
        </button>
      </div>
    </section>
  );
}

function ActivityTimelineList({ items }) {
  if (!items.length) {
    return <p className="tm-muted tm-activity-empty">No recent activity</p>;
  }

  return (
    <ul className="tm-activity-timeline">
      {items.map((item, index) => (
        <li key={item.id || item.key} className="tm-activity-timeline-item">
          <div className="tm-activity-timeline-marker" aria-hidden="true">
            <span className="tm-activity-timeline-dot" />
            {index < items.length - 1 && <span className="tm-activity-timeline-line" />}
          </div>
          <div className="tm-activity-timeline-body">
            <div className="tm-activity-timeline-title">{item.title}</div>
            <div className="tm-activity-timeline-meta tm-muted">
              <span>{item.author}</span>
              <span className="tm-activity-timeline-sep" aria-hidden="true">·</span>
              {item.time ? <TimeCell value={item.time} /> : <span>—</span>}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function RecentActivityCard({ ticket, onOpenHistory }) {
  const items = asArray(ticket?.recent_activity);

  return (
    <section className="tm-panel tm-side-card tm-activity-card" aria-labelledby="tm-activity-heading">
      <SideCardHeader
        id="tm-activity-heading"
        icon="bi-clock-history"
        title="Recent activity"
        trailingIcon="bi-chevron-right"
        onTrailingClick={onOpenHistory}
        trailingLabel="View full ticket history"
      />
      <ActivityTimelineList items={items} />
    </section>
  );
}

function TicketHistoryModal({ isOpen, onClose, ticketId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen || !ticketId) {
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError('');
    setItems([]);

    api.get(`/tickets/${ticketId}/activity`)
      .then((response) => {
        if (!cancelled) {
          setItems(asArray(response.data));
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(apiError(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, ticketId]);

  return (
    <Modal isOpen={isOpen} toggle={onClose} size="lg" backdrop>
      <ModalHeader toggle={onClose}>Ticket history</ModalHeader>
      <ModalBody>
        <ErrorBanner error={error} />
        {loading ? <Loading /> : <ActivityTimelineList items={items} />}
      </ModalBody>
      <ModalFooter>
        <Button color="secondary" outline type="button" onClick={onClose}>Close</Button>
      </ModalFooter>
    </Modal>
  );
}

function ChangeStatusModal({ isOpen, onClose, ticket, availableTransitions, onConfirm }) {
  const [selectedStatus, setSelectedStatus] = useState('');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setSelectedStatus('');
      setNote('');
      setSubmitting(false);
    }
  }, [isOpen]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!selectedStatus || submitting) return;
    setSubmitting(true);
    try {
      await onConfirm(selectedStatus, note);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} toggle={onClose} backdrop>
      <Form onSubmit={handleSubmit}>
        <ModalHeader toggle={onClose}>Change status</ModalHeader>
        <ModalBody>
          <p className="tm-muted tm-modal-lead">
            Current status: <StatusPill value={ticket?.status} />
          </p>
          {availableTransitions.length === 0 ? (
            <p className="tm-muted">No status changes are available.</p>
          ) : (
            <FormGroup>
              <Label for="tm-change-status-select">New status</Label>
              <Input
                id="tm-change-status-select"
                type="select"
                value={selectedStatus}
                onChange={(event) => setSelectedStatus(event.target.value)}
                required
              >
                <option value="">Select status</option>
                {availableTransitions.map((status) => (
                  <option key={status} value={status}>{labelValue(status)}</option>
                ))}
              </Input>
            </FormGroup>
          )}
          <FormGroup>
            <Label for="tm-change-status-note">Note (optional)</Label>
            <Input
              id="tm-change-status-note"
              type="textarea"
              rows="3"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Add a short internal note about this change"
            />
          </FormGroup>
        </ModalBody>
        <ModalFooter>
          <Button color="secondary" outline type="button" onClick={onClose}>Cancel</Button>
          <Button
            color="primary"
            type="submit"
            disabled={!selectedStatus || submitting || availableTransitions.length === 0}
          >
            Confirm
          </Button>
        </ModalFooter>
      </Form>
    </Modal>
  );
}

function ReassignModal({
  isOpen,
  onClose,
  ticket,
  assignment,
  setAssignment,
  assignmentTeam,
  resolverTeams,
  internalUsers,
  canReturnToQueue,
  onSubmit,
  onReturnToQueue
}) {
  return (
    <Modal isOpen={isOpen} toggle={onClose} backdrop>
      <Form onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}>
        <ModalHeader toggle={onClose}>Reassign ticket</ModalHeader>
        <ModalBody>
          <FormGroup>
            <Label for="tm-reassign-team">Team</Label>
            {ticket?.resolver_team ? (
              <div className="tm-readonly-field" id="tm-reassign-team">{ticket.resolver_team}</div>
            ) : (
              <Input
                id="tm-reassign-team"
                type="select"
                value={assignment.team}
                onChange={(event) => setAssignment({ ...assignment, team: event.target.value })}
              >
                {resolverTeams.map((team) => <option key={team}>{team}</option>)}
              </Input>
            )}
          </FormGroup>
          <FormGroup>
            <Label for="tm-reassign-assignee">Assignee</Label>
            <Input
              id="tm-reassign-assignee"
              type="select"
              value={assignment.assignee || ''}
              onChange={(event) => setAssignment({ ...assignment, assignee: event.target.value })}
            >
              <option value="">Unassigned</option>
              {internalUsers.filter((row) => hasInternalRole(row, assignmentTeam)).map((row) => (
                <option key={row.id} value={row.email}>{row.name}</option>
              ))}
            </Input>
          </FormGroup>
        </ModalBody>
        <ModalFooter>
          {canReturnToQueue && (
            <Button color="secondary" outline type="button" onClick={onReturnToQueue}>
              Return to queue
            </Button>
          )}
          <Button color="secondary" outline type="button" onClick={onClose}>Cancel</Button>
          <Button color="primary" type="submit">Save assignment</Button>
        </ModalFooter>
      </Form>
    </Modal>
  );
}

const PRIORITY_TILE_ORDER = ['Critical', 'High', 'Normal', 'Low'];

function priorityTileTone(priority) {
  if (priority === 'Critical') return 'danger';
  if (priority === 'High') return 'warning';
  if (priority === 'Low') return 'soft';
  return 'neutral';
}

function SetPriorityModal({ isOpen, onClose, ticket, priorities, onSelectPriority }) {
  const [submittingPriority, setSubmittingPriority] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setSubmittingPriority('');
    }
  }, [isOpen]);

  const currentPriority = ticket?.priority || '';
  const isBusy = Boolean(submittingPriority);
  const orderedPriorities = PRIORITY_TILE_ORDER.filter((priority) => priorities.includes(priority));

  const handleSelect = async (priority) => {
    if (isBusy || priority === currentPriority) return;
    setSubmittingPriority(priority);
    try {
      await onSelectPriority(priority);
    } finally {
      setSubmittingPriority('');
    }
  };

  return (
    <Modal isOpen={isOpen} toggle={onClose} backdrop>
      <ModalHeader toggle={onClose}>Set priority</ModalHeader>
      <ModalBody>
        <p className="tm-muted tm-modal-lead">
          Current priority: <StatusPill value={ticket?.priority} priority={ticket?.priority} />
        </p>
        <p className="tm-muted tm-set-priority-hint">Select a new priority</p>
        <div className="tm-priority-tiles" role="group" aria-label="Priority options">
          {orderedPriorities.map((priority) => {
            const isSelected = priority === currentPriority;
            const isLoading = submittingPriority === priority;
            const tone = priorityTileTone(priority);
            return (
              <button
                key={priority}
                type="button"
                className={[
                  'tm-priority-tile',
                  `tm-priority-tile-${tone}`,
                  isSelected ? 'tm-priority-tile-selected' : '',
                  isLoading ? 'tm-priority-tile-loading' : ''
                ].filter(Boolean).join(' ')}
                onClick={() => handleSelect(priority)}
                disabled={isBusy}
                aria-pressed={isSelected}
                aria-busy={isLoading}
              >
                {isLoading && <span className="tm-priority-tile-spinner" aria-hidden="true" />}
                <span className="tm-priority-tile-label">{labelValue(priority)}</span>
              </button>
            );
          })}
        </div>
      </ModalBody>
      <ModalFooter>
        <Button color="secondary" outline type="button" onClick={onClose} disabled={isBusy}>Cancel</Button>
      </ModalFooter>
    </Modal>
  );
}

function MoreActionsModal({
  isOpen,
  onClose,
  ticket,
  participants,
  attachments,
  partnerUsers,
  responsibleUsers,
  ticketTypes,
  canManageParticipants,
  canAddCommunication,
  canEditTicketType,
  canTransferOwner,
  canReturnToQueue,
  canDeleteTicket,
  participantId,
  setParticipantId,
  uploadFile,
  setUploadFile,
  ticketType,
  setTicketType,
  transferOwner,
  setTransferOwner,
  downloadingAttachmentId,
  onDownload,
  onCopyTicketId,
  onAddParticipant,
  onRemoveParticipant,
  onUploadAttachment,
  onSaveTicketType,
  onTransferOwner,
  onReturnToQueue,
  onDeleteTicket
}) {
  const [view, setView] = useState('menu');

  useEffect(() => {
    if (!isOpen) setView('menu');
  }, [isOpen]);

  const close = () => {
    setView('menu');
    onClose();
  };

  const titles = {
    menu: 'More actions',
    participants: 'Manage participants',
    attachments: 'Manage attachments',
    'ticket-type': 'Change ticket type',
    'transfer-owner': 'Transfer owner'
  };

  return (
    <Modal isOpen={isOpen} toggle={close} backdrop size={view === 'menu' ? undefined : 'lg'}>
      <ModalHeader toggle={close}>
        {view !== 'menu' && (
          <Button color="link" className="tm-modal-back p-0 me-2" type="button" onClick={() => setView('menu')} aria-label="Back to actions">
            <i className="bi bi-arrow-left" />
          </Button>
        )}
        {titles[view]}
      </ModalHeader>
      <ModalBody>
        {view === 'menu' && (
          <div className="tm-more-actions-menu">
            {canManageParticipants && (
              <Button color="secondary" outline className="tm-more-action-btn" onClick={() => setView('participants')}>
                <i className="bi bi-people" aria-hidden="true" />
                Manage participants
              </Button>
            )}
            <Button color="secondary" outline className="tm-more-action-btn" onClick={() => setView('attachments')}>
              <i className="bi bi-paperclip" aria-hidden="true" />
              Manage attachments
            </Button>
            <Button
              color="secondary"
              outline
              className="tm-more-action-btn"
              onClick={() => {
                onCopyTicketId();
              }}
            >
              <i className="bi bi-clipboard" aria-hidden="true" />
              Copy ticket ID
            </Button>
            {canEditTicketType && (
              <Button color="secondary" outline className="tm-more-action-btn" onClick={() => setView('ticket-type')}>
                <i className="bi bi-tag" aria-hidden="true" />
                Change ticket type
              </Button>
            )}
            {canTransferOwner && (
              <Button color="secondary" outline className="tm-more-action-btn" onClick={() => setView('transfer-owner')}>
                <i className="bi bi-arrow-left-right" aria-hidden="true" />
                Transfer owner
              </Button>
            )}
            {canReturnToQueue && (
              <Button color="secondary" outline className="tm-more-action-btn" onClick={onReturnToQueue}>
                <i className="bi bi-inbox" aria-hidden="true" />
                Return to queue
              </Button>
            )}
            {canDeleteTicket && (
              <Button color="danger" outline className="tm-more-action-btn" onClick={onDeleteTicket}>
                <i className="bi bi-trash" aria-hidden="true" />
                Delete ticket
              </Button>
            )}
          </div>
        )}
        {view === 'participants' && (
          <div className="tm-more-action-view">
            <div className={`tm-participant-list${canManageParticipants ? ' tm-participant-list-managed' : ''}`}>
              {participants.map((participant) => (
                canManageParticipants ? (
                  <div className="tm-participant-row" key={participant.id}>
                    <span className="tm-participant-pill">{participant.name}</span>
                    <Button
                      color="secondary"
                      outline
                      size="sm"
                      type="button"
                      className="tm-participant-remove-btn"
                      aria-label={`Remove ${participant.name}`}
                      onClick={() => onRemoveParticipant(participant.id)}
                    >
                      Remove
                    </Button>
                  </div>
                ) : (
                  <span className="tm-participant-pill" key={participant.id}>{participant.name}</span>
                )
              ))}
              {participants.length === 0 && <span className="tm-muted">No participants.</span>}
            </div>
            {canManageParticipants && partnerUsers.length > 0 && (
              <Form className="tm-inline-form tm-inline-form-compact mt-2" onSubmit={(event) => {
                event.preventDefault();
                if (participantId) onAddParticipant(participantId);
              }}>
                <Input
                  type="select"
                  value={participantId}
                  onChange={(event) => setParticipantId(event.target.value)}
                  aria-label="Add participant"
                >
                  <option value="">Add participant</option>
                  {partnerUsers.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                </Input>
                <Button color="primary" size="sm" type="submit" disabled={!participantId}>
                  Add
                </Button>
              </Form>
            )}
          </div>
        )}
        {view === 'attachments' && (
          <AttachmentPanel
            compact
            attachments={attachments}
            uploadFile={uploadFile}
            setUploadFile={setUploadFile}
            canUpload={canAddCommunication}
            downloadingAttachmentId={downloadingAttachmentId}
            onDownload={onDownload}
            onUpload={() => {
              if (uploadFile) onUploadAttachment();
            }}
          />
        )}
        {view === 'ticket-type' && (
          <Form onSubmit={(event) => {
            event.preventDefault();
            onSaveTicketType();
          }}>
            <FormGroup>
              <Label for="tm-more-ticket-type">Type</Label>
              <Input
                id="tm-more-ticket-type"
                type="select"
                value={ticketType || ticket?.type || ''}
                onChange={(event) => setTicketType(event.target.value)}
              >
                {ticketTypes.map((type) => <option key={type} value={type}>{labelValue(type)}</option>)}
              </Input>
            </FormGroup>
            <Button color="primary" size="sm" type="submit" disabled={!ticketType || ticketType === ticket?.type}>
              Save type
            </Button>
          </Form>
        )}
        {view === 'transfer-owner' && (
          <Form onSubmit={(event) => {
            event.preventDefault();
            onTransferOwner();
          }}>
            <FormGroup>
              <Label for="tm-more-transfer-owner">New owner</Label>
              <Input
                id="tm-more-transfer-owner"
                type="select"
                value={transferOwner}
                onChange={(event) => setTransferOwner(event.target.value)}
              >
                <option value="">Select owner</option>
                {responsibleUsers.map((row) => <option key={row.id} value={row.email}>{row.name}</option>)}
              </Input>
            </FormGroup>
            <Button color="primary" size="sm" type="submit" disabled={!transferOwner}>
              Transfer
            </Button>
          </Form>
        )}
      </ModalBody>
      {view === 'menu' && (
        <ModalFooter>
          <Button color="secondary" outline type="button" onClick={close}>Cancel</Button>
        </ModalFooter>
      )}
    </Modal>
  );
}

function DeleteTicketConfirmModal({ isOpen, onClose, ticket, onConfirm }) {
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setSubmitting(false);
    }
  }, [isOpen]);

  const handleConfirm = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await onConfirm();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} toggle={onClose} backdrop>
      <ModalHeader toggle={onClose}>Delete ticket</ModalHeader>
      <ModalBody>
        <p className="tm-modal-lead">
          Permanently delete ticket <strong>{ticket?.id}</strong> — <strong>{ticket?.title}</strong>?
        </p>
        <p className="tm-muted">
          This removes the ticket, comments, attachments, and related data. This action cannot be undone.
        </p>
      </ModalBody>
      <ModalFooter>
        <Button color="secondary" outline type="button" onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button color="danger" type="button" onClick={handleConfirm} disabled={submitting}>
          {submitting ? 'Deleting…' : 'Delete ticket'}
        </Button>
      </ModalFooter>
    </Modal>
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
                <td>{formatAttachmentSize(attachment.size_bytes)}</td>
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
