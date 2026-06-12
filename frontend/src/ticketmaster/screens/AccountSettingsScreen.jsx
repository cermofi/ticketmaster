import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Form, FormGroup, Input, Label } from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { useRefetchOnFocus } from '../hooks/useLiveRefresh.js';
import { ErrorBanner, Loading, PageHeader, apiError, roleLabel } from './helpers.jsx';

export default function AccountSettingsScreen() {
  return (
    <AuthGate>
      {(user, session) => <AccountSettings user={user} session={session} />}
    </AuthGate>
  );
}

function AccountSettings({ user, session }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState({ name: '', email: '' });

  const loadProfile = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const response = await api.get('/account/me');
      setProfile(response.data);
      setForm(profileToForm(response.data));
    } catch (err) {
      setError(apiError(err));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const refreshProfile = useCallback(() => loadProfile({ silent: true }), [loadProfile]);
  useRefetchOnFocus(refreshProfile);

  const emailEditable = profile?.email_editable === true;
  const role = useMemo(
    () => roleLabel(profile?.internal_role || profile?.partner_role) || 'Not set',
    [profile]
  );
  const hasChanges = useMemo(() => (
    profile
    && form.name.trim() !== (profile.name || '')
    && form.name.trim().length > 0
  ) || (
    profile
    && emailEditable
    && form.email.trim() !== (profile.email || '')
  ), [emailEditable, form.email, form.name, profile]);

  const resetForm = () => {
    if (!profile) return;
    setForm(profileToForm(profile));
    setError('');
    setSuccess('');
  };

  const save = async (event) => {
    event.preventDefault();
    if (!profile) return;
    if (!form.name.trim()) {
      setError('Name is required');
      return;
    }

    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const payload = { name: form.name.trim() };
      if (emailEditable) {
        payload.email = form.email.trim();
      }
      const response = await api.patch('/account/me', payload);
      setProfile(response.data);
      setForm(profileToForm(response.data));
      session.setUser(profileToSessionUser(response.data));
      setSuccess('Account settings saved.');
    } catch (err) {
      setError(apiError(err));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Loading />;

  return (
    <div className="tm-screen">
      <PageHeader title="Account settings">
        Manage your account details.
      </PageHeader>
      <ErrorBanner error={error} />
      {success && <Alert color="success" className="tm-alert">{success}</Alert>}
      <section className="tm-form-page tm-account-card">
        <Form onSubmit={save}>
          <FormGroup>
            <Label for="account-name">Full name</Label>
            <Input
              id="account-name"
              value={form.name}
              autoComplete="name"
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              required
            />
          </FormGroup>
          <FormGroup>
            <Label for="account-email">Email</Label>
            <Input
              id="account-email"
              value={form.email}
              autoComplete="email"
              disabled={!emailEditable}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
            {!emailEditable && (
              <div className="tm-field-note">
                {profile?.email_readonly_reason || 'E-mail cannot be changed from this screen.'}
              </div>
            )}
          </FormGroup>
          <FormGroup>
            <Label for="account-role">Role</Label>
            <Input id="account-role" value={role} disabled />
          </FormGroup>
          <div className="tm-account-meta">
            <span>User ID</span>
            <code>{profile?.id || user.id}</code>
          </div>
          <div className="tm-account-actions">
            <Button
              type="button"
              color="secondary"
              outline
              onClick={resetForm}
              disabled={saving || !profile}
            >
              Cancel
            </Button>
            <Button
              color="primary"
              type="submit"
              disabled={saving || !hasChanges}
            >
              {saving ? 'Saving...' : 'Save changes'}
            </Button>
          </div>
        </Form>
      </section>
    </div>
  );
}

function profileToForm(profile) {
  return {
    name: profile?.name || '',
    email: profile?.email || ''
  };
}

function profileToSessionUser(profile) {
  return {
    id: profile?.id,
    email: profile?.email,
    name: profile?.name,
    kind: profile?.kind,
    internal_role: profile?.internal_role,
    partner_id: profile?.partner_id,
    partner_role: profile?.partner_role,
    active: profile?.active,
    created_at: profile?.created_at
  };
}
