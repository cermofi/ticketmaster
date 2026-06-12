import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Alert,
  Button,
  ButtonGroup,
  Form,
  FormGroup,
  Input,
  Label
} from 'reactstrap';

import api, { clearSession, currentUser, saveSession } from '../../api/client.js';
import { roleLabel } from './helpers.jsx';

export function useSession() {
  const [user, setUser] = useState(currentUser());

  useEffect(() => {
    const isPartnerSession = user?.kind === 'partner';
    document.body.classList.toggle('tm-partner-session', isPartnerSession);
    document.body.classList.toggle('tm-login-session', !user);
    return () => {
      document.body.classList.remove('tm-partner-session');
      document.body.classList.remove('tm-login-session');
    };
  }, [user]);

  useEffect(() => {
    const token = localStorage.getItem('ticketmaster.token');
    if (!token) return;
    api.get('/auth/me')
      .then((response) => {
        localStorage.setItem('ticketmaster.user', JSON.stringify(response.data));
        setUser(response.data);
      })
      .catch(() => {
        clearSession();
        setUser(null);
      });
  }, []);

  return {
    user,
    setUser,
    logout: () => {
      clearSession();
      setUser(null);
      window.location.hash = '#/';
    }
  };
}

export default function AuthGate({ children }) {
  const session = useSession();
  if (!session.user) {
    return <LoginScreen onLogin={session.setUser} />;
  }
  return (
    <>
      <HeaderSession user={session.user} onLogout={session.logout} />
      {children(session.user)}
    </>
  );
}

function HeaderSession({ user, onLogout }) {
  const header = document.getElementById('app-header');
  if (!header) return null;
  return createPortal(
    <div className="tm-header-session">
      <div className="tm-header-user">
        <strong>{user.name}</strong>
        <span className="tm-muted">{roleLabel(user.internal_role || user.partner_role)}</span>
      </div>
      <Button size="sm" outline color="secondary" onClick={onLogout}>
        Logout
      </Button>
    </div>,
    header
  );
}

function LoginScreen({ onLogin }) {
  document.body.classList.add('tm-login-session');
  const initialToken = new URLSearchParams((window.location.hash.split('?')[1] || '')).get('token') || '';
  const [mode, setMode] = useState('internal');
  const [email, setEmail] = useState('admin@example.test');
  const [password, setPassword] = useState('ChangeMe123!');
  const [activationToken, setActivationToken] = useState(initialToken);
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    try {
      const response = activationToken
        ? await api.post('/auth/activate', { token: activationToken, password })
        : mode === 'internal'
        ? await api.post('/auth/dev-sso', { email })
        : await api.post('/auth/login', { email, password });
      saveSession(response.data);
      document.body.classList.remove('tm-login-session');
      onLogin(response.data.user);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  return (
    <div className="tm-screen tm-login">
      <Form className="tm-login-form" onSubmit={submit}>
        <h1 className="tm-login-title">TicketMaster</h1>
        {!activationToken && (
          <ButtonGroup className="mb-3 w-100">
            <Button color={mode === 'internal' ? 'primary' : 'secondary'} outline={mode !== 'internal'} onClick={() => setMode('internal')} type="button">
              Internal SSO
            </Button>
            <Button color={mode === 'partner' ? 'primary' : 'secondary'} outline={mode !== 'partner'} onClick={() => setMode('partner')} type="button">
              Partner
            </Button>
          </ButtonGroup>
        )}
        {error && <Alert color="danger">{error}</Alert>}
        {activationToken ? (
          <>
            <FormGroup>
              <Label>Reset token</Label>
              <Input value={activationToken} onChange={(event) => setActivationToken(event.target.value)} />
            </FormGroup>
            <FormGroup>
              <Label>New password</Label>
              <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" />
            </FormGroup>
          </>
        ) : (
          <FormGroup>
            <Label>Email</Label>
            <Input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
          </FormGroup>
        )}
        {!activationToken && mode === 'partner' && (
          <FormGroup>
            <Label>Password</Label>
            <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </FormGroup>
        )}
        <Button color="primary" type="submit" className="w-100">
          {activationToken ? 'Set password' : 'Sign in'}
        </Button>
      </Form>
    </div>
  );
}
