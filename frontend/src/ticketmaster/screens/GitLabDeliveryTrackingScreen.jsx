import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { usePolling, useRefetchOnFocus, useSessionDomainRefresh, DATA_DOMAINS } from '../hooks/useLiveRefresh.js';
import { useUrlFilters } from '../hooks/useUrlFilters.js';
import {
  asArray,
  downloadResponse,
  EmptyRow,
  ErrorBanner,
  exportError,
  Loading,
  MarkdownText,
  PageHeader,
  StatusPill,
  TimeCell,
  apiError,
  hasAnyInternalRole
} from './helpers.jsx';

const DEFAULT_SORT = { sort_by: 'last_gitlab_update', sort_direction: 'desc' };
const EMPTY_FILTERS = {
  search: '',
  target_team: '',
  state: '',
  assignee: '',
  label: '',
  updated_since: '',
  sort_by: DEFAULT_SORT.sort_by,
  sort_direction: DEFAULT_SORT.sort_direction
};
const FILTER_KEYS = Object.keys(EMPTY_FILTERS);
const POLL_MS = 60000;

export default function GitLabDeliveryTrackingScreen() {
  return (
    <AuthGate>
      {(user) => <TrackingDashboard user={user} />}
    </AuthGate>
  );
}

function TrackingDashboard({ user }) {
  const canView = user?.kind === 'internal';
  const canManage = canView && hasAnyInternalRole(user, ['Admin', 'DeliveryManager']);
  const { filters, syncFiltersToUrl, resetFilters: resetUrlFilters } = useUrlFilters(
    EMPTY_FILTERS,
    FILTER_KEYS
  );
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const [meta, setMeta] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [syncLoading, setSyncLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [mappingModalOpen, setMappingModalOpen] = useState(false);
  const [mappingTargetUrl, setMappingTargetUrl] = useState('');
  const [mappingError, setMappingError] = useState('');
  const [mappingSaving, setMappingSaving] = useState(false);
  const [mappingRow, setMappingRow] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailRow, setDetailRow] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [detailActionLoading, setDetailActionLoading] = useState('');
  const [detailEditModalOpen, setDetailEditModalOpen] = useState(false);
  const [detailEditTitle, setDetailEditTitle] = useState('');
  const [detailEditDescription, setDetailEditDescription] = useState('');
  const [detailEditPreview, setDetailEditPreview] = useState(false);
  const [detailEditError, setDetailEditError] = useState('');
  const [detailEditSaving, setDetailEditSaving] = useState(false);
  const detailEditDescriptionRef = useRef(null);
  const [detailMoveModalOpen, setDetailMoveModalOpen] = useState(false);
  const [detailMoveProjectId, setDetailMoveProjectId] = useState('');
  const [detailMoveError, setDetailMoveError] = useState('');
  const [detailMoveSaving, setDetailMoveSaving] = useState(false);
  const detailRequestRef = useRef(0);
  const [alertsModalOpen, setAlertsModalOpen] = useState(false);
  const [alertsRows, setAlertsRows] = useState([]);
  const [alertsUnreadCount, setAlertsUnreadCount] = useState(0);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [alertsActionLoading, setAlertsActionLoading] = useState(false);
  const [alertsError, setAlertsError] = useState('');
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createMeta, setCreateMeta] = useState(null);
  const [createMetaLoading, setCreateMetaLoading] = useState(false);
  const [createTitle, setCreateTitle] = useState('');
  const [createIssueType, setCreateIssueType] = useState('issue');
  const [createDescription, setCreateDescription] = useState('');
  const [createDescriptionPreview, setCreateDescriptionPreview] = useState(false);
  const [createConfidential, setCreateConfidential] = useState(false);
  const [createAssigneeId, setCreateAssigneeId] = useState('');
  const [createDueDate, setCreateDueDate] = useState('');
  const [createSelectedLabels, setCreateSelectedLabels] = useState([]);
  const [createLabelSearch, setCreateLabelSearch] = useState('');
  const [createSaving, setCreateSaving] = useState(false);
  const [createError, setCreateError] = useState('');
  const createDescriptionRef = useRef(null);

  const setFilters = useCallback((next) => {
    const merged = typeof next === 'function' ? next(filtersRef.current) : next;
    syncFiltersToUrl(merged);
  }, [syncFiltersToUrl]);

  const loadAlerts = useCallback(async ({ silent = false } = {}) => {
    if (!canView) return;
    if (!silent) setAlertsLoading(true);
    setAlertsError('');
    try {
      const response = await api.get('/gitlab/delivery-tracking/alerts', {
        params: { limit: 30, offset: 0 }
      });
      setAlertsRows(asArray(response.data));
      setAlertsUnreadCount(Number(response.data?.unread_count || 0));
    } catch (err) {
      setAlertsError(apiError(err));
    } finally {
      if (!silent) setAlertsLoading(false);
    }
  }, [canView]);

  const load = useCallback(async (nextFilters) => {
    if (!canView) return;
    const activeFilters = nextFilters ?? filtersRef.current;
    setError('');
    setLoading(true);
    try {
      const params = buildRequestParams(activeFilters);
      const [metaResponse, listResponse] = await Promise.all([
        api.get('/gitlab/delivery-tracking/meta'),
        api.get('/gitlab/delivery-tracking', { params })
      ]);
      setMeta(metaResponse.data);
      setRows(asArray(listResponse.data));
      await loadAlerts({ silent: true });
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  }, [canView, loadAlerts]);

  const filtersKey = useMemo(() => JSON.stringify(filters), [filters]);
  const createAvailableLabels = useMemo(() => {
    const labels = asArray(createMeta?.labels)
      .map((label) => String(label?.title || '').trim())
      .filter(Boolean);
    return Array.from(new Set(labels)).sort((left, right) => left.localeCompare(right));
  }, [createMeta]);
  const createFilteredLabels = useMemo(() => {
    const query = createLabelSearch.trim().toLowerCase();
    if (!query) return createAvailableLabels;
    return createAvailableLabels.filter((label) => label.toLowerCase().includes(query));
  }, [createAvailableLabels, createLabelSearch]);

  useEffect(() => {
    load(filters);
  }, [filtersKey, load]);

  useRefetchOnFocus(load, canView);
  useSessionDomainRefresh(DATA_DOMAINS.gitlabDeliveryTracking, load, canView);
  usePolling(load, POLL_MS, canView);

  const triggerSync = async () => {
    if (!canManage) return;
    setError('');
    setSyncLoading(true);
    try {
      await api.post('/gitlab/delivery-tracking/sync');
      await load();
    } catch (err) {
      setError(apiError(err));
    } finally {
      setSyncLoading(false);
    }
  };

  const exportDashboard = async () => {
    setError('');
    setExportLoading(true);
    try {
      const params = buildRequestParams(filtersRef.current);
      const response = await api.get('/gitlab/delivery-tracking/export', {
        params,
        responseType: 'blob'
      });
      downloadResponse(response, 'delivery_tracking.xlsx');
    } catch (err) {
      setError(await exportError(err));
    } finally {
      setExportLoading(false);
    }
  };

  const onSortChange = (key) => {
    const isSame = filtersRef.current.sort_by === key;
    const nextDirection = isSame && filtersRef.current.sort_direction === 'asc' ? 'desc' : 'asc';
    const nextFilters = {
      ...filtersRef.current,
      sort_by: key,
      sort_direction: nextDirection
    };
    setFilters(nextFilters);
  };

  const openMappingDialog = (row) => {
    setMappingRow(row);
    setMappingTargetUrl(row.target_url || '');
    setMappingError('');
    setMappingModalOpen(true);
  };

  const loadDetailDialog = useCallback(async (row) => {
    if (!row?.id) return;
    const requestId = detailRequestRef.current + 1;
    detailRequestRef.current = requestId;
    setDetailLoading(true);
    setDetailError('');
    try {
      const response = await api.get(`/gitlab/delivery-tracking/${row.id}/detail`);
      if (detailRequestRef.current !== requestId) return;
      setDetailData(response.data || null);
    } catch (err) {
      if (detailRequestRef.current !== requestId) return;
      setDetailError(apiError(err));
    } finally {
      if (detailRequestRef.current === requestId) {
        setDetailLoading(false);
      }
    }
  }, []);

  const openDetailDialog = (row) => {
    if (!row) return;
    setDetailRow(row);
    setDetailData(null);
    setDetailError('');
    setDetailModalOpen(true);
    loadDetailDialog(row);
  };

  const openAlertsDialog = () => {
    setAlertsModalOpen(true);
    loadAlerts();
  };

  const closeAlertsDialog = () => {
    if (alertsActionLoading) return;
    setAlertsModalOpen(false);
  };

  const markAllAlertsRead = async () => {
    setAlertsError('');
    setAlertsActionLoading(true);
    try {
      await api.post('/gitlab/delivery-tracking/alerts/read-all');
      await loadAlerts({ silent: true });
    } catch (err) {
      setAlertsError(apiError(err));
    } finally {
      setAlertsActionLoading(false);
    }
  };

  const openAlertIssue = (alert) => {
    const matched = rows.find(
      (row) => row.id === alert.tracked_issue_id || row.delivery_issue_iid === alert.delivery_issue_iid
    );
    if (matched) {
      closeAlertsDialog();
      openDetailDialog(matched);
      return;
    }
    if (alert.delivery_url) {
      window.open(alert.delivery_url, '_blank', 'noopener,noreferrer');
    }
  };

  const closeDetailDialog = () => {
    detailRequestRef.current += 1;
    setDetailModalOpen(false);
    setDetailRow(null);
    setDetailData(null);
    setDetailError('');
    setDetailLoading(false);
    setDetailActionLoading('');
    setDetailEditModalOpen(false);
    setDetailEditError('');
    setDetailEditSaving(false);
    setDetailMoveModalOpen(false);
    setDetailMoveError('');
    setDetailMoveSaving(false);
  };

  const refreshDetailDialog = () => {
    if (!detailRow) return;
    loadDetailDialog(detailRow);
  };

  const closeDetailIssue = async () => {
    if (!canManage || !detailRow?.id || detailActionLoading) return;
    if (typeof window !== 'undefined') {
      const confirmed = window.confirm('Close this GitLab issue?');
      if (!confirmed) return;
    }
    setDetailActionLoading('close');
    setDetailError('');
    try {
      await api.post(`/gitlab/delivery-tracking/${detailRow.id}/close`);
      await load();
      await loadDetailDialog(detailRow);
    } catch (err) {
      setDetailError(apiError(err));
    } finally {
      setDetailActionLoading('');
    }
  };

  const openDetailEditDialog = () => {
    if (!canManage) return;
    const issue = detailData?.issue;
    if (!issue) return;
    setDetailEditTitle(issue.title || '');
    setDetailEditDescription(issue.description || '');
    setDetailEditPreview(false);
    setDetailEditError('');
    setDetailEditModalOpen(true);
  };

  const closeDetailEditDialog = () => {
    if (detailEditSaving) return;
    setDetailEditModalOpen(false);
    setDetailEditError('');
  };

  const setDetailEditDescriptionWithSelection = (nextValue, selectionStart, selectionEnd) => {
    setDetailEditDescription(nextValue);
    requestAnimationFrame(() => {
      const input = detailEditDescriptionRef.current;
      if (!input) return;
      input.focus();
      if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
        input.setSelectionRange(selectionStart, selectionEnd);
      }
    });
  };

  const insertDetailEditWrapped = (prefix, suffix = '', placeholder = '') => {
    const input = detailEditDescriptionRef.current;
    const currentValue = detailEditDescription || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const selectedText = currentValue.slice(selectionStart, selectionEnd);
    const body = selectedText || placeholder;
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefix}${body}${suffix}${currentValue.slice(selectionEnd)}`;
    const cursorStart = selectionStart + prefix.length;
    const cursorEnd = cursorStart + body.length;
    setDetailEditDescriptionWithSelection(nextValue, cursorStart, cursorEnd);
  };

  const insertDetailEditAtCursor = (text) => {
    const input = detailEditDescriptionRef.current;
    const currentValue = detailEditDescription || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const nextValue = `${currentValue.slice(0, selectionStart)}${text}${currentValue.slice(selectionEnd)}`;
    const cursor = selectionStart + text.length;
    setDetailEditDescriptionWithSelection(nextValue, cursor, cursor);
  };

  const prefixDetailEditSelectedLines = (prefix) => {
    const input = detailEditDescriptionRef.current;
    const currentValue = detailEditDescription || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    if (selectionStart === selectionEnd) {
      insertDetailEditAtCursor(prefix);
      return;
    }
    const selected = currentValue.slice(selectionStart, selectionEnd);
    const prefixed = selected.split('\n').map((line) => (line ? `${prefix}${line}` : prefix.trimEnd())).join('\n');
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefixed}${currentValue.slice(selectionEnd)}`;
    setDetailEditDescriptionWithSelection(nextValue, selectionStart, selectionStart + prefixed.length);
  };

  const saveDetailIssueEdit = async () => {
    if (!canManage || !detailRow?.id) return;
    const title = detailEditTitle.trim();
    if (!title) {
      setDetailEditError('Title is required.');
      return;
    }
    setDetailEditSaving(true);
    setDetailEditError('');
    setDetailError('');
    try {
      await api.patch(`/gitlab/delivery-tracking/${detailRow.id}/edit`, {
        title,
        description: detailEditDescription
      });
      setDetailEditModalOpen(false);
      await load();
      await loadDetailDialog(detailRow);
    } catch (err) {
      setDetailEditError(apiError(err));
    } finally {
      setDetailEditSaving(false);
    }
  };

  const openDetailMoveDialog = () => {
    if (!canManage || !detailData?.issue) return;
    setDetailMoveProjectId('');
    setDetailMoveError('');
    setDetailMoveModalOpen(true);
  };

  const closeDetailMoveDialog = () => {
    if (detailMoveSaving) return;
    setDetailMoveModalOpen(false);
    setDetailMoveError('');
  };

  const saveDetailIssueMove = async () => {
    if (!canManage || !detailRow?.id) return;
    const toProjectId = detailMoveProjectId.trim();
    if (!toProjectId) {
      setDetailMoveError('Target project is required.');
      return;
    }
    setDetailMoveSaving(true);
    setDetailMoveError('');
    setDetailError('');
    try {
      await api.post(`/gitlab/delivery-tracking/${detailRow.id}/move`, { to_project_id: toProjectId });
      setDetailMoveModalOpen(false);
      await load();
      await loadDetailDialog(detailRow);
    } catch (err) {
      setDetailMoveError(apiError(err));
    } finally {
      setDetailMoveSaving(false);
    }
  };

  const closeMappingDialog = () => {
    if (mappingSaving) return;
    setMappingModalOpen(false);
    setMappingRow(null);
    setMappingTargetUrl('');
    setMappingError('');
  };

  const saveManualMapping = async () => {
    if (!mappingRow) return;
    setMappingError('');
    setMappingSaving(true);
    try {
      await api.post(`/gitlab/delivery-tracking/${mappingRow.id}/manual-mapping`, {
        target_url: mappingTargetUrl
      });
      setMappingModalOpen(false);
      setMappingRow(null);
      setMappingTargetUrl('');
      await load();
    } catch (err) {
      setMappingError(apiError(err));
    } finally {
      setMappingSaving(false);
    }
  };

  const loadCreateMeta = useCallback(async () => {
    if (!canManage) return;
    setCreateMetaLoading(true);
    setCreateError('');
    try {
      const response = await api.get('/gitlab/delivery-tracking/create-meta');
      const payload = response.data || {};
      setCreateMeta(payload);
      const types = asArray(payload.issue_types);
      const defaultType = String(types.find((item) => item?.value === 'issue')?.value || types[0]?.value || 'issue');
      setCreateIssueType(defaultType);
      const currentAssignee = payload?.current_assignee_id;
      setCreateAssigneeId(currentAssignee ? String(currentAssignee) : '');
    } catch (err) {
      setCreateError(apiError(err));
    } finally {
      setCreateMetaLoading(false);
    }
  }, [canManage]);

  const openCreateDialog = () => {
    if (!canManage) return;
    setCreateError('');
    setCreateTitle('');
    setCreateIssueType('issue');
    setCreateDescription('');
    setCreateDescriptionPreview(false);
    setCreateConfidential(false);
    setCreateAssigneeId('');
    setCreateDueDate('');
    setCreateSelectedLabels([]);
    setCreateLabelSearch('');
    setCreateModalOpen(true);
    loadCreateMeta();
  };

  const closeCreateDialog = () => {
    if (createSaving) return;
    setCreateModalOpen(false);
    setCreateError('');
  };

  const assignToMe = () => {
    const assigneeId = createMeta?.current_assignee_id;
    if (!assigneeId) return;
    setCreateAssigneeId(String(assigneeId));
  };

  const toggleCreateLabel = (labelTitle) => {
    setCreateSelectedLabels((previous) => {
      if (previous.includes(labelTitle)) {
        return previous.filter((item) => item !== labelTitle);
      }
      return [...previous, labelTitle];
    });
  };

  const removeCreateLabel = (labelTitle) => {
    setCreateSelectedLabels((previous) => previous.filter((item) => item !== labelTitle));
  };

  const setCreateDescriptionWithSelection = (nextValue, selectionStart, selectionEnd) => {
    setCreateDescription(nextValue);
    requestAnimationFrame(() => {
      const input = createDescriptionRef.current;
      if (!input) return;
      input.focus();
      if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
        input.setSelectionRange(selectionStart, selectionEnd);
      }
    });
  };

  const insertCreateWrapped = (prefix, suffix = '', placeholder = '') => {
    const input = createDescriptionRef.current;
    const currentValue = createDescription || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const selectedText = currentValue.slice(selectionStart, selectionEnd);
    const body = selectedText || placeholder;
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefix}${body}${suffix}${currentValue.slice(selectionEnd)}`;
    const cursorStart = selectionStart + prefix.length;
    const cursorEnd = cursorStart + body.length;
    setCreateDescriptionWithSelection(nextValue, cursorStart, cursorEnd);
  };

  const insertCreateAtCursor = (text) => {
    const input = createDescriptionRef.current;
    const currentValue = createDescription || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    const nextValue = `${currentValue.slice(0, selectionStart)}${text}${currentValue.slice(selectionEnd)}`;
    const cursor = selectionStart + text.length;
    setCreateDescriptionWithSelection(nextValue, cursor, cursor);
  };

  const prefixCreateSelectedLines = (prefix) => {
    const input = createDescriptionRef.current;
    const currentValue = createDescription || '';
    const selectionStart = input?.selectionStart ?? currentValue.length;
    const selectionEnd = input?.selectionEnd ?? currentValue.length;
    if (selectionStart === selectionEnd) {
      insertCreateAtCursor(prefix);
      return;
    }
    const selected = currentValue.slice(selectionStart, selectionEnd);
    const prefixed = selected.split('\n').map((line) => (line ? `${prefix}${line}` : prefix.trimEnd())).join('\n');
    const nextValue = `${currentValue.slice(0, selectionStart)}${prefixed}${currentValue.slice(selectionEnd)}`;
    setCreateDescriptionWithSelection(nextValue, selectionStart, selectionStart + prefixed.length);
  };

  const createTicket = async () => {
    if (!canManage) return;
    const title = createTitle.trim();
    if (!title) {
      setCreateError('Title is required.');
      return;
    }
    const assigneeId = Number.parseInt(createAssigneeId, 10);
    const payload = {
      title,
      description: createDescription,
      issue_type: createIssueType || null,
      confidential: createConfidential,
      assignee_ids: Number.isInteger(assigneeId) ? [assigneeId] : [],
      due_date: createDueDate || null,
      labels: createSelectedLabels
    };
    setCreateSaving(true);
    setCreateError('');
    setError('');
    try {
      await api.post('/gitlab/delivery-tracking/create', payload);
      setCreateModalOpen(false);
      await load();
    } catch (err) {
      setCreateError(apiError(err));
    } finally {
      setCreateSaving(false);
    }
  };

  if (!canView) {
    return (
      <div className="tm-screen">
        <PageHeader title="Tickets" />
        <ErrorBanner error="Tickets are available only to internal users." />
      </div>
    );
  }

  return (
    <div className="tm-screen">
      <PageHeader
        title="Tickets"
        actions={(
          <div className="d-flex gap-2">
            {canManage && (
              <Button color="primary" onClick={openCreateDialog}>
                Create ticket
              </Button>
            )}
            <Button
              color="secondary"
              outline
              className="tm-delivery-alert-bell"
              onClick={openAlertsDialog}
              aria-label="Open ticket alerts"
              title="Ticket alerts"
            >
              <i className="bi bi-bell" aria-hidden="true" />
              {alertsUnreadCount > 0 && (
                <span className="tm-delivery-alert-badge">{formatAlertUnreadCount(alertsUnreadCount)}</span>
              )}
            </Button>
            {canManage && (
              <Button color="secondary" outline onClick={triggerSync} disabled={syncLoading}>
                {syncLoading ? 'Sync in progress...' : 'Sync now'}
              </Button>
            )}
            <Button color="secondary" outline onClick={exportDashboard} disabled={exportLoading}>
              {exportLoading ? 'Exporting...' : 'Export Excel'}
            </Button>
          </div>
        )}
      >
        {meta?.last_sync_run?.finished_at ? `Last sync: ${new Date(meta.last_sync_run.finished_at).toLocaleString()}` : 'No sync run yet'}
      </PageHeader>
      <ErrorBanner error={error} />
      {loading && !meta ? <Loading /> : (
        <>
          <TrackingFilters
            filters={filters}
            setFilters={setFilters}
            teams={asArray(meta?.target_teams)}
            states={asArray(meta?.states)}
            assignees={asArray(meta?.assignees)}
            labels={asArray(meta?.labels)}
            onApply={load}
            onReset={() => {
              const reset = resetUrlFilters();
              load(reset);
            }}
          />
          <TrackingTable
            rows={rows}
            sortBy={filters.sort_by}
            sortDirection={filters.sort_direction}
            onSortChange={onSortChange}
            onOpenDetails={openDetailDialog}
          />
        </>
      )}
      <TrackingDetailsModal
        isOpen={detailModalOpen}
        row={detailRow}
        detailData={detailData}
        loading={detailLoading}
        error={detailError}
        canManage={canManage}
        onClose={closeDetailDialog}
        onRefresh={refreshDetailDialog}
        actionLoading={detailActionLoading}
        onCloseIssue={closeDetailIssue}
        onEditIssue={openDetailEditDialog}
        onMoveIssue={openDetailMoveDialog}
        onManualMapping={(row) => {
          if (!row) return;
          closeDetailDialog();
          openMappingDialog(row);
        }}
      />
      <Modal isOpen={detailEditModalOpen} toggle={closeDetailEditDialog} size="lg">
        <Form onSubmit={(event) => {
          event.preventDefault();
          saveDetailIssueEdit();
        }}
        >
          <ModalHeader toggle={closeDetailEditDialog}>Edit issue</ModalHeader>
          <ModalBody>
            <ErrorBanner error={detailEditError} />
            <FormGroup>
              <Label for="tm-detail-edit-title">Title</Label>
              <Input
                id="tm-detail-edit-title"
                value={detailEditTitle}
                onChange={(event) => setDetailEditTitle(event.target.value)}
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
                    onClick={() => insertDetailEditWrapped('**', '**', 'bold text')}
                  >
                    <i className="bi bi-type-bold" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => insertDetailEditWrapped('_', '_', 'italic text')}
                  >
                    <i className="bi bi-type-italic" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => insertDetailEditAtCursor('## ')}
                  >
                    <i className="bi bi-type-h2" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => prefixDetailEditSelectedLines('> ')}
                  >
                    <i className="bi bi-chat-square-quote" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => prefixDetailEditSelectedLines('- ')}
                  >
                    <i className="bi bi-list-ul" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => prefixDetailEditSelectedLines('1. ')}
                  >
                    <i className="bi bi-list-ol" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => insertDetailEditWrapped('[', '](https://)', 'link text')}
                  >
                    <i className="bi bi-link-45deg" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    color="secondary"
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => insertDetailEditWrapped('```\n', '\n```', 'code')}
                  >
                    <i className="bi bi-code-slash" aria-hidden="true" />
                  </Button>
                  <span className="tm-md-editor-separator" />
                  <Button
                    type="button"
                    color={detailEditPreview ? 'secondary' : 'primary'}
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => setDetailEditPreview(false)}
                  >
                    Write
                  </Button>
                  <Button
                    type="button"
                    color={detailEditPreview ? 'primary' : 'secondary'}
                    outline
                    size="sm"
                    className="tm-md-toolbar-btn"
                    onClick={() => setDetailEditPreview(true)}
                  >
                    Preview
                  </Button>
                </div>
                {detailEditPreview ? (
                  <div className="tm-create-md-preview">
                    <MarkdownText
                      content={detailEditDescription}
                      className="tm-markdown tm-markdown-preview-body"
                      emptyMessage="Nothing to preview yet."
                    />
                  </div>
                ) : (
                  <Input
                    id="tm-detail-edit-description"
                    innerRef={detailEditDescriptionRef}
                    type="textarea"
                    rows={10}
                    value={detailEditDescription}
                    onChange={(event) => setDetailEditDescription(event.target.value)}
                  />
                )}
              </div>
            </FormGroup>
          </ModalBody>
          <ModalFooter>
            <Button color="secondary" outline type="button" onClick={closeDetailEditDialog} disabled={detailEditSaving}>
              Cancel
            </Button>
            <Button color="primary" type="submit" disabled={!detailEditTitle.trim() || detailEditSaving}>
              {detailEditSaving ? 'Saving...' : 'Save changes'}
            </Button>
          </ModalFooter>
        </Form>
      </Modal>
      <Modal isOpen={detailMoveModalOpen} toggle={closeDetailMoveDialog}>
        <Form onSubmit={(event) => {
          event.preventDefault();
          saveDetailIssueMove();
        }}
        >
          <ModalHeader toggle={closeDetailMoveDialog}>Move issue</ModalHeader>
          <ModalBody>
            <ErrorBanner error={detailMoveError} />
            <p className="tm-muted">
              Move this issue to another project by entering target project path or ID
              {' '}
              <code>group/project</code>
              .
            </p>
            <FormGroup>
              <Label for="tm-detail-move-project">Target project</Label>
              <Input
                id="tm-detail-move-project"
                value={detailMoveProjectId}
                onChange={(event) => setDetailMoveProjectId(event.target.value)}
                placeholder="group/project or 123"
                required
              />
            </FormGroup>
          </ModalBody>
          <ModalFooter>
            <Button color="secondary" outline type="button" onClick={closeDetailMoveDialog} disabled={detailMoveSaving}>
              Cancel
            </Button>
            <Button color="primary" type="submit" disabled={!detailMoveProjectId.trim() || detailMoveSaving}>
              {detailMoveSaving ? 'Moving...' : 'Move issue'}
            </Button>
          </ModalFooter>
        </Form>
      </Modal>
      <DeliveryAlertsModal
        isOpen={alertsModalOpen}
        alerts={alertsRows}
        loading={alertsLoading}
        actionLoading={alertsActionLoading}
        unreadCount={alertsUnreadCount}
        error={alertsError}
        onClose={closeAlertsDialog}
        onRefresh={() => loadAlerts()}
        onMarkAllRead={markAllAlertsRead}
        onOpenAlert={openAlertIssue}
      />
      <Modal isOpen={createModalOpen} toggle={closeCreateDialog} size="lg">
        <Form onSubmit={(event) => {
          event.preventDefault();
          createTicket();
        }}
        >
          <ModalHeader toggle={closeCreateDialog}>
            New Issue
            {createMeta?.project?.path_with_namespace ? (
              <div className="tm-muted mt-1 fs-6">{createMeta.project.path_with_namespace}</div>
            ) : null}
          </ModalHeader>
          <ModalBody>
            <ErrorBanner error={createError} />
            {createMetaLoading && !createMeta ? <Loading /> : (
              <>
                <FormGroup>
                  <Label for="tm-create-title">Title (required)</Label>
                  <Input
                    id="tm-create-title"
                    value={createTitle}
                    onChange={(event) => setCreateTitle(event.target.value)}
                    maxLength={255}
                    required
                  />
                </FormGroup>

                <FormGroup>
                  <Label for="tm-create-issue-type">Type</Label>
                  <Input
                    id="tm-create-issue-type"
                    type="select"
                    value={createIssueType}
                    onChange={(event) => setCreateIssueType(event.target.value)}
                  >
                    {(asArray(createMeta?.issue_types).length > 0
                      ? asArray(createMeta?.issue_types)
                      : [{ value: 'issue', label: 'Issue' }]).map((issueType) => (
                      <option key={issueType.value} value={issueType.value}>{issueType.label}</option>
                    ))}
                  </Input>
                </FormGroup>

                <FormGroup>
                  <Label for="tm-create-description">Description</Label>
                  <div className="tm-md-editor">
                    <div className="tm-md-editor-toolbar" role="toolbar" aria-label="Issue description markdown toolbar">
                      <Button
                        type="button"
                        color="secondary"
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        title="Bold"
                        aria-label="Bold"
                        onClick={() => insertCreateWrapped('**', '**', 'bold text')}
                      >
                        <i className="bi bi-type-bold" aria-hidden="true" />
                      </Button>
                      <Button
                        type="button"
                        color="secondary"
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        title="Italic"
                        aria-label="Italic"
                        onClick={() => insertCreateWrapped('_', '_', 'italic text')}
                      >
                        <i className="bi bi-type-italic" aria-hidden="true" />
                      </Button>
                      <Button
                        type="button"
                        color="secondary"
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        title="Heading"
                        aria-label="Heading"
                        onClick={() => insertCreateAtCursor('## ')}
                      >
                        <i className="bi bi-type-h2" aria-hidden="true" />
                      </Button>
                      <Button
                        type="button"
                        color="secondary"
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        title="Quote"
                        aria-label="Quote"
                        onClick={() => prefixCreateSelectedLines('> ')}
                      >
                        <i className="bi bi-chat-square-quote" aria-hidden="true" />
                      </Button>
                      <Button
                        type="button"
                        color="secondary"
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        title="Bulleted list"
                        aria-label="Bulleted list"
                        onClick={() => prefixCreateSelectedLines('- ')}
                      >
                        <i className="bi bi-list-ul" aria-hidden="true" />
                      </Button>
                      <Button
                        type="button"
                        color="secondary"
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        title="Numbered list"
                        aria-label="Numbered list"
                        onClick={() => prefixCreateSelectedLines('1. ')}
                      >
                        <i className="bi bi-list-ol" aria-hidden="true" />
                      </Button>
                      <Button
                        type="button"
                        color="secondary"
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        title="Link"
                        aria-label="Link"
                        onClick={() => insertCreateWrapped('[', '](https://)', 'link text')}
                      >
                        <i className="bi bi-link-45deg" aria-hidden="true" />
                      </Button>
                      <Button
                        type="button"
                        color="secondary"
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        title="Code block"
                        aria-label="Code block"
                        onClick={() => insertCreateWrapped('```\n', '\n```', 'code')}
                      >
                        <i className="bi bi-code-slash" aria-hidden="true" />
                      </Button>
                      <span className="tm-md-editor-separator" />
                      <Button
                        type="button"
                        color={createDescriptionPreview ? 'secondary' : 'primary'}
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        onClick={() => setCreateDescriptionPreview(false)}
                      >
                        Write
                      </Button>
                      <Button
                        type="button"
                        color={createDescriptionPreview ? 'primary' : 'secondary'}
                        outline
                        size="sm"
                        className="tm-md-toolbar-btn"
                        onClick={() => setCreateDescriptionPreview(true)}
                      >
                        Preview
                      </Button>
                    </div>
                    {createDescriptionPreview ? (
                      <div className="tm-create-md-preview">
                        <MarkdownText
                          content={createDescription}
                          className="tm-markdown tm-markdown-preview-body"
                          emptyMessage="Nothing to preview yet."
                        />
                      </div>
                    ) : (
                      <Input
                        id="tm-create-description"
                        innerRef={createDescriptionRef}
                        type="textarea"
                        rows={10}
                        value={createDescription}
                        onChange={(event) => setCreateDescription(event.target.value)}
                        placeholder="Write a description..."
                      />
                    )}
                  </div>
                  <div className="tm-muted tm-field-help">GitLab Flavored Markdown is supported.</div>
                </FormGroup>

                <FormGroup check className="mb-3">
                  <Input
                    id="tm-create-confidential"
                    type="checkbox"
                    checked={createConfidential}
                    onChange={(event) => setCreateConfidential(event.target.checked)}
                  />
                  <Label for="tm-create-confidential" check>
                    This issue is confidential
                  </Label>
                </FormGroup>

                <div className="row g-3">
                  <div className="col-12 col-md-6">
                    <FormGroup>
                      <Label for="tm-create-assignee">Assignee</Label>
                      <div className="d-flex align-items-center gap-2">
                        <Input
                          id="tm-create-assignee"
                          type="select"
                          value={createAssigneeId}
                          onChange={(event) => setCreateAssigneeId(event.target.value)}
                        >
                          <option value="">Unassigned</option>
                          {asArray(createMeta?.assignees).map((assignee) => (
                            <option key={assignee.id} value={String(assignee.id)}>
                              {assignee.name || assignee.username || `User ${assignee.id}`}
                            </option>
                          ))}
                        </Input>
                        <Button
                          type="button"
                          color="link"
                          className="p-0 text-nowrap"
                          disabled={!createMeta?.current_assignee_id}
                          onClick={assignToMe}
                        >
                          Assign to me
                        </Button>
                      </div>
                    </FormGroup>
                  </div>
                  <div className="col-12 col-md-6">
                    <FormGroup>
                      <Label for="tm-create-due-date">Due date</Label>
                      <Input
                        id="tm-create-due-date"
                        type="date"
                        value={createDueDate}
                        onChange={(event) => setCreateDueDate(event.target.value)}
                      />
                    </FormGroup>
                  </div>
                  <div className="col-12">
                    <FormGroup>
                      <Label for="tm-create-labels">Labels</Label>
                      <Input
                        id="tm-create-labels"
                        type="search"
                        value={createLabelSearch}
                        onChange={(event) => setCreateLabelSearch(event.target.value)}
                        placeholder="Search labels..."
                      />
                      <div className="tm-create-label-picker mt-2">
                        {createFilteredLabels.length === 0 ? (
                          <div className="tm-muted">No labels found.</div>
                        ) : createFilteredLabels.map((labelTitle, index) => {
                          const optionId = `tm-create-label-option-${index}`;
                          return (
                            <FormGroup check className="mb-1" key={labelTitle}>
                              <Input
                                id={optionId}
                                type="checkbox"
                                checked={createSelectedLabels.includes(labelTitle)}
                                onChange={() => toggleCreateLabel(labelTitle)}
                              />
                              <Label for={optionId} check>{labelTitle}</Label>
                            </FormGroup>
                          );
                        })}
                      </div>
                      <div className="tm-muted tm-field-help">Pick multiple labels and quickly search in the list.</div>
                      {createSelectedLabels.length > 0 ? (
                        <div className="tm-create-selected-labels">
                          {createSelectedLabels.map((labelTitle) => (
                            <button
                              type="button"
                              className="tm-create-selected-label"
                              key={labelTitle}
                              onClick={() => removeCreateLabel(labelTitle)}
                              title={`Remove ${labelTitle}`}
                            >
                              <span>{labelTitle}</span>
                              <i className="bi bi-x-lg" aria-hidden="true" />
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </FormGroup>
                  </div>
                </div>
              </>
            )}
          </ModalBody>
          <ModalFooter>
            <Button color="secondary" outline type="button" onClick={closeCreateDialog} disabled={createSaving}>
              Cancel
            </Button>
            <Button color="primary" type="submit" disabled={!createTitle.trim() || createSaving || createMetaLoading}>
              {createSaving ? 'Creating...' : 'Create issue'}
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

function TrackingFilters({
  filters,
  setFilters,
  teams,
  states,
  assignees,
  labels,
  onApply,
  onReset
}) {
  const update = (key, value) => setFilters({ ...filters, [key]: value });

  return (
    <Form className="tm-delivery-filters-panel" onSubmit={(event) => { event.preventDefault(); onApply(); }}>
      <div className="tm-delivery-filters-head">
        <h6>Filters</h6>
        <span>Refine issues by team, assignee, labels and state.</span>
      </div>
      <div className="tm-delivery-filters-grid">
        <FormGroup className="tm-delivery-filter-search">
          <Label>Search</Label>
          <Input
            value={filters.search}
            placeholder="Search by delivery title or ticket ID"
            onChange={(event) => update('search', event.target.value)}
          />
        </FormGroup>
        <FormGroup>
          <Label>Target team</Label>
          <Input type="select" value={filters.target_team} onChange={(event) => update('target_team', event.target.value)}>
            <option value="">All</option>
            {teams.map((team) => <option key={team.name} value={team.name}>{team.name}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Current state</Label>
          <Input type="select" value={filters.state} onChange={(event) => update('state', event.target.value)}>
            <option value="">All</option>
            {states.map((state) => <option key={state} value={state}>{state}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Asignee</Label>
          <Input type="select" value={filters.assignee} onChange={(event) => update('assignee', event.target.value)}>
            <option value="">All</option>
            {assignees.map((assignee) => <option key={assignee} value={assignee}>{assignee}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Labels</Label>
          <Input type="select" value={filters.label} onChange={(event) => update('label', event.target.value)}>
            <option value="">All</option>
            {labels.map((label) => <option key={label} value={label}>{label}</option>)}
          </Input>
        </FormGroup>
        <FormGroup>
          <Label>Updated since</Label>
          <Input type="date" value={filters.updated_since} onChange={(event) => update('updated_since', event.target.value)} />
        </FormGroup>
      </div>
      <div className="tm-delivery-filters-actions">
        <Button size="sm" color="primary" type="submit">Apply filters</Button>
        <Button size="sm" color="secondary" outline type="button" onClick={onReset}>Reset</Button>
      </div>
    </Form>
  );
}

function TrackingTable({ rows, sortBy, sortDirection, onSortChange, onOpenDetails }) {
  const headers = [
    { key: 'last_gitlab_update', label: 'last update' },
    { key: 'ticket_id', label: 'ID' },
    { key: 'delivery_issue', label: 'delivery issue' },
    { key: 'current_state', label: 'Current state' },
    { key: 'target_issue_url', label: 'team id' },
    { key: 'assignee', label: 'Asignee' },
    { key: 'labels', label: 'Labels' }
  ];

  return (
    <div className="tm-table-wrap tm-delivery-table-wrap">
      <Table hover className="tm-table">
        <thead>
          <tr>
            {headers.map((header) => {
              const isActive = sortBy === header.key;
              const direction = isActive ? sortDirection : null;
              const ariaSort = isActive ? (direction === 'asc' ? 'ascending' : 'descending') : 'none';
              return (
                <th key={header.key} aria-sort={ariaSort}>
                  <button
                    type="button"
                    className={`tm-sort-button${isActive ? ' is-active' : ''}`}
                    onClick={() => onSortChange(header.key)}
                    aria-label={`Sort by ${header.label}${isActive ? ` (${direction})` : ''}`}
                  >
                    <span>{header.label}</span>
                    <span className="tm-sort-indicator" aria-hidden="true">
                      {isActive ? (direction === 'asc' ? '↑' : '↓') : '↕'}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const currentState = row.target_state || row.delivery_state;
            const labels = (Array.isArray(row.target_labels) && row.target_labels.length > 0)
              ? row.target_labels
              : row.delivery_labels;
            return (
              <tr key={row.id}>
                <td className="tm-quiet-cell">
                  <TimeCell value={row.target_updated_at || row.delivery_updated_at} />
                </td>
                <td className="tm-quiet-cell">{formatTicketId(row.delivery_issue_iid)}</td>
                <td>
                  <button
                    type="button"
                    className="tm-delivery-drilldown"
                    onClick={() => onOpenDetails(row)}
                  >
                    {row.delivery_title || '-'}
                  </button>
                </td>
                <td>
                  {currentState ? <StatusPill value={currentState} /> : <span className="tm-muted">-</span>}
                </td>
                <td>
                  <ExternalLink href={row.target_url} label={row.target_issue_iid || 'Open'} />
                </td>
                <td className="tm-quiet-cell">{formatAssignees(row.target_assignees)}</td>
                <td className="tm-quiet-cell">{formatLabels(labels)}</td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <EmptyRow
              colSpan="7"
              title="No tracked issues found"
              message="Adjust filters or run a sync to import Delivery issues from GitLab."
            />
          )}
        </tbody>
      </Table>
    </div>
  );
}

function DeliveryAlertsModal({
  isOpen,
  alerts,
  loading,
  actionLoading,
  unreadCount,
  error,
  onClose,
  onRefresh,
  onMarkAllRead,
  onOpenAlert
}) {
  return (
    <Modal isOpen={isOpen} toggle={onClose} size="lg">
      <ModalHeader toggle={onClose}>
        Delivery alerts
      </ModalHeader>
      <ModalBody>
        <ErrorBanner error={error} />
        <div className="tm-delivery-alerts-head">
          <span className="tm-muted">Unread alerts: {unreadCount}</span>
          <div className="d-flex gap-2">
            <Button size="sm" color="secondary" outline onClick={onRefresh} disabled={loading || actionLoading}>
              Refresh
            </Button>
            <Button size="sm" color="primary" outline onClick={onMarkAllRead} disabled={unreadCount === 0 || actionLoading}>
              {actionLoading ? 'Marking...' : 'Mark all read'}
            </Button>
          </div>
        </div>
        <div className="tm-delivery-alert-list">
          {loading && alerts.length === 0 ? (
            <div className="tm-muted">Loading alerts...</div>
          ) : alerts.length === 0 ? (
            <div className="tm-muted">No alerts yet.</div>
          ) : alerts.map((alert) => (
            <button
              key={alert.id}
              type="button"
              className={`tm-delivery-alert-item${alert.is_read ? '' : ' is-unread'}`}
              onClick={() => onOpenAlert(alert)}
            >
              <div className="tm-delivery-alert-title-row">
                <strong>{alert.message || 'Delivery ticket changed'}</strong>
                {!alert.is_read && <span className="tm-delivery-alert-dot" aria-label="Unread alert" />}
              </div>
              <div className="tm-muted">#{alert.delivery_issue_iid} {alert.delivery_title}</div>
              {alert.change_summary ? (
                <div className="tm-delivery-alert-summary">{alert.change_summary}</div>
              ) : null}
              <div className="tm-muted">
                <TimeCell value={alert.created_at} />
              </div>
            </button>
          ))}
        </div>
      </ModalBody>
      <ModalFooter>
        <Button outline color="secondary" onClick={onClose} disabled={actionLoading}>
          Close
        </Button>
      </ModalFooter>
    </Modal>
  );
}

function TrackingDetailsModal({
  isOpen,
  row,
  detailData,
  loading,
  error,
  actionLoading,
  canManage,
  onClose,
  onRefresh,
  onCloseIssue,
  onEditIssue,
  onMoveIssue,
  onManualMapping
}) {
  const tracked = detailData?.tracked_issue || row;
  const issue = detailData?.issue || null;
  const notes = asArray(detailData?.notes);
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
  const issueReference = issue?.reference || (issue?.iid ? `#${issue.iid}` : formatTicketId(tracked?.delivery_issue_iid));
  const noteCount = Number(issue?.user_notes_count || notes.length || 0);

  return (
    <Modal isOpen={isOpen} toggle={onClose} size="xl" className="tm-delivery-detail-modal">
      <ModalHeader toggle={onClose}>
        <div className="tm-delivery-detail-head">
          <div className="tm-muted text-uppercase small">GitLab issue detail</div>
          <div className="tm-delivery-detail-title-row">
            <strong>{issueReference}</strong>
            {currentState ? <StatusPill value={currentState} /> : null}
            {issue?.issue_type ? <span className="tm-muted">{formatIssueType(issue.issue_type)}</span> : null}
          </div>
          <div>{issue?.title || tracked?.delivery_title || '-'}</div>
        </div>
      </ModalHeader>
      <ModalBody>
        <ErrorBanner error={error} />
        {loading && !detailData ? <Loading /> : (
          !tracked ? null : (
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
              </div>
              <aside className="tm-delivery-detail-side">
                {canManage && tracked ? (
                  <section className="tm-delivery-detail-block tm-workflow-card">
                    <div className="tm-delivery-detail-block-head">Workflow</div>
                    <div className="tm-workflow-actions">
                      <button
                        type="button"
                        className="tm-workflow-action-btn tm-workflow-action-btn-primary"
                        onClick={onCloseIssue}
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
                        onClick={onEditIssue}
                        disabled={Boolean(actionLoading) || loading || !issue}
                      >
                        <i className="bi bi-pencil-square" aria-hidden="true" />
                        <span>{actionLoading === 'edit' ? 'Opening...' : 'Edit issue'}</span>
                      </button>
                      <button
                        type="button"
                        className="tm-workflow-action-btn"
                        onClick={onMoveIssue}
                        disabled={Boolean(actionLoading) || loading || !issue}
                      >
                        <i className="bi bi-arrow-left-right" aria-hidden="true" />
                        <span>{actionLoading === 'move' ? 'Moving...' : 'Move issue'}</span>
                      </button>
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
      </ModalBody>
      <ModalFooter>
        {canManage && tracked?.target_missing ? (
          <Button color="secondary" outline onClick={() => onManualMapping(tracked)}>
            Map manually
          </Button>
        ) : null}
        <Button color="secondary" outline onClick={onRefresh} disabled={loading || !tracked || Boolean(actionLoading)}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </Button>
        <Button outline color="secondary" onClick={onClose}>
          Close
        </Button>
      </ModalFooter>
    </Modal>
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

function ExternalLink({ href, label }) {
  if (!href) return <span className="tm-muted">-</span>;
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {label}
    </a>
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

function buildRequestParams(filters) {
  const params = {};
  if (filters.search) params.search = filters.search;
  if (filters.target_team) params.target_team = filters.target_team;
  if (filters.state) params.state = filters.state;
  if (filters.assignee) params.assignee = filters.assignee;
  if (filters.label) params.label = filters.label;
  if (filters.updated_since) params.updated_since = filters.updated_since;
  if (filters.sort_by) params.sort_by = filters.sort_by;
  if (filters.sort_direction) params.sort_direction = filters.sort_direction;
  return params;
}

function formatAlertUnreadCount(value) {
  const count = Number(value || 0);
  if (count > 99) return '99+';
  return String(Math.max(count, 0));
}
