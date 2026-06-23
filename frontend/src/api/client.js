import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api'
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('ticketmaster.token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const RETURN_TOKEN_KEY = 'ticketmaster.return_token';
export const SESSION_CHANGE_EVENT = 'tm:session-change';
export const SESSION_FINALIZED_EVENT = 'tm:session-finalized';

const sessionCacheInvalidators = new Set();

export function registerSessionCacheInvalidator(invalidator) {
  sessionCacheInvalidators.add(invalidator);
  return () => sessionCacheInvalidators.delete(invalidator);
}

export function invalidateSessionCaches() {
  sessionCacheInvalidators.forEach((invalidator) => {
    try {
      invalidator();
    } catch {
      // Cache invalidation must not block session changes.
    }
  });
  notifySessionChange();
}

export function notifySessionChange() {
  window.dispatchEvent(new Event(SESSION_CHANGE_EVENT));
}

export function saveSession(payload) {
  localStorage.setItem('ticketmaster.token', payload.token);
  localStorage.setItem('ticketmaster.user', JSON.stringify(payload.user));
  if (payload.return_token) {
    localStorage.setItem(RETURN_TOKEN_KEY, payload.return_token);
  } else {
    localStorage.removeItem(RETURN_TOKEN_KEY);
  }
}

export function clearSession() {
  localStorage.removeItem('ticketmaster.token');
  localStorage.removeItem('ticketmaster.user');
  localStorage.removeItem(RETURN_TOKEN_KEY);
  invalidateSessionCaches();
}

export function hasReturnToAdmin() {
  return Boolean(localStorage.getItem(RETURN_TOKEN_KEY));
}

export function getReturnToken() {
  return localStorage.getItem(RETURN_TOKEN_KEY);
}

export function currentUser() {
  const raw = localStorage.getItem('ticketmaster.user');
  return raw ? JSON.parse(raw) : null;
}

export default api;
