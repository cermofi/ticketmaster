export function normalizeLoginIdentifier(value) {
  return String(value || '').trim();
}

export function isLoginFormSubmittable({ identifier, password, activationToken, submitting }) {
  if (submitting) return false;
  if (activationToken) return Boolean(normalizeLoginIdentifier(activationToken)) && Boolean(password);
  return Boolean(normalizeLoginIdentifier(identifier)) && Boolean(password);
}

export function loginSubmitLabel(activationToken) {
  return activationToken ? 'Set password' : 'Sign in';
}

export function resolveLoginErrorMessage(err) {
  const data = err?.response?.data;
  if (typeof data?.message === 'string' && data.message) return data.message;
  if (typeof data?.detail === 'string' && data.detail) return data.detail;
  if (Array.isArray(data?.detail)) return 'Request validation failed';
  return err?.message || 'Unexpected error';
}
