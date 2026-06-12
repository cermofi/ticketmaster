import React, { useState } from 'react';
import { Alert, Button, Form, FormGroup, Input, Label } from 'reactstrap';

import api from '../../api/client.js';
import AuthGate from './AuthGate.jsx';
import { ErrorBanner, PageHeader, apiError } from './helpers.jsx';

export default function ChangePasswordScreen() {
  return (
    <AuthGate>
      {() => <ChangePassword />}
    </AuthGate>
  );
}

function ChangePassword() {
  const [form, setForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: ''
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const updateField = (key, value) => setForm({ ...form, [key]: value });

  const reset = () => {
    setForm({ current_password: '', new_password: '', confirm_password: '' });
    setError('');
    setSuccess('');
  };

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setSuccess('');

    const validationError = validatePasswordForm(form);
    if (validationError) {
      setError(validationError);
      return;
    }

    setSaving(true);
    try {
      await api.post('/account/change-password', form);
      setSuccess('Password changed successfully.');
      setForm({ current_password: '', new_password: '', confirm_password: '' });
    } catch (err) {
      setError(apiError(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="tm-screen">
      <PageHeader title="Change password">
        Update your password for this account.
      </PageHeader>
      <ErrorBanner error={error} />
      {success && <Alert color="success" className="tm-alert">{success}</Alert>}
      <section className="tm-form-page tm-account-card">
        <Form onSubmit={submit}>
          <FormGroup>
            <Label for="current-password">Current password</Label>
            <Input
              id="current-password"
              type="password"
              autoComplete="current-password"
              value={form.current_password}
              onChange={(event) => updateField('current_password', event.target.value)}
              required
            />
          </FormGroup>
          <FormGroup>
            <Label for="new-password">New password</Label>
            <Input
              id="new-password"
              type="password"
              autoComplete="new-password"
              value={form.new_password}
              onChange={(event) => updateField('new_password', event.target.value)}
              required
            />
          </FormGroup>
          <FormGroup>
            <Label for="confirm-password">Confirm new password</Label>
            <Input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              value={form.confirm_password}
              onChange={(event) => updateField('confirm_password', event.target.value)}
              required
            />
          </FormGroup>
          <div className="tm-field-note mb-3">
            Password requirements: at least 8 characters, at least one letter, at least one number.
          </div>
          <div className="tm-account-actions">
            <Button type="button" color="secondary" outline onClick={reset} disabled={saving}>
              Cancel
            </Button>
            <Button color="primary" type="submit" disabled={saving}>
              {saving ? 'Changing...' : 'Change password'}
            </Button>
          </div>
        </Form>
      </section>
    </div>
  );
}

function validatePasswordForm(form) {
  if (form.new_password !== form.confirm_password) {
    return 'New password and confirmation do not match.';
  }
  if (form.new_password.length < 8) {
    return 'New password must contain at least 8 characters.';
  }
  if (!/[A-Za-z]/.test(form.new_password)) {
    return 'New password must contain at least one letter.';
  }
  if (!/\d/.test(form.new_password)) {
    return 'New password must contain at least one number.';
  }
  return '';
}
