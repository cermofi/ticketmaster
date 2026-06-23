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
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  UncontrolledDropdown
} from 'reactstrap';

import api, {
  SESSION_FINALIZED_EVENT,
  clearSession,
  currentUser,
  getReturnToken,
  hasReturnToAdmin
} from '../../api/client.js';
import { applySessionUser, finalizeSession, readStoredSessionUser } from '../../api/session.js';
import { resolveLoginErrorMessage, isLoginFormSubmittable, loginSubmitLabel, normalizeLoginIdentifier } from '../loginFlow.js';
import { canReturnToAdmin, canSignInAsPartner } from '../sessionControls.js';
import { useRefetchOnFocus } from '../hooks/useLiveRefresh.js';
import { Loading, formatInternalRoles, hasAnyInternalRole, roleLabel } from './helpers.jsx';

export function useSession() {
  const [user, setUserState] = useState(() => readStoredSessionUser());
  const [loading, setLoading] = useState(true);

  const setUser = useCallback((nextUser) => {
    if (nextUser) {
      applySessionUser(nextUser);
    }
    setUserState(nextUser);
    setLoading(false);
  }, []);

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
  }, [setUser]);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  useEffect(() => {
    const syncFromStore = () => {
      setUserState(readStoredSessionUser());
      setLoading(false);
    };
    window.addEventListener(SESSION_FINALIZED_EVENT, syncFromStore);
    return () => window.removeEventListener(SESSION_FINALIZED_EVENT, syncFromStore);
  }, []);

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
    if (!session.loading) {
      window.dispatchEvent(new Event('tm:auth-ready'));
    }
  }, [session.loading]);
  if (session.loading) {
    return <Loading />;
  }
  if (!session.user) {
    return <LoginScreen />;
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
  const [partnerSignInOpen, setPartnerSignInOpen] = useState(false);
  const [returningToAdmin, setReturningToAdmin] = useState(false);
  const canSignInAsPartnerUser = canSignInAsPartner(user);
  const canReturnToAdminUser = canReturnToAdmin(user, hasReturnToAdmin());
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
  const returnToAdmin = async (event) => {
    event.preventDefault();
    const returnToken = getReturnToken();
    if (!returnToken || returningToAdmin) return;
    setReturningToAdmin(true);
    try {
      const response = await api.post('/auth/back-to-admin', { return_token: returnToken });
      finalizeSession(response.data);
    } catch (err) {
      window.alert(resolveLoginErrorMessage(err));
    } finally {
      setReturningToAdmin(false);
    }
  };

  if (!headerNavList) return null;
  return (
    <>
      {createPortal(
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
              {canReturnToAdminUser && (
                <DropdownItem onClick={returnToAdmin} disabled={returningToAdmin}>
                  {returningToAdmin ? 'Returning to admin...' : 'Back to admin'}
                </DropdownItem>
              )}
              {canSignInAsPartnerUser && (
                <DropdownItem onClick={() => setPartnerSignInOpen(true)}>
                  Sign in as partner
                </DropdownItem>
              )}
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
      )}
      {canSignInAsPartnerUser && (
        <SignInAsPartnerModal
          isOpen={partnerSignInOpen}
          onClose={() => setPartnerSignInOpen(false)}
          onSignedIn={(payload) => {
            setPartnerSignInOpen(false);
            finalizeSession(payload);
          }}
        />
      )}
    </>
  );
}

function SignInAsPartnerModal({ isOpen, onClose, onSignedIn }) {
  const [partners, setPartners] = useState([]);
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setSelectedUserId('');
      setError('');
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    Promise.all([api.get('/partners'), api.get('/users')])
      .then(([partnersResponse, usersResponse]) => {
        if (cancelled) return;
        setPartners(Array.isArray(partnersResponse.data) ? partnersResponse.data : []);
        setUsers(Array.isArray(usersResponse.data) ? usersResponse.data : []);
      })
      .catch((err) => {
        if (!cancelled) setError(resolveLoginErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const partnerNames = new Map(partners.map((row) => [row.id, row.name]));
  const partnerUsers = users
    .filter((row) => row.kind === 'partner' && row.active)
    .sort((left, right) => {
      const leftPartner = partnerNames.get(left.partner_id) || '';
      const rightPartner = partnerNames.get(right.partner_id) || '';
      return leftPartner.localeCompare(rightPartner, 'cs-CZ')
        || (left.name || left.email).localeCompare(right.name || right.email, 'cs-CZ');
    });

  const submit = async (event) => {
    event.preventDefault();
    if (!selectedUserId) return;
    setSubmitting(true);
    setError('');
    try {
      const response = await api.post('/auth/sign-in-as-partner', { user_id: selectedUserId });
      onSignedIn(response.data);
    } catch (err) {
      setError(resolveLoginErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} toggle={onClose}>
      <Form onSubmit={submit}>
        <ModalHeader toggle={onClose}>Sign in as partner</ModalHeader>
        <ModalBody>
          {error && <Alert color="danger">{error}</Alert>}
          <FormGroup>
            <Label for="tm-partner-sign-in-user">Partner account</Label>
            <Input
              id="tm-partner-sign-in-user"
              type="select"
              value={selectedUserId}
              onChange={(event) => setSelectedUserId(event.target.value)}
              disabled={loading || submitting || partnerUsers.length === 0}
            >
              <option value="">{loading ? 'Loading partner accounts...' : 'Select partner account'}</option>
              {partnerUsers.map((row) => (
                <option key={row.id} value={row.id}>
                  {(partnerNames.get(row.partner_id) || 'Partner')
                    + ' — '
                    + (row.name || row.email)
                    + ' ('
                    + (roleLabel(row.partner_role) || row.partner_role || 'partner')
                    + ')'}
                </option>
              ))}
            </Input>
          </FormGroup>
        </ModalBody>
        <ModalFooter>
          <Button color="secondary" outline onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button color="primary" type="submit" disabled={!selectedUserId || loading || submitting}>
            {submitting ? 'Signing in...' : 'Sign in'}
          </Button>
        </ModalFooter>
      </Form>
    </Modal>
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

function LoginScreen() {
  document.body.classList.add('tm-login-session');
  const initialToken = new URLSearchParams((window.location.hash.split('?')[1] || '')).get('token') || '';
  const [identifier, setIdentifier] = useState(import.meta.env.DEV ? 'admin@example.test' : '');
  const [password, setPassword] = useState(import.meta.env.DEV ? 'ChangeMe123!' : '');
  const [activationToken, setActivationToken] = useState(initialToken);
  const [error, setError] = useState('');

  const [submitting, setSubmitting] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (!isLoginFormSubmittable({ identifier, password, activationToken, submitting })) return;
    setError('');
    setSubmitting(true);
    try {
      const response = activationToken
        ? await api.post('/auth/activate', { token: activationToken, password })
        : await api.post('/auth/login', { email: normalizeLoginIdentifier(identifier), password });
      finalizeSession(response.data);
    } catch (err) {
      setError(resolveLoginErrorMessage(err));
    } finally {
      setSubmitting(false);
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
        <Button color="primary" type="submit" className="w-100" disabled={!isLoginFormSubmittable({ identifier, password, activationToken, submitting })}>
          {submitting ? 'Please wait…' : loginSubmitLabel(activationToken)}
        </Button>
      </Form>
    </div>
  );
}
