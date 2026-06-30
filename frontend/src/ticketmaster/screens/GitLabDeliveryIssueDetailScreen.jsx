import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  Button,
  Form,
  FormGroup,
  Input,
  Label,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader
} from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { usePolling, useRefetchOnFocus, useSessionDomainRefresh, DATA_DOMAINS } from '../hooks/useLiveRefresh.js';
import {
  asArray,
  ErrorBanner,
  Loading,
  MarkdownText,
  PageHeader,
  StatusPill,
  TimeCell,
  apiError,
  hasAnyInternalRole
} from './helpers.jsx';

const POLL_MS = 60000;

export default function GitLabDeliveryIssueDetailScreen() {
  const { trackedIssueId } = useParams();
  return (
    <AuthGate>
      {(user) => <IssueDetailPage user={user} trackedIssueId={trackedIssueId} />}
    </AuthGate>
  );
}

function IssueDetailPage({ user, trackedIssueId }) {
  const navigate = useNavigate();
  const canView = user?.kind === 'internal';
  const canManage = canView && hasAnyInternalRole(user, ['Admin', 'DeliveryManager']);
  const [detailData, setDetailData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState('');
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editPreview, setEditPreview] = useState(false);
  const [editError, setEditError] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const editDescriptionRef = useRef(null);
  const [moveModalOpen, setMoveModalOpen] = useState(false);
  const [moveProjectId, setMoveProjectId] = useState('');
  const [moveError, setMoveError] = useState('');
  const [moveSaving, setMoveSaving] = useState(false);
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [assignUserId, setAssignUserId] = useState('');
  const [assignError, setAssignError] = useState('');
  const [assignSaving, setAssignSaving] = useState(false);
  const [moveProjectOptions, setMoveProjectOptions] = useState([]);
  const [mappingModalOpen, setMappingModalOpen] = useState(false);
  const [mappingTargetUrl, setMappingTargetUrl] = useState('');
  const [mappingError, setMappingError] = useState('');
  const [mappingSaving, setMappingSaving] = useState(false);
  const [commentBody, setCommentBody] = useState('');
  const [commentPreview, setCommentPreview] = useState(false);
  const [commentInternal, setCommentInternal] = useState(false);
  const [commentError, setCommentError] = useState('');
  const [commentSaving, setCommentSaving] = useState(false);
  const commentBodyRef = useRef(null);

  const loadDetail = useCallback(async () => {
    if (!canView || !trackedIssueId) return;
    setLoading(true);
    setError('');
    try {
      const response = await api.get(`/gitlab/delivery-tracking/${trackedIssueId}/detail`);
      setDetailData(response.data || null);
    } catch (err) {
      setError(apiError(err));
      setDetailData(null);
    } finally {
      setLoading(false);
    }
  }, [canView, trackedIssueId]);

  const loadMoveProjectOptions = useCallback(async () => {
    if (!canManage) return;
    try {
      const response = await api.get('/gitlab/delivery-tracking/meta');
      const dedup = new Map();
      asArray(response.data?.target_teams).forEach((team) => {
        const projectId = String(team?.project_id || '').trim();
        if (!projectId || dedup.has(projectId)) return;
        dedup.set(projectId, {
          value: projectId,
          label: team?.name ? `${team.name} (${projectId})` : projectId
        });
      });
      const options = Array.from(dedup.values()).sort((left, right) => left.label.localeCompare(right.label));
      setMoveProjectOptions(options);
    } catch {
      setMoveProjectOptions([]);
    }
  }, [canManage]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    loadMoveProjectOptions();
  }, [loadMoveProjectOptions]);

  useRefetchOnFocus(loadDetail, canView && Boolean(trackedIssueId));
  useSessionDomainRefresh(DATA_DOMAINS.gitlabDeliveryTracking, loadDetail, canView && Boolean(trackedIssueId));
  usePolling(loadDetail, POLL_MS, canView && Boolean(trackedIssueId));

  const tracked = detailData?.tracked_issue || null;
  const issue = detailData?.issue || null;
  const notes = asArray(detailData?.notes);
  const assignableUsers = asArray(detailData?.assignable_users);
  const currentState = issue?.state || tracked?.target_state || tracked?.delivery_state;
  const labels = (Array.isArray(issue?.labels) && issue.labels.length > 0)
    ? issue.labels
    : (Array.isArray(tracked?.target_labels) && tracked.target_labels.length > 0)
      ? tracked.target_labels
      : tracked?.delivery_labels;
  const assignees = (Array.isArray(issue?.assignees) && issue.assignees.length > 0)
    ? issue.assignees
    : tracked?.target_assignees;
  const targetTeam = tracked?.target_team_name || (tracked?.sync_status === 'in_delivery' ? 'Delivery' : '-');
  const lastGitlabUpdate = issue?.updated_at || (tracked ? (tracked.target_updated_at || tracked.delivery_updated_at) : null);
  const issueReference = useMemo(
    () => issue?.reference || (issue?.iid ? `#${issue.iid}` : formatTicketId(tracked?.delivery_issue_iid)),
    [issue, tracked]
  );
  const noteCount = Number(issue?.user_notes_count || notes.length || 0);

  const closeIssue = async () => {
    if (!canManage || !trackedIssueId || actionLoading) return;
    if (typeof window !== 'undefined') {
      const confirmed = window.confirm('Close this GitLab issue?');
      if (!confirmed) return;
    }
    setActionLoading('close');
    setError('');
    try {
      await api.post(`/gitlab/delivery-tracking/${trackedIssueId}/close`);
      await loadDetail();
    } catch (err) {
      setError(apiError(err));
    } finally {
      setActionLoading('');
    }
  };

  const openEditDialog = () => {
    if (!canManage || !issue) return;
    setEditTitle(issue.title || '');
    setEditDescription(issue.description || '');
    setEditPreview(false);
    setEditError('');
    setEditModalOpen(true);
  };

  const closeEditDialog = () => {
    if (editSaving) return;
    setEditModalOpen(false);
    setEditError('');
  };

  const setEditDescriptionWithSelection = (nextValue, selectionStart, selectionEnd) => {
    setEditDescription(nextValue);
    requestAnimationFrame(() => {
      const input = editDescriptionRef.current;
      if (!input) return;
      input.focus();
      if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
        input.setSelectionRange(selectionStart, selectionEnd);
      }
    });
  };

  const insertEditWrapped = (prefix, suffix = '', placeholder = '') => {
    const input = editDescriptionRef.current;
    const currentValue = editDescription || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const selectedText = currentValue.slice(selectionStart, selectionEnd);
    const body = selectedText || placeholder;
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefix}${body}${suffix}${currentValue.slice(selectionEnd)}`;
    const cursorStart = selectionStart + prefix.length;
    const cursorEnd = cursorStart + body.length;
    setEditDescriptionWithSelection(nextValue, cursorStart, cursorEnd);
  };

  const insertEditAtCursor = (text) => {
    const input = editDescriptionRef.current;
    const currentValue = editDescription || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const nextValue = `${currentValue.slice(0, selectionStart)}${text}${currentValue.slice(selectionEnd)}`;
    const cursor = selectionStart + text.length;
    setEditDescriptionWithSelection(nextValue, cursor, cursor);
  };

  const prefixEditSelectedLines = (prefix) => {
    const input = editDescriptionRef.current;
    const currentValue = editDescription || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    if (selectionStart === selectionEnd) {
      insertEditAtCursor(prefix);
      return;
    }
    const selected = currentValue.slice(selectionStart, selectionEnd);
    const prefixed = selected.split('\n').map((line) => (line ? `${prefix}${line}` : prefix.trimEnd())).join('\n');
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefixed}${currentValue.slice(selectionEnd)}`;
    setEditDescriptionWithSelection(nextValue, selectionStart, selectionStart + prefixed.length);
  };

  const saveIssueEdit = async () => {
    if (!canManage || !trackedIssueId) return;
    const title = editTitle.trim();
    if (!title) {
      setEditError('Title is required.');
      return;
    }
    setEditSaving(true);
    setEditError('');
    setError('');
    try {
      await api.patch(`/gitlab/delivery-tracking/${trackedIssueId}/edit`, {
        title,
        description: editDescription
      });
      setEditModalOpen(false);
      await loadDetail();
    } catch (err) {
      setEditError(apiError(err));
    } finally {
      setEditSaving(false);
    }
  };

  const openMoveDialog = () => {
    if (!canManage || !issue) return;
    setMoveProjectId(moveProjectOptions[0]?.value || '');
    setMoveError('');
    setMoveModalOpen(true);
  };

  const closeMoveDialog = () => {
    if (moveSaving) return;
    setMoveModalOpen(false);
    setMoveError('');
  };

  const saveIssueMove = async () => {
    if (!canManage || !trackedIssueId) return;
    const toProjectId = moveProjectId.trim();
    if (!toProjectId) {
      setMoveError('Target project is required.');
      return;
    }
    setMoveSaving(true);
    setMoveError('');
    setError('');
    try {
      await api.post(`/gitlab/delivery-tracking/${trackedIssueId}/move`, { to_project_id: toProjectId });
      setMoveModalOpen(false);
      await loadDetail();
    } catch (err) {
      setMoveError(apiError(err));
    } finally {
      setMoveSaving(false);
    }
  };

  const openAssignDialog = () => {
    if (!canManage || !issue) return;
    const currentAssigneeId = asArray(issue.assignees)[0]?.id;
    setAssignUserId(currentAssigneeId ? String(currentAssigneeId) : '');
    setAssignError('');
    setAssignModalOpen(true);
  };

  const closeAssignDialog = () => {
    if (assignSaving) return;
    setAssignModalOpen(false);
    setAssignError('');
  };

  const saveIssueAssign = async () => {
    if (!canManage || !trackedIssueId) return;
    const assigneeId = Number.parseInt(assignUserId, 10);
    const assigneeIds = Number.isInteger(assigneeId) ? [assigneeId] : [];
    setActionLoading('assign');
    setAssignSaving(true);
    setAssignError('');
    setError('');
    try {
      await api.patch(`/gitlab/delivery-tracking/${trackedIssueId}/assign`, { assignee_ids: assigneeIds });
      setAssignModalOpen(false);
      await loadDetail();
    } catch (err) {
      setAssignError(apiError(err));
    } finally {
      setActionLoading('');
      setAssignSaving(false);
    }
  };

  const openMappingDialog = () => {
    setMappingTargetUrl('');
    setMappingError('');
    setMappingModalOpen(true);
  };

  const closeMappingDialog = () => {
    if (mappingSaving) return;
    setMappingModalOpen(false);
    setMappingTargetUrl('');
    setMappingError('');
  };

  const saveManualMapping = async () => {
    if (!trackedIssueId) return;
    const targetUrl = mappingTargetUrl.trim();
    if (!targetUrl) {
      setMappingError('Target issue URL is required.');
      return;
    }
    setMappingSaving(true);
    setMappingError('');
    setError('');
    try {
      await api.post(`/gitlab/delivery-tracking/${trackedIssueId}/manual-mapping`, {
        target_url: targetUrl
      });
      setMappingModalOpen(false);
      await loadDetail();
    } catch (err) {
      setMappingError(apiError(err));
    } finally {
      setMappingSaving(false);
    }
  };

  const setCommentBodyWithSelection = (nextValue, selectionStart, selectionEnd) => {
    setCommentBody(nextValue);
    requestAnimationFrame(() => {
      const input = commentBodyRef.current;
      if (!input) return;
      input.focus();
      if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
        input.setSelectionRange(selectionStart, selectionEnd);
      }
    });
  };

  const insertCommentWrapped = (prefix, suffix = '', placeholder = '') => {
    const input = commentBodyRef.current;
    const currentValue = commentBody || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const selectedText = currentValue.slice(selectionStart, selectionEnd);
    const body = selectedText || placeholder;
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefix}${body}${suffix}${currentValue.slice(selectionEnd)}`;
    const cursorStart = selectionStart + prefix.length;
    const cursorEnd = cursorStart + body.length;
    setCommentBodyWithSelection(nextValue, cursorStart, cursorEnd);
  };

  const insertCommentAtCursor = (text) => {
    const input = commentBodyRef.current;
    const currentValue = commentBody || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const nextValue = `${currentValue.slice(0, selectionStart)}${text}${currentValue.slice(selectionEnd)}`;
    const cursor = selectionStart + text.length;
    setCommentBodyWithSelection(nextValue, cursor, cursor);
  };

  const prefixCommentSelectedLines = (prefix) => {
    const input = commentBodyRef.current;
    const currentValue = commentBody || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    if (selectionStart === selectionEnd) {
      insertCommentAtCursor(prefix);
      return;
    }
    const selected = currentValue.slice(selectionStart, selectionEnd);
    const prefixed = selected.split('\n').map((line) => (line ? `${prefix}${line}` : prefix.trimEnd())).join('\n');
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefixed}${currentValue.slice(selectionEnd)}`;
    setCommentBodyWithSelection(nextValue, selectionStart, selectionStart + prefixed.length);
  };

  const submitComment = async () => {
    if (!canManage || !trackedIssueId) return;
    const trimmed = commentBody.trim();
    if (!trimmed) {
      setCommentError('Comment is required.');
      return;
    }
    setCommentSaving(true);
    setCommentError('');
    setError('');
    try {
      await api.post(`/gitlab/delivery-tracking/${trackedIssueId}/comments`, {
        body: commentBody,
        internal: commentInternal
      });
      setCommentBody('');
      setCommentPreview(false);
      setCommentInternal(false);
      await loadDetail();
    } catch (err) {
      setCommentError(apiError(err));
    } finally {
      setCommentSaving(false);
    }
  };

  if (!canView) {
    return (
      <div className="tm-screen">
        <PageHeader
          title="Ticket detail"
          actions={(
            <Button color="secondary" outline onClick={() => navigate('/delivery-tracking')}>
              Back to tickets
            </Button>
          )}
        />
        <ErrorBanner error="Ticket details are available only to internal users." />
      </div>
    );
  }

  return (
    <div className="tm-screen tm-delivery-detail-page">
      <PageHeader
        title={issue?.title || tracked?.delivery_title || 'Ticket detail'}
        actions={(
          <div className="d-flex gap-2">
            <Button color="secondary" outline onClick={() => navigate('/delivery-tracking')}>
              Back to tickets
            </Button>
            <Button
              color="secondary"
              outline
              onClick={loadDetail}
              disabled={loading || Boolean(actionLoading) || commentSaving}
            >
              {loading ? 'Refreshing...' : 'Refresh'}
            </Button>
          </div>
        )}
      >
        <div className="d-flex align-items-center gap-2">
          <span>{issueReference}</span>
          {currentState ? <StatusPill value={currentState} /> : null}
          {issue?.issue_type ? <span className="tm-muted">{formatIssueType(issue.issue_type)}</span> : null}
        </div>
      </PageHeader>
      <ErrorBanner error={error} />
      {loading && !detailData ? <Loading /> : (
        !tracked ? (
          <div className="tm-muted">Issue detail is not available.</div>
        ) : (
          <div className="tm-delivery-detail-layout">
            <div className="tm-delivery-detail-main">
              <section className="tm-delivery-detail-block">
                <div className="tm-delivery-detail-block-head">Description</div>
                <MarkdownText
                  content={issue?.description || ''}
                  className="tm-markdown tm-delivery-detail-description"
                  emptyMessage="No description."
                />
              </section>
              <section className="tm-delivery-detail-block">
                <div className="tm-delivery-detail-block-head">Discussion ({noteCount})</div>
                {notes.length === 0 ? (
                  <div className="tm-muted">No comments yet.</div>
                ) : (
                  <div className="tm-delivery-note-list">
                    {notes.map((note, index) => (
                      <article
                        key={note.id || `${note.created_at || note.updated_at || 'note'}-${index}`}
                        className={`tm-delivery-note${note.system ? ' is-system' : ''}`}
                      >
                        <div className="tm-delivery-note-head">
                          <strong>{note.author?.name || note.author?.username || 'GitLab user'}</strong>
                          <span className="tm-muted">
                            <TimeCell value={note.updated_at || note.created_at} />
                          </span>
                        </div>
                        {note.internal ? <span className="badge text-bg-warning mb-1">Internal note</span> : null}
                        <MarkdownText
                          content={note.body}
                          className="tm-markdown tm-delivery-note-body"
                          emptyMessage={note.system ? 'System note' : 'Empty note'}
                        />
                      </article>
                    ))}
                  </div>
                )}
              </section>
              {canManage ? (
                <section className="tm-delivery-detail-block">
                  <div className="tm-delivery-detail-block-head">Add comment</div>
                  <ErrorBanner error={commentError} />
                  <Form onSubmit={(event) => {
                    event.preventDefault();
                    submitComment();
                  }}
                  >
                    <div className="tm-md-editor">
                      <div className="tm-md-editor-toolbar" role="toolbar" aria-label="Comment markdown toolbar">
                        <Button
                          type="button"
                          color="secondary"
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => insertCommentWrapped('**', '**', 'bold text')}
                        >
                          <i className="bi bi-type-bold" aria-hidden="true" />
                        </Button>
                        <Button
                          type="button"
                          color="secondary"
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => insertCommentWrapped('_', '_', 'italic text')}
                        >
                          <i className="bi bi-type-italic" aria-hidden="true" />
                        </Button>
                        <Button
                          type="button"
                          color="secondary"
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => insertCommentAtCursor('## ')}
                        >
                          <i className="bi bi-type-h2" aria-hidden="true" />
                        </Button>
                        <Button
                          type="button"
                          color="secondary"
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => prefixCommentSelectedLines('> ')}
                        >
                          <i className="bi bi-chat-square-quote" aria-hidden="true" />
                        </Button>
                        <Button
                          type="button"
                          color="secondary"
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => prefixCommentSelectedLines('- ')}
                        >
                          <i className="bi bi-list-ul" aria-hidden="true" />
                        </Button>
                        <Button
                          type="button"
                          color="secondary"
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => prefixCommentSelectedLines('1. ')}
                        >
                          <i className="bi bi-list-ol" aria-hidden="true" />
                        </Button>
                        <Button
                          type="button"
                          color="secondary"
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => insertCommentWrapped('[', '](https://)', 'link text')}
                        >
                          <i className="bi bi-link-45deg" aria-hidden="true" />
                        </Button>
                        <Button
                          type="button"
                          color="secondary"
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => insertCommentWrapped('```\n', '\n```', 'code')}
                        >
                          <i className="bi bi-code-slash" aria-hidden="true" />
                        </Button>
                        <span className="tm-md-editor-separator" />
                        <Button
                          type="button"
                          color={commentPreview ? 'secondary' : 'primary'}
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => setCommentPreview(false)}
                        >
                          Write
                        </Button>
                        <Button
                          type="button"
                          color={commentPreview ? 'primary' : 'secondary'}
                          outline
                          size="sm"
                          className="tm-md-toolbar-btn"
                          onClick={() => setCommentPreview(true)}
                        >
                          Preview
                        </Button>
                      </div>
                      {commentPreview ? (
                        <div className="tm-create-md-preview">
                          <MarkdownText
                            content={commentBody}
                            className="tm-markdown tm-markdown-preview-body"
                            emptyMessage="Nothing to preview yet."
                          />
                        </div>
                      ) : (
                        <Input
                          id="tm-detail-comment-body"
                          innerRef={commentBodyRef}
                          type="textarea"
                          rows={8}
                          value={commentBody}
                          onChange={(event) => setCommentBody(event.target.value)}
                          placeholder="Write a comment..."
                        />
                      )}
                    </div>
                    <div className="d-flex flex-wrap justify-content-between align-items-center mt-2 gap-2">
                      <FormGroup check className="mb-0">
                        <Input
                          id="tm-detail-comment-internal"
                          type="checkbox"
                          checked={commentInternal}
                          onChange={(event) => setCommentInternal(event.target.checked)}
                        />
                        <Label for="tm-detail-comment-internal" check>
                          Internal note
                        </Label>
                      </FormGroup>
                      <Button
                        color="primary"
                        type="submit"
                        disabled={!commentBody.trim() || commentSaving || loading || Boolean(actionLoading)}
                      >
                        {commentSaving ? 'Commenting...' : 'Comment'}
                      </Button>
                    </div>
                  </Form>
                </section>
              ) : null}
            </div>
            <aside className="tm-delivery-detail-side">
              {canManage && tracked ? (
                <section className="tm-delivery-detail-block tm-workflow-card">
                  <div className="tm-delivery-detail-block-head">Workflow</div>
                  <div className="tm-workflow-actions">
                    <button
                      type="button"
                      className="tm-workflow-action-btn tm-workflow-action-btn-primary"
                      onClick={closeIssue}
                      disabled={Boolean(actionLoading) || loading || currentState === 'closed'}
                    >
                      <i className="bi bi-check2-circle" aria-hidden="true" />
                      <span>
                        {actionLoading === 'close'
                          ? 'Closing...'
                          : currentState === 'closed'
                            ? 'Issue closed'
                            : 'Close issue'}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="tm-workflow-action-btn"
                      onClick={openEditDialog}
                      disabled={Boolean(actionLoading) || loading || !issue}
                    >
                      <i className="bi bi-pencil-square" aria-hidden="true" />
                      <span>Edit issue</span>
                    </button>
                    <button
                      type="button"
                      className="tm-workflow-action-btn"
                      onClick={openAssignDialog}
                      disabled={Boolean(actionLoading) || loading || !issue}
                    >
                      <i className="bi bi-person-plus" aria-hidden="true" />
                      <span>{actionLoading === 'assign' ? 'Assigning...' : 'Assign issue'}</span>
                    </button>
                    <button
                      type="button"
                      className="tm-workflow-action-btn"
                      onClick={openMoveDialog}
                      disabled={Boolean(actionLoading) || loading || !issue}
                    >
                      <i className="bi bi-arrow-left-right" aria-hidden="true" />
                      <span>Move issue</span>
                    </button>
                    {tracked?.target_missing ? (
                      <button
                        type="button"
                        className="tm-workflow-action-btn"
                        onClick={openMappingDialog}
                        disabled={loading || mappingSaving}
                      >
                        <i className="bi bi-link-45deg" aria-hidden="true" />
                        <span>Map manually</span>
                      </button>
                    ) : null}
                  </div>
                </section>
              ) : null}
              <section className="tm-delivery-detail-block">
                <div className="tm-delivery-detail-block-head">Metadata</div>
                <div className="tm-delivery-meta-list">
                  <DetailMetaRow label="State">
                    {currentState ? <StatusPill value={currentState} /> : <span className="tm-muted">-</span>}
                  </DetailMetaRow>
                  <DetailMetaRow label="Type">
                    <span>{issue?.issue_type ? formatIssueType(issue.issue_type) : '-'}</span>
                  </DetailMetaRow>
                  <DetailMetaRow label="Confidential">
                    <span>{issue?.confidential ? 'Yes' : 'No'}</span>
                  </DetailMetaRow>
                  <DetailMetaRow label="Assignee">
                    <span>{formatAssignees(assignees)}</span>
                  </DetailMetaRow>
                  <DetailMetaRow label="Labels">
                    <span>{formatLabels(labels)}</span>
                  </DetailMetaRow>
                  <DetailMetaRow label="Milestone">
                    <span>{issue?.milestone?.title || '-'}</span>
                  </DetailMetaRow>
                  <DetailMetaRow label="Due date">
                    <span>{issue?.due_date || '-'}</span>
                  </DetailMetaRow>
                  <DetailMetaRow label="Target team">
                    <div>
                      <div>{targetTeam}</div>
                      <div className="tm-muted">{tracked?.target_project_name || '-'}</div>
                    </div>
                  </DetailMetaRow>
                  <DetailMetaRow label="Sync status">
                    <StatusPill value={syncStatusLabel(tracked?.sync_status)} tone={syncStatusTone(tracked?.sync_status)} />
                  </DetailMetaRow>
                  <DetailMetaRow label="Resolution">
                    <span>{tracked?.resolution_source || '-'}</span>
                  </DetailMetaRow>
                  <DetailMetaRow label="Updated">
                    <TimeCell value={lastGitlabUpdate} />
                  </DetailMetaRow>
                  <DetailMetaRow label="Synced">
                    <TimeCell value={tracked?.last_synced_at} />
                  </DetailMetaRow>
                </div>
                {tracked?.sync_error ? (
                  <div className="mt-3">
                    <div className="tm-muted mb-1">Sync error</div>
                    <div>{tracked.sync_error}</div>
                  </div>
                ) : null}
              </section>
            </aside>
          </div>
        )
      )}
      <Modal isOpen={editModalOpen} toggle={closeEditDialog} size="lg">
        <Form onSubmit={(event) => {
          event.preventDefault();
          saveIssueEdit();
        }}
        >
          <ModalHeader toggle={closeEditDialog}>Edit issue</ModalHeader>
          <ModalBody>
            <ErrorBanner error={editError} />
            <FormGroup>
              <Label for="tm-detail-edit-title">Title</Label>
              <Input
                id="tm-detail-edit-title"
                value={editTitle}
                onChange={(event) => setEditTitle(event.target.value)}
                maxLength={255}
                required
              />
            </FormGroup>
            <FormGroup>
              <Label for="tm-detail-edit-description">Description</Label>
              <div className="tm-md-editor">
                <div className="tm-md-editor-toolbar" role="toolbar" aria-label="Edit issue markdown toolbar">
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => insertEditWrapped('**', '**', 'bold text')}
                  >
                    <i className="bi bi-type-bold" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => insertEditWrapped('_', '_', 'italic text')}
                  >
                    <i className="bi bi-type-italic" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => insertEditAtCursor('## ')}
                  >
                    <i className="bi bi-type-h2" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => prefixEditSelectedLines('> ')}
                  >
                    <i className="bi bi-chat-square-quote" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => prefixEditSelectedLines('- ')}
                  >
                    <i className="bi bi-list-ul" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => prefixEditSelectedLines('1. ')}
                  >
                    <i className="bi bi-list-ol" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => insertEditWrapped('[', '](https://)', 'link text')}
                  >
                    <i className="bi bi-link-45deg" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => insertEditWrapped('```\n', '\n```', 'code')}
                  >
                    <i className="bi bi-code-slash" aria-hidden="true" />
                  </Button>
                  <span className="tm-md-editor-separator" />
                  <Button
                    type="button"
                    color={editPreview ? 'secondary' : 'primary'}
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => setEditPreview(false)}
                  >
                    Write
                  </Button>
                  <Button
                    type="button"
                    color={editPreview ? 'primary' : 'secondary'}
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => setEditPreview(true)}
                  >
                    Preview
                  </Button>
                </div>
                {editPreview ? (
                  <div className="tm-create-md-preview">
                    <MarkdownText
                      content={editDescription}
                      className="tm-markdown tm-markdown-preview-body"
                      emptyMessage="Nothing to preview yet."
                    />
                  </div>
                ) : (
                  <Input
                    id="tm-detail-edit-description"
                    innerRef={editDescriptionRef}
                    type="textarea"
                    rows={10}
                    value={editDescription}
                    onChange={(event) => setEditDescription(event.target.value)}
                  />
                )}
              </div>
            </FormGroup>
          </ModalBody>
          <ModalFooter>
            <Button color="secondary" outline type="button" onClick={closeEditDialog} disabled={editSaving}>
              Cancel
            </Button>
            <Button color="primary" type="submit" disabled={!editTitle.trim() || editSaving}>
              {editSaving ? 'Saving...' : 'Save changes'}
            </Button>
          </ModalFooter>
        </Form>
      </Modal>
      <Modal isOpen={moveModalOpen} toggle={closeMoveDialog}>
        <Form onSubmit={(event) => {
          event.preventDefault();
          saveIssueMove();
        }}
        >
          <ModalHeader toggle={closeMoveDialog}>Move issue</ModalHeader>
          <ModalBody>
            <ErrorBanner error={moveError} />
            <p className="tm-muted">Move this issue to one of the configured target projects.</p>
            <FormGroup>
              <Label for="tm-detail-move-project">Target project</Label>
              <Input
                id="tm-detail-move-project"
                type="select"
                value={moveProjectId}
                onChange={(event) => setMoveProjectId(event.target.value)}
                required
              >
                {moveProjectOptions.length === 0 ? (
                  <option value="">No configured projects</option>
                ) : (
                  <>
                    <option value="">Select project</option>
                    {moveProjectOptions.map((project) => (
                      <option key={project.value} value={project.value}>{project.label}</option>
                    ))}
                  </>
                )}
              </Input>
            </FormGroup>
          </ModalBody>
          <ModalFooter>
            <Button color="secondary" outline type="button" onClick={closeMoveDialog} disabled={moveSaving}>
              Cancel
            </Button>
            <Button color="primary" type="submit" disabled={!moveProjectId.trim() || moveSaving}>
              {moveSaving ? 'Moving...' : 'Move issue'}
            </Button>
          </ModalFooter>
        </Form>
      </Modal>
      <Modal isOpen={assignModalOpen} toggle={closeAssignDialog}>
        <Form onSubmit={(event) => {
          event.preventDefault();
          saveIssueAssign();
        }}
        >
          <ModalHeader toggle={closeAssignDialog}>Assign issue</ModalHeader>
          <ModalBody>
            <ErrorBanner error={assignError} />
            <FormGroup>
              <Label for="tm-detail-assign-user">Assignee</Label>
              <Input
                id="tm-detail-assign-user"
                type="select"
                value={assignUserId}
                onChange={(event) => setAssignUserId(event.target.value)}
              >
                <option value="">Unassigned</option>
                {assignableUsers.map((member) => (
                  <option key={member.id || member.username || member.name} value={member.id || ''}>
                    {member.name || member.username || `User ${member.id}`}
                  </option>
                ))}
              </Input>
              {assignableUsers.length === 0 ? (
                <div className="tm-muted tm-field-help">No assignable users found for this project.</div>
              ) : null}
            </FormGroup>
          </ModalBody>
          <ModalFooter>
            <Button color="secondary" outline type="button" onClick={closeAssignDialog} disabled={assignSaving}>
              Cancel
            </Button>
            <Button color="primary" type="submit" disabled={assignSaving}>
              {assignSaving ? 'Saving...' : 'Save assignee'}
            </Button>
          </ModalFooter>
        </Form>
      </Modal>
      <Modal isOpen={mappingModalOpen} toggle={closeMappingDialog}>
        <ModalHeader toggle={closeMappingDialog}>Manual issue mapping</ModalHeader>
        <ModalBody>
          <ErrorBanner error={mappingError} />
          <p className="tm-muted">
            Paste target GitLab issue URL (for example:
            {' '}
            <code>https://gitlab.example.com/group/project/-/issues/123</code>
            ).
          </p>
          <FormGroup>
            <Label for="manual-mapping-url">Target issue URL</Label>
            <Input
              id="manual-mapping-url"
              value={mappingTargetUrl}
              onChange={(event) => setMappingTargetUrl(event.target.value)}
              placeholder="https://gitlab.example.com/group/project/-/issues/123"
            />
          </FormGroup>
        </ModalBody>
        <ModalFooter>
          <Button outline color="secondary" onClick={closeMappingDialog} disabled={mappingSaving}>
            Cancel
          </Button>
          <Button color="primary" onClick={saveManualMapping} disabled={!mappingTargetUrl.trim() || mappingSaving}>
            {mappingSaving ? 'Saving...' : 'Save mapping'}
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}

function DetailMetaRow({ label, children }) {
  return (
    <div className="tm-delivery-meta-row">
      <div className="tm-muted">{label}</div>
      <div>{children}</div>
    </div>
  );
}

function formatLabels(labels) {
  if (!Array.isArray(labels) || labels.length === 0) return '-';
  return labels.join(', ');
}

function formatAssignees(assignees) {
  if (!Array.isArray(assignees) || assignees.length === 0) return '-';
  return assignees.map((assignee) => assignee?.name || assignee?.username).filter(Boolean).join(', ') || '-';
}

function formatTicketId(value) {
  if (!value) return '-';
  return String(value);
}

function formatIssueType(value) {
  if (!value) return 'Issue';
  return String(value)
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function syncStatusLabel(value) {
  if (value === 'ok') return 'Synced';
  if (value === 'in_delivery') return 'In delivery';
  if (value === 'target_missing') return 'Target missing';
  if (value === 'error') return 'Sync error';
  return value || 'Unknown';
}

function syncStatusTone(value) {
  if (value === 'ok') return 'success';
  if (value === 'in_delivery') return 'neutral';
  if (value === 'target_missing') return 'warning';
  if (value === 'error') return 'danger';
  return 'muted';
}
