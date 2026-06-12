import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Alert,
  Button,
  ButtonGroup,
  DropdownItem,
  DropdownMenu,
  DropdownToggle,
  Form,
  FormGroup,
  Input,
  Label,
  UncontrolledDropdown
} from 'reactstrap';

import api, { clearSession, currentUser, saveSession } from '../../api/client.js';
import { useRefetchOnFocus } from '../hooks/useLiveRefresh.js';
import { roleLabel } from './helpers.jsx';

export function useSession() {
  const [user, setUserState] = useState(currentUser());

  const setUser = (nextUser) => {
    if (nextUser) {
      localStorage.setItem('ticketmaster.user', JSON.stringify(nextUser));
    }
    setUserState(nextUser);
  };

  useEffect(() => {
    const isPartnerSession = user?.kind === 'partner';
    document.body.classList.toggle('tm-partner-session', isPartnerSession);
    document.body.classList.toggle('tm-login-session', !user);
    return () => {
      document.body.classList.remove('tm-partner-session');
      document.body.classList.remove('tm-login-session');
    };
  }, [user]);

  const refreshUser = useCallback(() => {
    const token = localStorage.getItem('ticketmaster.token');
    if (!token) return;
    api.get('/auth/me')
      .then((response) => {
        setUser(response.data);
      })
      .catch(() => {
        clearSession();
        setUserState(null);
      });
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  useRefetchOnFocus(refreshUser);

  return {
    user,
    setUser,
    logout: () => {
      clearSession();
      setUserState(null);
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
      {children(session.user, session)}
    </>
  );
}

function HeaderSession({ user, onLogout }) {
  const [headerNavList, setHeaderNavList] = useState(null);
  const displayName = (user?.name || user?.email || 'User').trim();
  const role = roleLabel(user?.internal_role || user?.partner_role);
  const email = (user?.email || '').trim();
  const initials = userInitials(user?.name, email);

  useEffect(() => {
    let observer = null;

    const resolveHeaderNav = () => {
      const node = document.querySelector('#app-header > ul.nav')
        || document.querySelector('#app-header ul.nav');
      if (!node) return false;
      setHeaderNavList(node);
      return true;
    };

    if (!resolveHeaderNav()) {
      observer = new MutationObserver(() => {
        if (resolveHeaderNav()) {
          observer?.disconnect();
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }

    return () => observer?.disconnect();
  }, []);

  const openSettings = (event) => {
    event.preventDefault();
    window.location.hash = '#/settings';
  };
  const openAccountSettings = (event) => {
    event.preventDefault();
    window.location.hash = '#/account';
  };
  const openChangePassword = (event) => {
    event.preventDefault();
    window.location.hash = '#/account/password';
  };

  if (!headerNavList) return null;
  return createPortal(
    <li className="tm-header-session nav-item">
      <UncontrolledDropdown className="tm-header-user-menu">
        <DropdownToggle
          tag="button"
          type="button"
          className="tm-header-user-toggle tm-header-avatar-toggle"
          aria-label="Open user menu"
          title="Account menu"
        >
          <span className="tm-header-avatar" aria-hidden="true">{initials}</span>
        </DropdownToggle>
        <DropdownMenu end className="tm-header-account-menu">
          <div className="tm-header-account-head">
            <strong className="tm-header-account-name">{displayName}</strong>
            {role && <div className="tm-header-account-role">{role}</div>}
            {email && <div className="tm-header-account-email">{email}</div>}
          </div>
          <DropdownItem onClick={openAccountSettings}>Account settings</DropdownItem>
          <DropdownItem onClick={openChangePassword}>Change password</DropdownItem>
          <DropdownItem onClick={openSettings}>Preferences</DropdownItem>
          <DropdownItem divider />
          <DropdownItem className="tm-header-logout-item" onClick={onLogout}>
            Logout
          </DropdownItem>
        </DropdownMenu>
      </UncontrolledDropdown>
    </li>,
    headerNavList
  );
}

function userInitials(name, email = '') {
  const rawParts = String(name || '').trim().split(/[\s._@-]+/).filter(Boolean);
  if (rawParts.length > 0) {
    const first = rawParts[0]?.charAt(0) || '';
    const second = rawParts[1]?.charAt(0) || rawParts[0]?.charAt(1) || '';
    const letters = `${first}${second}`.toLocaleUpperCase('cs-CZ');
    if (letters.trim()) return letters;
  }
  const normalized = String(name || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
  const normalizedParts = normalized.split(/[\s._@-]+/).filter(Boolean);
  if (normalizedParts.length > 0) {
    const first = normalizedParts[0]?.charAt(0) || '';
    const second = normalizedParts[1]?.charAt(0) || normalizedParts[0]?.charAt(1) || '';
    const letters = `${first}${second}`.toUpperCase();
    if (letters.trim()) return letters;
  }
  const emailLetter = email.trim().charAt(0).toUpperCase();
  return emailLetter || 'U';
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
