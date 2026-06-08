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

export function saveSession(payload) {
  localStorage.setItem('ticketmaster.token', payload.token);
  localStorage.setItem('ticketmaster.user', JSON.stringify(payload.user));
}

export function clearSession() {
  localStorage.removeItem('ticketmaster.token');
  localStorage.removeItem('ticketmaster.user');
}

export function currentUser() {
  const raw = localStorage.getItem('ticketmaster.user');
  return raw ? JSON.parse(raw) : null;
}

export default api;
