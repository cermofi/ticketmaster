import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Alert,
  Button,
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
import { Loading, formatInternalRoles, roleLabel } from './helpers.jsx';

export function useSession() {
  const [user, setUserState] = useState(currentUser());
  const [loading, setLoading] = useState(true);

  const setUser = (nextUser) => {
    if (nextUser) {
      localStorage.setItem('ticketmaster.user', JSON.stringify(nextUser));
    }
    setUserState(nextUser);
    setLoading(false);
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
    if (!token) {
      setLoading(false);
      return;
    }
    api.get('/auth/me')
      .then((response) => {
        setUser(response.data);
      })
      .catch(() => {
        clearSession();
        setUserState(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  useRefetchOnFocus(refreshUser);

  return {
    user,
    loading,
    setUser,
    logout: () => {
      clearSession();
      setUserState(null);
      setLoading(false);
      window.location.hash = '#/';
    }
  };
}

export default function AuthGate({ children }) {
  const session = useSession();
  useEffect(() => {
    if (!session.loading && !session.user) {
      window.dispatchEvent(new Event('tm:auth-ready'));
    }
  }, [session.loading, session.user]);
  if (session.loading) {
    return <Loading />;
  }
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
  const role = user?.kind === 'internal'
    ? formatInternalRoles(user) || 'Not set'
    : roleLabel(user?.partner_role) || 'Not set';
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
  const [identifier, setIdentifier] = useState('admin@example.test');
  const [password, setPassword] = useState('ChangeMe123!');
  const [activationToken, setActivationToken] = useState(initialToken);
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    try {
      const response = activationToken
        ? await api.post('/auth/activate', { token: activationToken, password })
        : await api.post('/auth/login', { email: identifier, password });
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
          <>
            <FormGroup>
              <Label>E-mail / přihlašovací jméno</Label>
              <Input value={identifier} onChange={(event) => setIdentifier(event.target.value)} autoComplete="username" />
            </FormGroup>
            <FormGroup>
              <Label>Heslo</Label>
              <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
            </FormGroup>
          </>
        )}
        <Button color="primary" type="submit" className="w-100">
          {activationToken ? 'Set password' : 'Sign in'}
        </Button>
      </Form>
    </div>
  );
}
