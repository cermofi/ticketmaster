import React, { useEffect, useState } from 'react';
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
      <div className="tm-session-bar">
        <div>
          <strong>{session.user.name}</strong>
          <span className="tm-muted ms-2">{roleLabel(session.user.internal_role || session.user.partner_role)}</span>
        </div>
        <Button size="sm" outline color="secondary" onClick={session.logout}>
          <i className="bi bi-box-arrow-right me-1" />
          Logout
        </Button>
      </div>
      {children(session.user)}
    </>
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
              <i className="bi bi-building-lock me-1" />
              Internal SSO
            </Button>
            <Button color={mode === 'partner' ? 'primary' : 'secondary'} outline={mode !== 'partner'} onClick={() => setMode('partner')} type="button">
              <i className="bi bi-person-badge me-1" />
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
            <Label>E-mail</Label>
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
          <i className="bi bi-box-arrow-in-right me-1" />
          {activationToken ? 'Set password' : 'Login'}
        </Button>
      </Form>
    </div>
  );
}
